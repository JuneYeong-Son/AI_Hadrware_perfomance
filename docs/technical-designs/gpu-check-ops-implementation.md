# GPU Check / GPU Ops 구현 노트

이 문서는 [development-brief-0713.md](development-brief-0713.md)의 P0 범위를 실제로 구현한 결과를 정리한다. 브리프가 "무엇을/왜"라면, 이 문서는 "어떻게 만들었고 어디에 있는가"를 설명한다.

## 1. 무엇을 만들었나

- **공통 측정 코어(P0)**: 센서 수집과 실제 GPU 연산 측정을 분리하고, 진단·기준선·리포트를 생성하는 엔진.
- **GPU Check (개인 구매자용 데스크톱 앱)**: PySide6 기반. 단일 GPU 검사 → 판정·근거 → 리포트.
- **GPU Ops (운영자용 데스크톱 앱)**: 장비 표·검사 작업·기준선 이력.
- **CLI**: 기존 `health/list/inspect/snapshot/report`에 `validate/baseline/history/overview`를 추가.

실제 NVIDIA GPU(RTX 3060 Ti)에서 통제된 GEMM workload가 GPU event 기준으로 측정됨을 확인했다. GPU가 없는 CI 환경에서도 fake collector/runner로 전체 파이프라인이 테스트된다.

## 2. 아키텍처

브리프 §4.3의 컴포넌트 분리를 그대로 따른다. 모든 신규 기능은 `GpuMeasurementService`를 통해 CLI·데스크톱·향후 Web/LLM이 공유한다.

```
GpuCollector        장치 식별, 정적 정보, 센서/환경 수집 (nvidia-smi)      collector.py
GpuWorkloadRunner   통제된 GPU 연산 실행 + GPU event 기준 시간 측정        workload.py
MeasurementOrchestrator  사전확인·워밍업·연산·센서 샘플링·결합·진행/취소     orchestrator.py
DiagnosticEngine    센서+측정 근거로 이상 징후 분류 (규칙 기반)            diagnostics.py
ReportBuilder       JSON 및 사람이 읽는 리포트(내부/외부) 생성            report_builder.py
BaselineStore       기준선 저장, 이력, 모델 비교                          baseline.py
UsageMonitor        누적 쓰로틀/온도 관찰, 혹사 참고 지표                  usage_monitor.py
GpuMeasurementService  애플리케이션 경계 (모든 어댑터의 진입점)            service.py
```

데스크톱은 `application/gpu_measurer/desktop/` 아래 `shared / buyer / operator`로 분리한다. 프론트엔드는 collector를 직접 호출하지 않고, 실제 workload는 `QThread` worker에서 실행해 UI를 멈추지 않으며 취소 가능하다.

## 3. 측정과 지표의 정의 (정직성 규칙)

혼동을 막기 위해 세 값을 엄격히 구분한다.

- **achieved TFLOPS**: 통제된 GEMM을 실제 실행해 측정한 유효 성능. `operation_count / elapsed_seconds / 1e12`. multiply-add를 2 연산으로 계산하며, FP32는 TF32를 꺼서 진짜 FP32를 측정한다.
- **theoretical peak**: 제조사 사양상 이론 최대. `gpu_reference.py`에 **출처가 명확한 주요 GPU의 FP32 값만** 수동 등록(NVIDIA/TechPowerUp). 표에 없는 모델·비FP32·무효 측정은 값을 **지어내지 않고** `not_comparable`로 둔다.
- **사양 대비 %(peak_utilization)**: `achieved / theoretical_peak × 100`. 이론 최대는 튜닝 안 한 GEMM이 도달하기 어려운 천장이므로, "이 검사 정상 범위(FP32 GEMM 40~70%)"를 함께 표시해 낮은 값이 결함으로 오해되지 않게 한다.

측정 신뢰성은 `valid / inconclusive / failed`로 구분하고, GPU 점유율이 낮거나 측정 시간이 너무 짧으면 `inconclusive`로 강등한다.

## 4. 진단과 쓰로틀 해석

`DiagnosticEngine`은 "느리다"만 표시하지 않고 근거·심각도·confidence·권장 조치를 함께 낸다(thermal/power/cooling/workload/driver). 특히 쓰로틀은 **보호 동작**이며, 원인을 구분해 표시한다.

- **전력 제한(sw_power_cap)**: 고부하에서 전력 한도를 지키는 정상 동작. 걱정 대상 아님.
- **열 쓰로틀(hw/sw_thermal)**: GPU 발열이 심하다는 신호. 추적·확인이 필요한 요인.

UI는 이 구분을 ⓘ 툴팁으로 설명하고, 누적 기록에서도 열 쓰로틀을 별도로 집계한다.

## 5. 기준선·비교·누적 관찰

- **기준선(baseline)**: 유효한 측정만 저장. GPU identity·protocol·dtype·shape·driver가 모두 같고 둘 다 valid일 때만 delta를 계산한다(브리프 §6). 조건이 다르면 "비교 불가".
- **처음 검사 대비 %**: 같은 protocol의 첫 기준선과 현재를 비교. 기록이 없으면 지어내지 않고 "첫 검사" 안내 + 저장 유도.
- **모델 비교**: 저장된 결과를 **같은 protocol끼리만** 모아 achieved TFLOPS와 1회 실행시간(elapsed/iterations)으로 정렬. 서로 다른 검사를 섞거나 종합 점수·가격·가치 순위는 매기지 않는다(브리프 §7).
- **누적 쓰로틀/온도(UsageMonitor)**: 앱이 켜져 있는 동안 관찰한 값을 GPU별로 누적 저장. "GPU 제조 이후 전체 이력"은 nvidia-smi가 제공하지 않으므로 **"이 앱 관찰 이후"**로 정직하게 표기한다.
- **혹사 점검(참고)**: 센서로 채굴 이력·사용 기간을 단정할 수 없음을 명시하고(브리프 §7/§12), 관찰 가능한 지표(발열, 부스트 클럭 유지, 사양 대비 %, 누적 쓰로틀)만 참고로 제공한다. 판정이 아니다.

## 6. 실행 방법

```bash
# 데스크톱 앱
python gpu_check.py     # GPU Check (개인 구매자)
python gpu_ops.py       # GPU Ops (운영자)

# CLI
python main.py                 # 콘솔 개요
python main.py --validate      # 통제된 GPU workload 실행 및 진단
python main.py --baseline      # 유효 결과를 기준선으로 저장
python main.py --history       # 저장된 측정 이력
python main.py --ui            # 개발용 Tkinter (fallback)
```

의존성: 코어 CLI는 표준 라이브러리만으로 동작. 데스크톱은 `PySide6`, 실제 GPU 측정은 CUDA 빌드 `torch`가 필요(`application/requirements.txt` 참고). torch가 없으면 achieved TFLOPS를 측정하지 않고 그 사실을 명시한다.

## 7. 데이터 계약

`schema_version: 1.0` 응답 봉투와 개인정보 마스킹(UUID·hostname)을 유지한다. validation 응답은 다음 영역을 포함한다.

```
device · environment · workload · performance · telemetry_summary ·
findings · baseline · limitations · protocol_id · samples
```

`limitations`는 필수이며, 측정하지 않은 항목·비교 불가 사유·지원되지 않는 센서를 명시한다. 사양 대비 %를 실제로 계산한 경우에는 "계산하지 않았다"는 문구를 넣지 않는다(모순 방지).

## 8. 테스트

- fake collector / fake workload runner로 GPU 없이 전체 파이프라인 검증.
- 데스크톱은 `QT_QPA_PLATFORM=offscreen` 헤드리스 스모크 테스트로 창 생성·어댑터 연동 확인.

```bash
cd application
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -p "test_*.py"
```

실제 GPU에서의 achieved TFLOPS 정확성은 자동화 테스트가 보증하지 않으며, 수동 검증으로 별도 확인한다.

## 9. 이번 범위에서 하지 않은 것 (브리프 §7 준수)

- CPU 병목 자동 판정
- 서로 다른 GPU의 단일 종합 점수·가격·가치 순위
- 실제 모델 adapter 없는 MFU 표기
- 센서만으로 채굴 이력·사용 기간·물리 결함 단정
