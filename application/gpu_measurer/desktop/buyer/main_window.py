"""GPU Check — single-device inspection app for used-GPU buyers.

Flow (brief §9.7): 검사 모드 선택 → 장치 선택 → 진행 상태 → 결론과 근거 → 리포트.
One window with three pages: Home, Progress, Result.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...gpu_reference import (
    LOAD_TEMPERATURE_NORMAL_MAX_C,
    LOAD_TEMPERATURE_THROTTLE_WATCH_C,
)
from ...models import WorkloadSpec
from ...report_builder import verdict
from ...reporting import summarize_throttle
from ...serialization import redact_sensitive_data
from ..shared.api_client import ApiError
from ..shared.service_adapter import UiServiceAdapter
from ..shared.theme import APP_STYLESHEET
from ..shared.widgets import (
    BigStat,
    Card,
    InfoDot,
    RangeGauge,
    StatusBadge,
    collapsible,
    h1,
    h2,
    muted,
)

CLOCK_TOOLTIP = (
    "그래픽 클럭은 상황에 따라 달라요.<br><br>"
    "• <b>유휴 시</b>: 절전을 위해 낮아져요 (낮은 게 정상).<br>"
    "• <b>부하 시</b>: 정격 부스트 근처까지 올라가요.<br><br>"
    "정상 여부는 부하를 거는 <b>‘벤치마크’</b>로<br>확인하는 게 정확해요."
)

PSTATE_TOOLTIP = (
    "성능 상태(P-State)는 GPU의 전력·클럭 단계예요.<br>"
    "숫자가 <b>낮을수록 고성능</b>입니다.<br><br>"
    "• <b>P0</b>: 최대 성능 (부하가 걸릴 때)<br>"
    "• P2~P5: 중간 단계<br>"
    "• <b>P8</b>: 유휴·절전 (놀 때 — 정상이에요)"
)

VRAM_TOOLTIP = (
    "VRAM은 왜 중요할까?<br><br>"
    "GPU 전용 메모리예요. AI 모델·데이터가 여기에<br>"
    "올라가기 때문에, 모델이 이 용량 안에 들어가야<br>"
    "실행할 수 있어요.<br><br>"
    "그래서 중고 구매 시 <b>VRAM 전체 용량</b>이<br>"
    "중요한 기준이에요 (예: 8GB vs 24GB).<br>"
    "사용량은 부하에 따라 오르내려요."
)

TIMING_TOOLTIP = (
    "연산 시간을 어떻게 쟀는지예요.<br><br>"
    "• <b>cuda_event</b>: GPU 내부 타이머로 측정 —<br>"
    "&nbsp;&nbsp;순수 GPU 연산 시간만 정확히 재요.<br>"
    "&nbsp;&nbsp;(데이터 복사·CPU 시간이 섞이지 않음)<br>"
    "• perf_counter: CPU 시계 기준 (덜 정확)<br>"
    "• fake: 실제 GPU 없이 만든 테스트 값<br><br>"
    "cuda_event라야 achieved TFLOPS를 믿을 수 있어요."
)

PROTOCOL_TOOLTIP = (
    "이 검사의 <b>고유 방식 이름</b>이에요.<br><br>"
    "같은 연산·정밀도(dtype)·행렬 크기로 잰<br>"
    "결과끼리만 공정하게 비교할 수 있어요.<br><br>"
    "이 값이 같아야 ‘처음 검사 대비’와 ‘모델 비교’가<br>"
    "성립해요. (반복 횟수는 비교에서 제외돼요)"
)

# "ⓘ" 호버 설명 — 쓰로틀 개념을 쉬운 말로.
THROTTLE_TOOLTIP = (
    "쓰로틀링은 GPU를 보호하는 안전장치예요.<br><br>"
    "• <b>열(온도) 쓰로틀</b>: GPU 발열이 심하다는 신호예요.<br>"
    "&nbsp;&nbsp;추적·확인이 필요한 요인이에요.<br>"
    "• <b>전력 제한</b>: 고부하에서 한도를 지키는<br>"
    "&nbsp;&nbsp;정상 동작이에요."
)

# 쓰로틀 코드 -> 사용자용 한국어 라벨
THROTTLE_LABELS = {
    "sw_power_cap": "전력 제한",
    "hw_power_brake_slowdown": "전력 브레이크",
    "hw_thermal_slowdown": "온도(열) 제한",
    "sw_thermal_slowdown": "온도(열) 제한",
    "hw_slowdown": "하드웨어 감속",
    "applications_clocks_setting": "앱 클럭 설정",
    "sync_boost": "동기 부스트",
    "display_clock_setting": "디스플레이 클럭",
}
from ..shared.worker import ValidationWorker

FIELD_SPEC = WorkloadSpec(size=4096, warmup_iterations=10, measured_iterations=120)
THOROUGH_SPEC = WorkloadSpec()  # defaults: 4096 / warmup 20 / 300 iters


def _page(name: str) -> QWidget:
    page = QWidget()
    page.setObjectName("Page")
    return page


class GpuCheckWindow(QMainWindow):
    def __init__(self, adapter: UiServiceAdapter | None = None):
        super().__init__()
        self.adapter = adapter or UiServiceAdapter.create()
        self.gpu_index = 0
        self._gpu_uuid = ""
        self._gpu_name = ""
        self._worker: ValidationWorker | None = None
        self._last_result = None
        self._last_payload: dict | None = None
        self._verify_code = ""
        self._elapsed = QElapsedTimer()

        self._benchmarking = False

        self.setWindowTitle("GPU Check — 중고 GPU 검사")
        self.setStyleSheet(APP_STYLESHEET)
        self.resize(780, 680)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Tab 1 — live detailed GPU info.
        self.info_tab = _page("info")
        self._build_info_tab()
        self.tabs.addTab(self.info_tab, "GPU 정보")

        # Tab 2 — benchmark flow (home / progress / result stacked).
        self.bench_tab = _page("bench")
        bench_layout = QVBoxLayout(self.bench_tab)
        bench_layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        bench_layout.addWidget(self.stack)
        self._build_home()
        self._build_progress()
        self._build_result()
        self.stack.setCurrentWidget(self.home_page)
        self.tabs.addTab(self.bench_tab, "벤치마크")

        # Tab 3 — cross-model comparison over saved results.
        self.compare_tab = _page("compare")
        self._build_compare_tab()
        self.tabs.addTab(self.compare_tab, "모델 비교")

        # Live info refresh: poll short sensor snapshots while the info tab is
        # active and no benchmark is running (snapshots are short requests).
        self._info_timer = QTimer(self)
        self._info_timer.setInterval(1500)
        self._info_timer.timeout.connect(self._refresh_info)
        self._info_timer.start()
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Always-on cumulative monitor: records a throttle/temp observation every
        # few seconds (any tab), paused during a benchmark. This is how "이 앱을
        # 깔고 난 후 쓰로틀링이 얼마나 됐는지" is accumulated.
        self._monitor_timer = QTimer(self)
        self._monitor_timer.setInterval(5000)
        self._monitor_timer.timeout.connect(self._monitor_tick)
        self._monitor_timer.start()

        self._refresh_info_identity()
        self._refresh_usage_card()

    # ---- Tab 1: GPU 정보 -------------------------------------------------
    # (key, 라벨, 단위, ⓘ 툴팁) — 2열 그리드라 쌍(전력 사용/한도, VRAM 사용/전체)을
    # 같은 줄(짝수 인덱스 = 왼쪽)에 오도록 배치.
    _LIVE_FIELDS = [
        ("temperature_c", "온도", "°C", None),
        ("gpu_utilization_pct", "GPU 사용률", "%", None),
        ("power_draw_w", "전력 사용", "W", None),
        ("power_limit_w", "전력 한도", "W", None),
        ("memory_used_mib", "VRAM 사용", "MiB", None),
        ("memory_total_mib", "VRAM 전체", "MiB", VRAM_TOOLTIP),
        ("graphics_clock_mhz", "그래픽 클럭", "MHz", CLOCK_TOOLTIP),
        ("memory_clock_mhz", "메모리 클럭", "MHz", None),
        ("performance_state", "성능 상태", "", PSTATE_TOOLTIP),
        ("memory_controller_pct", "메모리 컨트롤러", "%", None),
        ("fan_speed_pct", "팬 속도", "%", None),
        ("throttle_reasons_active", "쓰로틀 상태", "", THROTTLE_TOOLTIP),
    ]

    def _build_info_tab(self) -> None:
        outer = QVBoxLayout(self.info_tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("Page")
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        root.addWidget(h1("GPU 정보"))
        self.info_title = h2("")
        root.addWidget(self.info_title)

        # 정적 장치 정보
        identity = Card()
        identity.add(h2("장치 정보"))
        self.identity_label = muted("")
        identity.add(self.identity_label)
        root.addWidget(identity)

        # 실시간 센서 (자동 갱신)
        live = Card()
        head = QHBoxLayout()
        head.addWidget(h2("실시간 센서"))
        head.addStretch(1)
        self.info_updated = muted("자동 갱신 중…")
        head.addWidget(self.info_updated)
        live.layout().addLayout(head)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(8)
        self.info_live: dict[str, QLabel] = {}
        for i, (key, label, _unit, tooltip) in enumerate(self._LIVE_FIELDS):
            r, c = divmod(i, 2)
            caption_row = QHBoxLayout()
            caption_row.setSpacing(4)
            caption = QLabel(label)
            caption.setObjectName("Muted")
            caption_row.addWidget(caption)
            if tooltip:
                caption_row.addWidget(InfoDot(tooltip))
            caption_row.addStretch(1)
            value = QLabel("—")
            value.setObjectName("H2")
            cell = QVBoxLayout()
            cell.setSpacing(0)
            cell.addLayout(caption_row)
            cell.addWidget(value)
            wrap = QWidget()
            wrap.setLayout(cell)
            grid.addWidget(wrap, r, c)
            self.info_live[key] = value
        live.add(grid_host)
        live.add(
            muted(
                "온도·전력·VRAM 사용량은 GPU가 무거운 작업을 할 때만 올라가요. "
                "지금 낮다면 GPU가 쉬고 있다는 뜻이고 정상이에요."
            )
        )
        root.addWidget(live)

        # 누적 쓰로틀 기록 (이 앱이 관찰한 동안)
        usage = Card()
        usage_head = QHBoxLayout()
        usage_head.addWidget(h2("쓰로틀링 누적 기록"))
        usage_head.addWidget(InfoDot(THROTTLE_TOOLTIP))
        usage_head.addStretch(1)
        usage.layout().addLayout(usage_head)
        usage.add(muted("이 앱이 켜져 있던 동안 관찰한 값이에요. GPU 제조 이후 전체 이력은 아닙니다."))
        self.usage_label = QLabel("아직 관찰 기록이 없어요.")
        self.usage_label.setObjectName("H2")
        self.usage_label.setWordWrap(True)
        usage.add(self.usage_label)
        root.addWidget(usage)
        root.addStretch(1)

    def _refresh_info_identity(self) -> None:
        if not self.adapter.is_ready:
            self.info_title.setText("GPU collector를 찾을 수 없습니다.")
            self.identity_label.setText(self.adapter.error or "NVIDIA 드라이버를 확인하세요.")
            return
        info = self.adapter.inspect(self.gpu_index)
        if not info:
            self.info_title.setText("GPU 정보를 읽을 수 없습니다.")
            return
        gpu = info.get("gpu", {})

        def value(key: str, unit: str = "") -> str:
            raw = gpu.get(key)
            return "확인 불가" if raw in (None, "", "[N/A]") else f"{raw}{unit}"

        self._gpu_uuid = gpu.get("uuid", "") or ""
        self._gpu_name = gpu.get("name", "") or ""
        self.info_title.setText(f"GPU {gpu.get('index', self.gpu_index)} — {gpu.get('name', '')}")
        self.identity_label.setText(
            "\n".join(
                [
                    f"VRAM {value('memory.total', ' MiB')}",
                    f"드라이버 {value('driver_version')}   ·   VBIOS {value('vbios_version')}",
                    f"Compute Capability {value('compute_cap')}",
                    f"최대 클럭 {value('clocks.max.graphics', ' MHz')} (그래픽) / {value('clocks.max.memory', ' MHz')} (메모리)",
                    f"PCIe {value('pci.bus_id')}   ·   장치 ID {value('pci.device_id')}",
                    "UUID [보안을 위해 표시하지 않음]",
                ]
            )
        )

    def _refresh_info(self) -> None:
        # Only poll when the info tab is active and no benchmark is running.
        if self._benchmarking or self.tabs.currentWidget() is not self.info_tab:
            return
        if not self.adapter.is_ready:
            return
        snapshot = self.adapter.snapshot(self.gpu_index)
        if not snapshot:
            self.info_updated.setText("센서를 읽지 못했어요.")
            return
        values = snapshot.get("values", {})
        for key, _label, unit, _tip in self._LIVE_FIELDS:
            raw = values.get(key)
            if raw is None:
                text = "미지원"
            elif isinstance(raw, float):
                text = f"{raw:.0f}{unit}"
            else:
                text = f"{raw}{unit}"
            self.info_live[key].setText(text)
        stamp = snapshot.get("timestamp", "")
        self.info_updated.setText(f"업데이트 {stamp[11:19]}" if len(stamp) >= 19 else "업데이트됨")

    def _monitor_tick(self) -> None:
        # Accumulate a cumulative observation; skip while a benchmark runs (it
        # feeds its own denser samples into the monitor on completion).
        if self._benchmarking or not self.adapter.is_ready or not self._gpu_uuid:
            return
        snapshot = self.adapter.snapshot(self.gpu_index)
        if not snapshot:
            return
        self.adapter.record_usage(self._gpu_uuid, snapshot.get("values", {}))
        self._refresh_usage_card()

    def _refresh_usage_card(self) -> None:
        if not self._gpu_uuid:
            return
        summary = self.adapter.usage_summary(self._gpu_uuid)
        if not summary.get("has_data") or not summary.get("observation_count"):
            self.usage_label.setText("아직 관찰 기록이 없어요. 앱을 켜 두면 계속 쌓입니다.")
            return
        if not summary.get("supported"):
            self.usage_label.setText("이 드라이버는 쓰로틀 상태를 제공하지 않아 누적할 수 없어요.")
            return
        total = summary["observation_count"]
        throttled = summary["throttled_count"]
        peak = summary.get("peak_temperature_c")
        reasons = summary.get("reason_counts", {})
        reason_text = (
            ", ".join(
                f"{THROTTLE_LABELS.get(name, name)} {count}회"
                for name, count in reasons.items()
            )
            if reasons
            else "없음"
        )
        rows = [
            ("총 관찰 개수", f"{total}회"),
            ("쓰로틀 개수", f"{throttled}회"),
            ("종류별 개수", reason_text),
            ("관찰된 최고 온도", f"{peak:.0f}°C" if peak is not None else "—"),
        ]
        body = "".join(
            f"<tr><td style='color:#757575;padding:2px 24px 2px 0'>{label}</td>"
            f"<td><b>{value}</b></td></tr>"
            for label, value in rows
        )
        self.usage_label.setText(f"<table>{body}</table>")

    # ---- Tab 3: 모델 비교 ------------------------------------------------
    _COMPARE_COLUMNS = ["#", "모델", "achieved TFLOPS", "1회 실행시간", "측정일"]

    def _build_compare_tab(self) -> None:
        root = QVBoxLayout(self.compare_tab)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)
        root.addWidget(h1("모델 비교"))
        self.compare_note = muted("")
        root.addWidget(self.compare_note)

        self.compare_table = QTableWidget(0, len(self._COMPARE_COLUMNS))
        self.compare_table.setHorizontalHeaderLabels(self._COMPARE_COLUMNS)
        self.compare_table.verticalHeader().setVisible(False)
        self.compare_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.compare_table.setSelectionMode(QAbstractItemView.NoSelection)
        self.compare_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        root.addWidget(self.compare_table, 1)

        root.addWidget(
            muted(
                "같은 검사 방식(protocol·dtype·크기)에서 측정한 결과만 비교해요. "
                "‘이 성능을 기준으로 저장’한 검사만 포함됩니다. 서로 다른 검사끼리 섞거나 "
                "종합 점수·가격을 매기지는 않아요."
            )
        )

    def _refresh_compare(self) -> None:
        report = self.adapter.compare_models()
        entries = report.get("entries", [])
        if not report.get("available") or not entries:
            self.compare_note.setText(
                "아직 비교할 저장된 결과가 없어요. 벤치마크 후 ‘이 성능을 기준으로 저장’을 "
                "누르면 여기에 쌓이고, 다른 GPU를 검사할수록 비교표가 채워집니다."
            )
            self.compare_table.setRowCount(0)
            return
        dtype = report.get("dtype")
        size = report.get("size")
        self.compare_note.setText(
            f"검사 방식: {dtype} · {size}×{size} 행렬  ·  achieved TFLOPS가 높을수록 빠릅니다."
        )
        self.compare_table.setRowCount(len(entries))
        for r, entry in enumerate(entries):
            is_current = entry["name"] == self._gpu_name
            per_iter = entry.get("per_iter_ms")
            cells = [
                str(r + 1),
                entry["name"] + ("  (현재 GPU)" if is_current else ""),
                f"{entry['achieved_tflops']:.2f}",
                f"{per_iter:.2f} ms" if per_iter is not None else "—",
                entry.get("measured_at", "—"),
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if is_current:
                    from PySide6.QtGui import QColor, QFont

                    item.setBackground(QColor("#eef6db"))
                    font = QFont()
                    font.setBold(True)
                    item.setFont(font)
                self.compare_table.setItem(r, c, item)

    def _on_tab_changed(self, _index: int) -> None:
        current = self.tabs.currentWidget()
        if current is self.info_tab:
            self._refresh_info()
        elif current is self.compare_tab:
            self._refresh_compare()

    # ---- Home -----------------------------------------------------------
    def _build_home(self) -> None:
        self.home_page = _page("home")
        root = QVBoxLayout(self.home_page)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        root.addWidget(h1("GPU Check"))
        root.addWidget(muted("구매 전 확인과 수령 후 검수를 연결해 거래 위험과 반품 분쟁을 줄입니다."))

        device_card = Card()
        device_card.add(h2("감지된 GPU"))
        self.device_label = QLabel()
        self.device_label.setObjectName("H2")
        device_card.add(self.device_label)
        self.device_detail = muted("")
        device_card.add(self.device_detail)
        root.addWidget(device_card)

        # 검사 모드 선택 (상호 배타) — 선택 후 아래 '검사 시작'을 눌러야 진행됩니다.
        mode_card = Card()
        mode_card.add(h2("검사 모드 선택"))
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.field_button = QPushButton("◯  현장 간이 확인 (약 30초)")
        self.thorough_button = QPushButton("◯  수령 후 정밀 검수 (약 1~2분)")
        for button in (self.field_button, self.thorough_button):
            button.setObjectName("ModeButton")
            button.setCheckable(True)
            button.toggled.connect(self._sync_mode_labels)
            self.mode_group.addButton(button)
            mode_card.add(button)
        self.thorough_button.setChecked(True)
        root.addWidget(mode_card)

        advanced, adv_layout = collapsible("고급 설정 (선택)")
        row = QHBoxLayout()
        row.addWidget(QLabel("dtype"))
        self.dtype_combo = QComboBox()
        self.dtype_combo.addItems(["float32", "float16", "bfloat16"])
        row.addWidget(self.dtype_combo)
        row.addWidget(QLabel("행렬 크기"))
        self.size_spin = QSpinBox()
        self.size_spin.setRange(512, 16384)
        self.size_spin.setSingleStep(512)
        self.size_spin.setValue(THOROUGH_SPEC.size)
        row.addWidget(self.size_spin)
        row.addWidget(QLabel("반복"))
        self.iter_spin = QSpinBox()
        self.iter_spin.setRange(10, 5000)
        self.iter_spin.setValue(THOROUGH_SPEC.measured_iterations)
        row.addWidget(self.iter_spin)
        row_wrap = QWidget()
        row_wrap.setLayout(row)
        adv_layout.addWidget(row_wrap)
        root.addWidget(advanced)

        self.start_button = QPushButton("검사 시작")
        self.start_button.clicked.connect(self._on_start_clicked)
        root.addWidget(self.start_button)

        recent_card = Card()
        recent_card.add(h2("최근 검사 결과"))
        self.recent_label = muted("아직 검사 이력이 없습니다.")
        recent_card.add(self.recent_label)
        root.addWidget(recent_card)
        root.addStretch(1)

        self.stack.addWidget(self.home_page)
        self._refresh_home()

    def _on_start_clicked(self) -> None:
        spec = FIELD_SPEC if self.field_button.isChecked() else self._thorough_spec()
        self._start(spec)

    def _sync_mode_labels(self) -> None:
        # Radio-style marker so the selected mode is obvious (color + ●).
        self.field_button.setText(
            ("●" if self.field_button.isChecked() else "◯") + "  현장 간이 확인 (약 30초)"
        )
        self.thorough_button.setText(
            ("●" if self.thorough_button.isChecked() else "◯") + "  수령 후 정밀 검수 (약 1~2분)"
        )

    def _fill_device_detail(self) -> None:
        info = self.adapter.inspect(self.gpu_index)
        if not info:
            self.device_detail.setText("")
            return
        gpu = info.get("gpu", {})
        vram = gpu.get("memory.total")
        driver = gpu.get("driver_version")
        self.device_detail.setText(
            f"VRAM {vram or '—'} MiB · 드라이버 {driver or '—'}   "
            "(자세한 정보는 ‘GPU 정보’ 탭에서)"
        )

    def _thorough_spec(self) -> WorkloadSpec:
        return WorkloadSpec(
            dtype=self.dtype_combo.currentText(),
            size=self.size_spin.value(),
            measured_iterations=self.iter_spin.value(),
        )

    def _refresh_home(self) -> None:
        if not self.adapter.is_ready:
            self.device_label.setText("GPU collector를 찾을 수 없습니다. NVIDIA 드라이버를 확인하세요.")
            self.device_detail.setText("")
            self.start_button.setEnabled(False)
            return
        devices = self.adapter.list_devices()
        if not devices:
            self.device_label.setText("감지된 GPU가 없습니다.")
            self.device_detail.setText("")
            self.start_button.setEnabled(False)
            return
        device = devices[self.gpu_index]
        self.device_label.setText(f"GPU {device['index']} — {device['name']}")
        self.start_button.setEnabled(True)
        self._fill_device_detail()
        history = self.adapter.history(self.gpu_index)
        if history["record_count"]:
            latest = history["records"][-1]
            tflops = latest.get("achieved_tflops")
            shown = f"{tflops:.2f}" if isinstance(tflops, (int, float)) else "확인 불가"
            self.recent_label.setText(
                f"저장된 기준선 {history['record_count']}건 · 최근 achieved {shown} TFLOPS"
            )
        else:
            self.recent_label.setText("아직 검사 이력이 없습니다.")

    # ---- Progress -------------------------------------------------------
    def _build_progress(self) -> None:
        self.progress_page = _page("progress")
        root = QVBoxLayout(self.progress_page)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)
        root.addWidget(h1("GPU 검사 중"))
        self.stage_label = h2("사전 확인")
        root.addWidget(self.stage_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # busy indicator
        root.addWidget(self.progress_bar)
        self.elapsed_label = muted("경과 0.0초")
        root.addWidget(self.elapsed_label)

        sensors = Card()
        sensors.add(h2("현재 센서"))
        self.live_temp = QLabel("온도 —")
        self.live_power = QLabel("전력 —")
        self.live_clock = QLabel("graphics clock —")
        self.live_throttle = QLabel("throttle —")
        for widget in (self.live_temp, self.live_power, self.live_clock, self.live_throttle):
            sensors.add(widget)
        root.addWidget(sensors)
        root.addStretch(1)

        self.cancel_button = QPushButton("검사 취소")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.clicked.connect(self._cancel)
        root.addWidget(self.cancel_button)

        self._timer = QTimer(self)
        self._timer.setInterval(100)
        self._timer.timeout.connect(self._tick_elapsed)
        self.stack.addWidget(self.progress_page)

    def _tick_elapsed(self) -> None:
        self.elapsed_label.setText(f"경과 {self._elapsed.elapsed() / 1000:.1f}초")

    # ---- Result ---------------------------------------------------------
    def _build_result(self) -> None:
        self.result_page = _page("result")
        outer = QVBoxLayout(self.result_page)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("Page")
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(h1("검사 결과"))
        header.addStretch(1)
        self.verdict_badge = StatusBadge("")
        header.addWidget(self.verdict_badge)
        root.addLayout(header)

        # Friendly one-line summary.
        summary_card = Card()
        self.summary_label = QLabel("")
        self.summary_label.setObjectName("H2")
        self.summary_label.setWordWrap(True)
        summary_card.add(self.summary_label)
        root.addWidget(summary_card)

        # Performance — the headline the seller shows the buyer.
        perf_card = Card()
        perf_card.add(h2("성능"))
        self.spec_stat = BigStat("제조사 사양(이론 최대) 대비")
        perf_card.add(self.spec_stat)
        self.spec_gauge = RangeGauge()
        perf_card.add(self.spec_gauge)
        self.range_status = QLabel("")
        self.range_status.setWordWrap(True)
        perf_card.add(self.range_status)
        self.spec_note = muted("")
        perf_card.add(self.spec_note)
        self.vs_first_label = QLabel("")
        self.vs_first_label.setObjectName("H2")
        self.vs_first_label.setWordWrap(True)
        perf_card.add(self.vs_first_label)
        root.addWidget(perf_card)

        # Simple sensor status, each with a plain "what's normal" guide.
        status_card = Card()
        status_card.add(h2("검사 중 상태"))
        self.temp_label = QLabel("🌡️ 최고 온도 —")
        self.temp_label.setObjectName("H2")
        self.temp_guide = muted("")
        self.util_label = QLabel("⚡ GPU 사용률 —")
        self.util_label.setObjectName("H2")
        self.util_guide = muted("검사 중 GPU가 제대로 가동됐는지 보여줘요 — 높을수록 좋아요.")
        self.power_label = QLabel("🔌 전력 —")
        self.power_label.setObjectName("H2")
        self.power_guide = muted("")
        self.throttle_label = QLabel("🧊 쓰로틀링 —")
        self.throttle_label.setObjectName("H2")
        self.throttle_guide = muted("")
        for widget in (
            self.temp_label, self.temp_guide,
            self.util_label, self.util_guide,
            self.power_label, self.power_guide,
        ):
            status_card.add(widget)
        throttle_row = QHBoxLayout()
        throttle_row.addWidget(self.throttle_label)
        throttle_row.addWidget(InfoDot(THROTTLE_TOOLTIP))
        throttle_row.addStretch(1)
        status_card.layout().addLayout(throttle_row)
        status_card.add(self.throttle_guide)
        root.addWidget(status_card)

        # Why (diagnostics, already plain-Korean titles).
        reason_card = Card()
        reason_card.add(h2("확인된 점"))
        self.reason_label = muted("")
        reason_card.add(self.reason_label)
        root.addWidget(reason_card)

        # 혹사 점검 (참고) — observable indicators only, never a mining verdict.
        abuse_card = Card()
        abuse_card.add(h2("혹사 점검 (참고)"))
        self.abuse_note = muted("")
        abuse_card.add(self.abuse_note)
        self.abuse_box = QVBoxLayout()
        self.abuse_box.setSpacing(6)
        abuse_box_host = QWidget()
        abuse_box_host.setLayout(self.abuse_box)
        abuse_card.add(abuse_box_host)
        root.addWidget(abuse_card)

        # Collapsed technical detail for power users — truly hidden until opened.
        self.tech_group, tech_layout = collapsible("자세히 (기술 정보)")

        def tech_row(caption: str, tooltip: str | None = None) -> QLabel:
            row = QHBoxLayout()
            row.setSpacing(6)
            cap = QLabel(caption + ":")
            cap.setObjectName("Muted")
            value = QLabel("—")
            row.addWidget(cap)
            row.addWidget(value)
            if tooltip:
                row.addWidget(InfoDot(tooltip))
            row.addStretch(1)
            host = QWidget()
            host.setLayout(row)
            tech_layout.addWidget(host)
            return value

        self.tech_perf = tech_row("실제 연산 성능")
        self.tech_work = tech_row("작업")
        self.tech_timing = tech_row("시간 측정", TIMING_TOOLTIP)
        self.tech_reliability = tech_row("측정 상태")
        self.tech_protocol = tech_row("protocol", PROTOCOL_TOOLTIP)
        self.limits_label = muted("")
        tech_layout.addWidget(self.limits_label)
        root.addWidget(self.tech_group)

        # 서버 기록 · 진위 증명 공유
        share_card = Card()
        share_card.add(h2("결과 기록 · 공유 (진위 증명)"))
        share_card.add(
            muted(
                "측정을 서버에 기록하면 위조할 수 없는 검증 코드가 생겨요. "
                "이 코드를 상대에게 주면, 상대는 확인 링크에서 결과의 진위를 직접 검증할 수 있어요."
            )
        )
        self.upload_button = QPushButton("결과 서버에 기록하고 공유 코드 받기")
        self.upload_button.clicked.connect(self._upload_result)
        share_card.add(self.upload_button)

        # 업로드 성공 후에만 보이는 코드 영역.
        self.share_result = QWidget()
        share_box = QVBoxLayout(self.share_result)
        share_box.setContentsMargins(0, 8, 0, 0)
        share_box.setSpacing(4)
        share_box.addWidget(muted("검증 코드 (이 코드를 공유하세요)"))
        self.share_verify_label = QLabel("")
        self.share_verify_label.setObjectName("H1")
        self.share_verify_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        share_box.addWidget(self.share_verify_label)
        self.share_device_label = muted("")
        share_box.addWidget(self.share_device_label)
        self.share_link_label = QLabel("")
        self.share_link_label.setObjectName("Muted")
        self.share_link_label.setWordWrap(True)
        self.share_link_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        share_box.addWidget(self.share_link_label)
        self.copy_button = QPushButton("검증 코드 복사")
        self.copy_button.setObjectName("Secondary")
        self.copy_button.clicked.connect(self._copy_verify_code)
        share_box.addWidget(self.copy_button)
        self.share_result.setVisible(False)
        share_card.add(self.share_result)
        root.addWidget(share_card)

        root.addStretch(1)

        actions = QHBoxLayout()
        self.baseline_button = QPushButton("이 성능을 기준으로 저장")
        self.baseline_button.setObjectName("Secondary")
        self.baseline_button.clicked.connect(self._save_baseline)
        self.save_button = QPushButton("리포트 저장 (JSON)")
        self.save_button.clicked.connect(self._save_report)
        self.again_button = QPushButton("다시 검사")
        self.again_button.setObjectName("Secondary")
        self.again_button.clicked.connect(self._go_home)
        actions.addWidget(self.baseline_button)
        actions.addWidget(self.save_button)
        actions.addWidget(self.again_button)
        root.addLayout(actions)
        self.stack.addWidget(self.result_page)

    # ---- Run lifecycle --------------------------------------------------
    def _start(self, spec: WorkloadSpec) -> None:
        if not self.adapter.is_ready or self.adapter.service is None:
            return
        self._benchmarking = True
        self.stage_label.setText("사전 확인")
        for widget in (self.live_temp, self.live_power, self.live_clock, self.live_throttle):
            widget.setText(widget.text().split(" ")[0] + " —")
        self.stack.setCurrentWidget(self.progress_page)
        self._elapsed.restart()
        self._timer.start()

        self._worker = ValidationWorker(self.adapter.service, self.gpu_index, spec)
        self._worker.stage_changed.connect(lambda _key, label: self.stage_label.setText(label))
        self._worker.sensor_tick.connect(self._on_tick)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.start()

    def _on_tick(self, values: dict) -> None:
        def fmt(key: str, unit: str = "") -> str:
            value = values.get(key)
            return "—" if value is None else f"{value}{unit}"

        self.live_temp.setText(f"온도 {fmt('temperature_c', ' °C')}")
        self.live_power.setText(
            f"전력 {fmt('power_draw_w')} / {fmt('power_limit_w', ' W')}"
        )
        self.live_clock.setText(f"graphics clock {fmt('graphics_clock_mhz', ' MHz')}")
        self.live_throttle.setText(f"throttle {fmt('throttle_reasons_active')}")

    def _cancel(self) -> None:
        if self._worker is not None:
            self.cancel_button.setEnabled(False)
            self._worker.cancel()

    def _stop_timer(self) -> None:
        self._timer.stop()
        self.cancel_button.setEnabled(True)
        self._benchmarking = False

    def _on_completed(self, result, payload: dict) -> None:
        self._stop_timer()
        self._last_result = result
        self._last_payload = payload
        # Fold the benchmark's dense under-load samples into the cumulative log.
        if self._gpu_uuid:
            for sample in result.samples:
                self.adapter.record_usage(self._gpu_uuid, sample.values)
            self._refresh_usage_card()
        self.baseline_button.setEnabled(result.workload.reliability == "valid")
        self._show_result(result, payload)
        self.stack.setCurrentWidget(self.result_page)
        self._refresh_home()

    def _save_baseline(self) -> None:
        if self._last_result is None:
            return
        outcome = self.adapter.save_result_as_baseline(self._last_result)
        if outcome.get("saved"):
            self.baseline_button.setEnabled(False)
            self._update_vs_first(self._last_result)
            self._refresh_compare()
            QMessageBox.information(
                self, "기준 저장 완료", "이번 성능을 기준으로 저장했어요. ‘모델 비교’ 탭에서도 확인할 수 있어요."
            )
        else:
            QMessageBox.warning(self, "저장 안 됨", outcome.get("note", "저장하지 못했습니다."))

    def _on_failed(self, message: str) -> None:
        self._stop_timer()
        QMessageBox.critical(self, "검사 실패", message)
        self.stack.setCurrentWidget(self.home_page)

    def _on_cancelled(self) -> None:
        self._stop_timer()
        QMessageBox.information(self, "검사 취소", "검사가 취소되었습니다. 결과는 저장되지 않았습니다.")
        self.stack.setCurrentWidget(self.home_page)

    _SUMMARY = {
        "통과": "지금 검사에서는 성능과 상태 모두 특별한 문제가 보이지 않았어요.",
        "주의": "지금 검사에서 몇 가지 주의할 점이 보였어요. 아래 ‘확인된 점’을 확인하세요.",
        "판정 불가": "측정이 충분히 유효하지 않아 지금은 판단하기 어려워요. 다시 검사해 보세요.",
        "실패": "검사가 정상적으로 끝나지 않았어요. 드라이버나 환경을 확인해 주세요.",
    }

    def _show_result(self, result, payload: dict) -> None:
        # A fresh result invalidates any previously shown verify code.
        self._verify_code = ""
        self.share_result.setVisible(False)
        the_verdict = verdict(result)
        self.verdict_badge.set_status(the_verdict)
        self.summary_label.setText(self._SUMMARY.get(the_verdict, ""))

        # 사양(이론 최대) 대비 % + 정상 범위 게이지
        performance = payload.get("performance", {})
        peak_pct = performance.get("peak_utilization_pct")
        normal_range = performance.get("normal_range_pct")
        if performance.get("peak_utilization_status") == "ok" and peak_pct is not None:
            self.spec_stat.set_value(f"{peak_pct:.0f}%")
            peak = performance.get("theoretical_peak_tflops")
            if normal_range:
                low, high = normal_range
                self.spec_gauge.setVisible(True)
                self.spec_gauge.set_values(peak_pct, low, high)
                if performance.get("within_normal_range"):
                    self.range_status.setText(
                        f"✅ 이 검사에서 정상 GPU가 보통 내는 범위({low}~{high}%) 안이에요."
                    )
                    self.range_status.setStyleSheet("color:#3f8500; font-weight:600;")
                else:
                    self.range_status.setText(
                        f"⚠️ 이 검사의 정상 범위({low}~{high}%)보다 낮아요. 냉각·전원 상태나 재검사를 확인하세요."
                    )
                    self.range_status.setStyleSheet("color:#b25200; font-weight:600;")
            else:
                self.spec_gauge.setVisible(False)
                self.range_status.setText("")
            self.spec_note.setText(
                f"이 GPU 모델의 이론 최대({peak} TFLOPS)와 비교한 값이에요. "
                "이 검사 방식에서는 정상 GPU도 이론값보다 낮게 나오는 게 정상이에요."
            )
        else:
            self.spec_stat.set_value("비교 불가")
            self.spec_gauge.setVisible(False)
            self.range_status.setText("")
            self.spec_note.setText(
                "등록된 사양 정보가 없는 모델이라 사양 대비 %는 표시하지 않았어요."
            )

        # 처음 검사 대비 %
        self._update_vs_first(result)

        # 검사 중 상태 (쉬운 말 + 정상 기준)
        telemetry = result.telemetry_summary
        self._fill_temperature(telemetry)
        self.util_label.setText(
            f"⚡ GPU 사용률  최고 {self._stat(telemetry, 'gpu_utilization_pct', 'max', '%')}"
        )
        self._fill_power(telemetry)
        self._fill_throttle(result.samples)

        # 확인된 점 (진단)
        reasons = [
            f"• {f.title}\n   → {f.recommendation}"
            for f in result.findings
            if f.category != "none"
        ]
        self.reason_label.setText(
            "\n".join(reasons) if reasons else "특별히 주의할 점은 발견되지 않았어요."
        )

        # 혹사 점검 (참고)
        self._fill_abuse(result)

        # 자세히
        workload = result.workload
        tflops = workload.achieved_tflops
        self.tech_perf.setText(f"{tflops:.2f} TFLOPS" if tflops else "확인 불가")
        self.tech_work.setText(
            f"{workload.dtype} · {workload.shape['m']}×{workload.shape['k']} · {workload.measured_iterations}회"
        )
        self.tech_timing.setText(workload.timing_source)
        self.tech_reliability.setText(workload.reliability)
        self.tech_protocol.setText(result.protocol_id)
        self.limits_label.setText(
            "측정 한계:\n" + "\n".join(f"• {item}" for item in result.limitations)
        )

    @staticmethod
    def _stat(telemetry: dict, field: str, agg: str, unit: str) -> str:
        stats = telemetry.get(field)
        if not stats or stats.get(agg) is None:
            return "확인 불가"
        return f"{stats[agg]:.0f}{unit}"

    def _fill_temperature(self, telemetry: dict) -> None:
        stats = telemetry.get("temperature_c")
        peak = stats.get("max") if stats else None
        if peak is None:
            self.temp_label.setText("🌡️ 최고 온도  확인 불가")
            self.temp_guide.setText("")
            return
        self.temp_label.setText(f"🌡️ 최고 온도  {peak:.0f}°C")
        normal = LOAD_TEMPERATURE_NORMAL_MAX_C
        watch = LOAD_TEMPERATURE_THROTTLE_WATCH_C
        if peak < normal:
            msg, color = f"보통 부하 시 {normal}°C 이하가 정상이에요. 여유가 있어요.", "#3f8500"
        elif peak < watch:
            msg, color = f"보통 범위예요 ({normal}~{watch}°C). {watch}°C 이상이면 쓰로틀링 주의.", "#5e5e5e"
        else:
            msg, color = f"{watch}°C 이상이라 쓰로틀링이 생길 수 있어요. 냉각 상태를 확인하세요.", "#b25200"
        self.temp_guide.setText(msg)
        self.temp_guide.setStyleSheet(f"color:{color};")

    def _fill_power(self, telemetry: dict) -> None:
        draw = telemetry.get("power_draw_w")
        limit = telemetry.get("power_limit_w")
        draw_avg = draw.get("avg") if draw else None
        limit_val = limit.get("max") if limit else None
        if draw_avg is None:
            self.power_label.setText("🔌 전력  확인 불가")
            self.power_guide.setText("")
            return
        if limit_val:
            pct = draw_avg / limit_val * 100
            self.power_label.setText(f"🔌 전력  평균 {draw_avg:.0f}W / 한도 {limit_val:.0f}W ({pct:.0f}%)")
            self.power_guide.setText(
                "검사 중에는 전력을 많이 쓰는 게 정상이에요 — 한도에 가까울수록 GPU가 제대로 일한 거예요."
            )
        else:
            self.power_label.setText(f"🔌 전력  평균 {draw_avg:.0f}W")
            self.power_guide.setText("검사 중에는 전력을 많이 쓰는 게 정상이에요.")

    def _fill_throttle(self, samples) -> None:
        summary = summarize_throttle(samples)
        if not summary["supported"] or summary["total_samples"] == 0:
            self.throttle_label.setText("🧊 쓰로틀링  정보 미지원")
            self.throttle_guide.setText("이 드라이버에서는 쓰로틀링 상태를 제공하지 않아요.")
            return
        total = summary["total_samples"]
        throttled = summary["throttled_samples"]
        if throttled == 0:
            self.throttle_label.setText(f"🧊 쓰로틀링  없음 (측정 {total}회 모두 정상)")
            self.throttle_guide.setText("검사 내내 성능 제한이 관찰되지 않았어요.")
            self.throttle_guide.setStyleSheet("color:#3f8500;")
            return
        reasons = ", ".join(
            THROTTLE_LABELS.get(name, name) for name in summary["reasons"]
        )
        self.throttle_label.setText(f"🧊 쓰로틀링  측정 {total}회 중 {throttled}회 ({reasons})")
        # 전력 제한만이면 부하 중 흔한 정상 동작, 열 제한이면 주의.
        thermal = any("thermal" in name for name in summary["reasons"])
        if thermal:
            self.throttle_guide.setText("온도로 인한 성능 제한이 있었어요. 냉각 상태를 확인하세요.")
            self.throttle_guide.setStyleSheet("color:#b25200;")
        else:
            self.throttle_guide.setText("전력 제한 위주예요 — 고부하에서는 흔한 정상 동작일 수 있어요.")
            self.throttle_guide.setStyleSheet("color:#5e5e5e;")

    _ABUSE_ICON = {"ok": "✅", "watch": "⚠️", "info": "ℹ️"}

    def _fill_abuse(self, result) -> None:
        report = self.adapter.abuse_check(result)
        self.abuse_note.setText(report.get("note", ""))

        # Clear any previous rows.
        while self.abuse_box.count():
            item = self.abuse_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        indicators = report.get("indicators", [])
        if not indicators:
            self.abuse_box.addWidget(muted("표시할 참고 지표가 없어요."))
            return
        for item in indicators:
            icon = self._ABUSE_ICON.get(item.get("status"), "•")
            row = QHBoxLayout()
            title = QLabel(f"{icon} {item['label']}: {item['value']}")
            title.setObjectName("H2")
            row.addWidget(title)
            if item.get("tooltip"):
                row.addWidget(InfoDot(item["tooltip"]))
            row.addStretch(1)
            row_host = QWidget()
            row_host.setLayout(row)
            self.abuse_box.addWidget(row_host)
            self.abuse_box.addWidget(muted(f"   {item['detail']}"))

    def _update_vs_first(self, result) -> None:
        from ...baseline import percent_vs_first

        history = self.adapter.history(self.gpu_index)
        comparison = percent_vs_first(
            history.get("records", []),
            protocol_id=result.protocol_id,
            dtype=result.workload.dtype,
            shape=result.workload.shape,
            achieved_tflops=result.workload.achieved_tflops,
        )
        if comparison["available"]:
            self.vs_first_label.setText(
                f"처음 검사({comparison['first_date']}) 대비  {comparison['percent']}%"
            )
        else:
            self.vs_first_label.setText(
                "처음 검사 기록이 없어요. 아래 ‘이 성능을 기준으로 저장’을 누르면 "
                "다음 검사 때 지금과 비교할 수 있어요."
            )

    def _save_report(self) -> None:
        if self._last_result is None or self._last_payload is None:
            return
        default = str(Path.home() / "gpu-check-report.json")
        path, _ = QFileDialog.getSaveFileName(self, "리포트 저장", default, "JSON (*.json)")
        if not path:
            return
        document = {
            "validation": redact_sensitive_data(self._last_payload),
            "shared_report": self.adapter.service.shared_report(self._last_result),
        }
        Path(path).write_text(
            json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        QMessageBox.information(self, "저장 완료", f"리포트를 저장했습니다:\n{path}")

    # ---- Server record / provenance sharing -----------------------------
    def _upload_result(self) -> None:
        session = getattr(self, "auth_session", None)
        if session is None or not getattr(session, "authenticated", False):
            QMessageBox.information(
                self,
                "로그인 필요",
                "결과를 서버에 기록하려면 로그인하세요.\n창 우측 하단에서 로그인할 수 있어요.",
            )
            return
        result = self._last_result
        payload = self._last_payload
        if result is None or payload is None:
            return
        workload = result.workload
        if not workload.achieved_tflops or workload.reliability != "valid":
            QMessageBox.warning(
                self,
                "기록 불가",
                "유효한(valid) 측정만 서버에 기록할 수 있어요. 재검사 후 다시 시도하세요.",
            )
            return
        if not self._gpu_uuid:
            QMessageBox.warning(
                self,
                "기록 불가",
                "GPU 식별자(UUID)를 확인할 수 없어 기기를 등록할 수 없어요.",
            )
            return

        # The raw UUID never leaves this machine — only its hash is sent.
        fingerprint = hashlib.sha256(self._gpu_uuid.encode("utf-8")).hexdigest()
        gpu_name = self._gpu_name or (workload.device_name or "")
        performance = result.performance or {}
        submission = {
            "device_public_code": None,  # filled in after device registration
            "gpu_name": gpu_name,
            "protocol_id": result.protocol_id,
            "achieved_tflops": workload.achieved_tflops,
            "dtype": workload.dtype,
            "matrix_size": workload.shape.get("m"),
            "peak_tflops": performance.get("theoretical_peak_tflops"),
            "peak_utilization_pct": performance.get("peak_utilization_pct"),
            "reliability": workload.reliability,
            "driver_version": result.device.get("driver_version"),
            "torch_version": result.environment.get("torch_version"),
            "cuda_version": result.environment.get("cuda_version"),
            "timing_source": workload.timing_source,
            "telemetry_summary": result.telemetry_summary,
            "raw": redact_sensitive_data(payload),
        }

        self.upload_button.setEnabled(False)
        self.upload_button.setText("기록 중…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            device = session.client.register_device(
                session.token, fingerprint, gpu_name
            )
            submission["device_public_code"] = device["public_code"]
            response = session.client.submit_measurement(session.token, submission)
        except ApiError as error:
            QMessageBox.warning(self, "기록 실패", str(error))
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.upload_button.setEnabled(True)
            self.upload_button.setText("결과 서버에 기록하고 공유 코드 받기")

        self._verify_code = response.get("verify_code", "")
        base = session.client.base_url
        share_url = response.get("share_url", f"/api/verify/{self._verify_code}")
        self.share_verify_label.setText(self._verify_code)
        self.share_device_label.setText(f"기기 코드: {device['public_code']}")
        self.share_link_label.setText(f"확인 링크: {base}{share_url}")
        self.share_result.setVisible(True)

    def _copy_verify_code(self) -> None:
        if not self._verify_code:
            return
        QApplication.clipboard().setText(self._verify_code)
        QMessageBox.information(
            self, "복사됨", f"검증 코드 {self._verify_code} 를 클립보드에 복사했어요."
        )

    def _go_home(self) -> None:
        self._refresh_home()
        self.stack.setCurrentWidget(self.home_page)
