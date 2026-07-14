"""GPU Ops — repeated checks and history for AI server operators.

Status-first (not spec-first) operational screen: summary tiles, a scannable
device table, an inline progress/cancel bar for long checks, and a per-device
history detail with a delta only when the protocol matches. No cross-device
ranking — status and evidence only (brief §9.2–§9.3).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...models import WorkloadSpec
from ...report_builder import verdict
from ..shared.service_adapter import UiServiceAdapter
from ..shared.theme import APP_STYLESHEET, status_style
from ..shared.widgets import BigStat, Card, StatusBadge, h1, h2, muted
from ..shared.worker import ValidationWorker

TABLE_COLUMNS = ["GPU", "모델", "마지막 검사", "상태", "achieved TFLOPS", "진단 요약", "기준선"]


class DeviceRow:
    def __init__(self, index: int, name: str):
        self.index = index
        self.name = name
        self.status = "검사 필요"
        self.last_check = "—"
        self.tflops = "미측정"
        self.diagnosis = "—"
        self.baseline = "기준선 없음"


class GpuOpsWindow(QMainWindow):
    def __init__(self, adapter: UiServiceAdapter | None = None):
        super().__init__()
        self.adapter = adapter or UiServiceAdapter.create()
        self._worker: ValidationWorker | None = None
        self._rows: list[DeviceRow] = []
        self._running = False

        self.setWindowTitle("GPU Ops — AI 서버 운영 검사")
        self.setStyleSheet(APP_STYLESHEET)
        self.resize(940, 660)

        central = QWidget()
        central.setObjectName("Page")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        root.addWidget(h1("GPU Ops · 운영 현황"))
        self._build_tiles(root)
        self._build_table(root)
        self._build_detail(root)
        self._build_action_bar(root)

        self.refresh()

    # ---- Summary tiles --------------------------------------------------
    def _build_tiles(self, root: QVBoxLayout) -> None:
        row = QHBoxLayout()
        self.tile_need = BigStat("검사 필요")
        self.tile_warn = BigStat("주의 필요")
        self.tile_running = BigStat("검사 진행 중")
        self.tile_recent = BigStat("최근 검사")
        for tile in (self.tile_need, self.tile_warn, self.tile_running, self.tile_recent):
            card = Card()
            card.add(tile)
            row.addWidget(card)
        root.addLayout(row)

    # ---- Device table ---------------------------------------------------
    def _build_table(self, root: QVBoxLayout) -> None:
        self.table = QTableWidget(0, len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.itemSelectionChanged.connect(self._update_detail)
        root.addWidget(self.table, 1)

    # ---- Detail / history ----------------------------------------------
    def _build_detail(self, root: QVBoxLayout) -> None:
        card = Card()
        header = QHBoxLayout()
        header.addWidget(h2("장비 상세 · 이력"))
        header.addStretch(1)
        self.detail_badge = StatusBadge("")
        header.addWidget(self.detail_badge)
        card.layout().addLayout(header)
        self.detail_label = muted("장비를 선택하세요.")
        card.add(self.detail_label)
        root.addWidget(card)

    # ---- Action bar -----------------------------------------------------
    def _build_action_bar(self, root: QVBoxLayout) -> None:
        bar = QHBoxLayout()
        self.run_button = QPushButton("선택 장비 검사 실행 (기준선 저장)")
        self.run_button.clicked.connect(self._run_selected)
        self.cancel_button = QPushButton("취소")
        self.cancel_button.setObjectName("Danger")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.setEnabled(False)
        self.stage_label = muted("")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setMaximumWidth(220)
        bar.addWidget(self.run_button)
        bar.addWidget(self.cancel_button)
        bar.addWidget(self.stage_label, 1)
        bar.addWidget(self.progress_bar)
        root.addLayout(bar)

    # ---- Data -----------------------------------------------------------
    def _compute_rows(self) -> list[DeviceRow]:
        rows: list[DeviceRow] = []
        for device in self.adapter.list_devices():
            row = DeviceRow(device["index"], device["name"])
            history = self.adapter.history(device["index"])
            if history["record_count"]:
                latest = history["records"][-1]
                tflops = latest.get("achieved_tflops")
                row.tflops = f"{tflops:.2f}" if isinstance(tflops, (int, float)) else "확인 불가"
                row.last_check = (latest.get("created_at") or "—").replace("T", " ")[:19]
                row.baseline = f"{history['record_count']}건"
                findings = latest.get("findings", [])
                severities = {f.get("severity") for f in findings}
                if severities & {"warning", "critical"}:
                    row.status = "주의"
                    titles = [f["title"] for f in findings if f.get("severity") in {"warning", "critical"}]
                    row.diagnosis = titles[0] if titles else "주의"
                else:
                    row.status = "통과"
                    row.diagnosis = "이상 없음"
            rows.append(row)
        return rows

    def refresh(self) -> None:
        if not self.adapter.is_ready:
            self.table.setRowCount(0)
            self.detail_label.setText(
                self.adapter.error or "GPU collector를 찾을 수 없습니다."
            )
            self.run_button.setEnabled(False)
            return
        self._rows = self._compute_rows()
        self._fill_table()
        self._fill_tiles()
        if self._rows and not self.table.selectedItems():
            self.table.selectRow(0)

    def _fill_table(self) -> None:
        self.table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            values = [
                str(row.index),
                row.name,
                row.last_check,
                row.status,
                row.tflops,
                row.diagnosis,
                row.baseline,
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c == 3:  # status column: tint by status
                    _label, fg, bg = status_style(row.status)
                    item.setForeground(Qt.GlobalColor.black)
                    from PySide6.QtGui import QColor

                    item.setBackground(QColor(bg))
                self.table.setItem(r, c, item)

    def _fill_tiles(self) -> None:
        need = sum(1 for row in self._rows if row.status == "검사 필요")
        warn = sum(1 for row in self._rows if row.status == "주의")
        checks = [row.last_check for row in self._rows if row.last_check != "—"]
        self.tile_need.set_value(str(need))
        self.tile_warn.set_value(str(warn))
        self.tile_running.set_value("1" if self._running else "0")
        self.tile_recent.set_value(max(checks)[5:16] if checks else "없음")

    def _selected_index(self) -> int | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        return self._rows[rows[0].row()].index

    def _update_detail(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        row = next((r for r in self._rows if r.index == idx), None)
        if row is None:
            return
        self.detail_badge.set_status(row.status)
        history = self.adapter.history(idx)
        lines = [f"GPU {row.index} — {row.name}", f"기준선 {row.baseline} · 마지막 검사 {row.last_check}"]
        comparison = history.get("comparison", {})
        if comparison.get("comparable") and comparison.get("delta"):
            delta = comparison["delta"]
            lines.append(
                f"최근 변화: {delta['relative_pct']:+.2f}% "
                f"({delta['previous_tflops']} → {delta['latest_tflops']} TFLOPS, 같은 protocol)"
            )
        elif history["record_count"]:
            reason = comparison.get("reason") or "비교 기준이 부족합니다."
            lines.append(f"비교: {reason}")
        else:
            lines.append("아직 비교 가능한 기준선이 없습니다. 검사를 실행해 기준선을 저장하세요.")
        if history["record_count"]:
            latest = history["records"][-1]
            for finding in latest.get("findings", []):
                lines.append(f"• {finding['title']} ({finding['severity']}/{finding['confidence']})")
        self.detail_label.setText("\n".join(lines))

    # ---- Run ------------------------------------------------------------
    def _run_selected(self) -> None:
        idx = self._selected_index()
        if idx is None or self.adapter.service is None or self._running:
            return
        self._running = True
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.tile_running.set_value("1")

        self._worker = ValidationWorker(
            self.adapter.service, idx, WorkloadSpec(), save_baseline=True
        )
        self._worker.stage_changed.connect(lambda _k, label: self.stage_label.setText(f"GPU {idx} · {label}"))
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        self._worker.start()

    def _cancel(self) -> None:
        if self._worker is not None:
            self.cancel_button.setEnabled(False)
            self._worker.cancel()

    def _end_run(self) -> None:
        self._running = False
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setVisible(False)
        self.stage_label.setText("")

    def _on_completed(self, result, payload: dict) -> None:
        self._end_run()
        saved = payload.get("baseline_saved")
        note = "기준선으로 저장됨" if saved else payload.get("baseline_note", "저장되지 않음")
        self.refresh()
        QMessageBox.information(
            self,
            "검사 완료",
            f"판정 {verdict(result)} · {note}",
        )

    def _on_failed(self, message: str) -> None:
        self._end_run()
        self.refresh()
        QMessageBox.critical(self, "검사 실패", message)

    def _on_cancelled(self) -> None:
        self._end_run()
        self.refresh()
        QMessageBox.information(self, "검사 취소", "검사가 취소되었습니다. 결과는 저장되지 않았습니다.")
