# AI Hardware Performance

## 개발 협업 브리프

이 문서는 AI 코딩 에이전트 또는 개발 협업자가 프로젝트의 목적, 우선순위, 측정 범위, 기술적 제약을 빠르게 이해하기 위한 기준 문서다.

이 문서를 읽은 뒤에는 새로운 기능을 넓게 제안하기보다 현재 저장소를 먼저 확인하고, 아래의 P0 범위 안에서 작동하는 구현과 테스트를 만들어야 한다.

---

## 1. 제품 한 문장

**GPU의 현재 상태, 실제 연산 성능, 쓰로틀링 원인, 측정 이력을 근거와 함께 설명하는 공통 측정 엔진 위에, 개인 구매자용 앱과 AI 서버 운영자용 앱을 각각 제공한다.**

이 제품은 단순히 GPU 센서 값을 보여주는 모니터가 아니다. GPU를 구매하거나 운영할 때 다음 질문에 답하는 것이 목적이다.

- 이 GPU가 실제로 연산을 수행하고 있는가?
- 제조사 사양의 이론 성능과 비교해 현재 성능은 어느 정도인가?
- 성능이 낮다면 GPU 자체의 문제인가, 온도와 전력 제한 때문인가?
- 지금 측정한 결과를 다음 달 또는 1년 뒤의 기준으로 사용할 수 있는가?
- 다른 장비와의 상대적 가치와 가격을 판단할 수 있을 만큼 신뢰할 수 있는 데이터가 쌓였는가?

---

## 2. 두 제품으로 분기하는 고객 전략

개인 중고 GPU 구매자와 AI 서버 운영 사업자는 같은 센서와 benchmark를 필요로 하지만, 돈을 지불하는 순간과 원하는 결과가 다르다. 하나의 화면에 두 요구를 모두 넣으면 개인에게는 복잡하고, 운영 사업자에게는 얕아진다.

따라서 제품은 다음 두 앱으로 나눈다.

```text
공통 GPU Measurement Core
  ├─ GPU Check       개인 중고 GPU 구매자용 앱
  └─ GPU Ops         AI 서버 운영 사업자용 앱
```

두 앱은 측정 엔진, 수집기, workload runner, 진단 규칙, JSON schema를 공유한다. 그러나 사용자의 작업 흐름, 화면, 저장 이력, 리포트 문구, 과금 단위는 분리한다. 두 개의 독립된 코드베이스를 복제하지 않는다.

### 2.1 고객의 결정이 어떻게 다른가

| 구분 | GPU Check: 개인 구매자 | GPU Ops: AI 서버 운영 사업자 |
|---|---|---|
| 핵심 질문 | 사기 전에 확인할 수 있는가? 받은 기기가 설명과 일치하는가? | 이 장비를 계속 운영해도 되는가? |
| 사용 시점 | 구매 전 현장 확인 및 수령 직후·반품 기간 내 검수 | 매일, 주기적 검사, 장애 발생 시 |
| 장비 수 | 보통 1대 또는 소수 | 여러 서버와 여러 GPU |
| 가장 중요한 결과 | 구매·반품 판단과 결함 의심 근거 | 성능 저하, 쓰로틀링, 운영 장애 원인 |
| 사용자의 기술 수준 | 다양함. 비전문 사용자도 포함 | 인프라 담당자 또는 기술 대표 |
| 리포트 목적 | 판매자에게 보여주거나 구매 기록으로 보관 | 내부 조치, 고객 설명, 장애 보고 |
| 저장 방식 | 로컬 파일, 공유 가능한 결과 | 장기 이력, 장비별 history, 운영 기록 |
| 초기 과금 방향 | 1회 검사 또는 유료 리포트 | 장비 수 또는 GPU 수 기준 구독 |

### 2.2 GPU Check: 개인 중고 GPU 구매자용 앱

#### 고객 페르소나

중고 RTX 3090, 4090, A5000 등 GPU를 구매해 AI 개발이나 로컬 inference에 사용하려는 개인이다. 판매자의 설명과 사진만으로는 GPU의 실제 상태를 알기 어렵다. 판매자 PC에서 구매 전 간단히 확인할 수도 있지만, 실제 핵심 검수는 기기를 받은 뒤 반품 기간 안에 수행한다.

이 사용자는 CUDA, VBIOS, throttle reason의 의미를 모를 수 있다. 따라서 원시 값보다 “거래를 진행해도 되는지, 받은 기기가 설명과 일치하는지, 반품 근거가 있는지”를 알려주는 결론과 근거가 중요하다.

#### 핵심 기능

1. **빠른 장치 확인**
   - 실제 GPU 모델, VRAM, 드라이버, VBIOS, PCIe 상태 확인
   - 표시된 모델과 실제 수집 정보가 일치하는지 확인
   - 지원되지 않는 값은 `확인 불가`로 표시

2. **구매 전·후 검사 마법사**
   - `현장 간이 확인`과 `수령 후 정밀 검수` 모드 선택
   - 현장 모드: 장치 식별, VRAM, 드라이버, 짧은 workload, 기본 센서 확인
   - 수령 후 모드: 권장 workload, warmup, thermal 구간, 센서 수집을 포함한 정밀 검사
   - 검사 대상과 검사 시간을 사용자가 선택
   - 사용자가 이해할 수 있는 단계별 진행 상태 제공

3. **거래·수령 검수 결과**
   - `검사 통과`, `주의 필요`, `판정 불가`, `검사 실패`
   - achieved TFLOPS
   - 최고 온도, 평균 온도, 전력, graphics clock
   - 쓰로틀링 또는 오류 관찰 여부
   - “왜 주의인지”와 “판매 설명과 다른 점이 있는지”를 짧은 문장으로 설명

4. **거래·반품 증거 리포트**
   - 검사 시각, 검사 모드, 검사 조건
   - 장치 정보
   - 실제 측정 성능
   - 관찰된 센서 상태와 진단 근거
   - 측정 한계와 개인정보 마스킹
   - 판매자 문의, 반품 요청, 개인 보관에 사용할 수 있는 JSON 및 PDF 리포트

5. **거래와 반품 기간 기록**
   - 판매자, 구매일, 수령일, 반품 마감일, asking price, 실제 구매가를 사용자가 직접 입력
   - `구매 전 확인`, `수령 후 검수 대기`, `검수 완료`, `반품 검토`, `보관` 상태 관리
   - 최초 검사 결과와 수령 후 정밀 검사 결과를 하나의 거래 기록에 연결
   - 자동 시장 가격이나 서로 다른 GPU의 상대 가치는 아직 계산하지 않음

#### GPU Check에 넣지 않는 것

- 다중 GPU fleet 화면
- daemon 방식의 상시 모니터링
- 복잡한 alert rule 편집
- 전체 장비 순위
- CPU 병목 분석
- GPU 모델 간 자동 매입가 산정

개인용 앱의 핵심은 “많은 정보를 보여주는 것”이 아니라 **구매 전 확인과 수령 후 검수를 연결해, 거래 위험과 반품 분쟁을 줄이고 판단을 증거로 남기는 것**이다.

### 2.3 GPU Ops: AI 서버 운영 사업자용 앱

#### 고객 페르소나

중고 여부와 관계없이 NVIDIA GPU 서버를 여러 대 운영하는 소규모 AI 인프라 사업자의 대표 또는 인프라 책임자다. 고객에게 GPU 서버 또는 연산 서비스를 제공하고, 장비 한 대의 성능 저하가 곧 처리량 저하, 장애, 환불, 신뢰 하락으로 이어진다.

이 사용자는 이미 `nvidia-smi`나 기존 모니터링 도구를 사용할 수 있다. 필요한 것은 센서 화면이 아니라, 장비별 성능 변화와 원인을 운영 의사결정으로 연결하는 것이다.

#### 핵심 기능

1. **장비 인벤토리와 운영 현황**
   - 서버, GPU, 위치, 담당자, 용도 태그
   - GPU별 마지막 검사, 현재 상태, 최근 진단
   - 검사 필요, 주의, 측정 실패 장비의 작업 목록

2. **반복 검사와 기준선**
   - 신규 장비 도입 시 기준선 생성
   - 주기적 workload 측정
   - 장비별 protocol, dtype, driver, runtime 기록
   - 동일 장비의 과거 결과와 현재 결과 연결
   - 충분히 동일한 조건일 때만 성능 delta 제공

3. **운영 중 원인 추적**
   - thermal throttling, power limit, clock drop, cooling issue 의심
   - GPU utilization이 낮은 구간과 workload 유효성 표시
   - XID, ECC 등 지원 가능한 오류 기록
   - 한 번의 상태보다 시간에 따른 반복 이벤트를 우선

4. **AI workload 성능 측정**
   - 통제된 GPU workload의 achieved TFLOPS
   - dtype과 workload별 peak utilization
   - 실제 모델 adapter가 추가된 후에만 모델별 throughput과 MFU
   - 모델명, batch, sequence length, precision, FLOPs 산정 기준 기록

5. **운영 리포트와 장애 보고**
   - 장비별 성능 이력
   - 장애 전후 온도, 전력, 클럭, workload 상태
   - “47번 노드가 느린 이유”에 대한 관찰 근거
   - 내부 운영용 상세 리포트
   - 고객에게 제공할 수 있는 제한된 공유 리포트

6. **운영 자동화의 기반**
   - 백그라운드 검사 작업
   - 향후 일정 기반 검사와 알림
   - JSON export와 LLM 도구 연결
   - 여러 장비의 상태를 보여주되, 초기에는 종합 점수나 순위를 제공하지 않음

#### GPU Ops에 넣지 않는 것

- 개인 구매자를 위한 복잡한 가격 입력 중심 흐름
- 판매자에게 보여주기 위한 단일 검사 마법사만 제공
- CPU 병목의 자동 원인 확정
- 실제 데이터가 쌓이기 전 장비 간 상대 가치 점수
- 서로 다른 workload를 하나의 순위로 합산

GPU Ops의 핵심은 **GPU가 지금 작동하는지보다, 언제부터 어떤 근거로 성능이 변했는지 운영자가 설명할 수 있게 하는 것**이다.

### 2.4 분기 전략의 핵심

두 앱은 기능 목록만 다른 것이 아니라 성공 기준이 다르다.

```text
GPU Check 성공
  사용자가 수령한 GPU의 상태를 이해하고 구매 유지 또는 반품 결정을 내림
  구매 전에는 짧은 현장 확인 결과를 거래 판단에 활용함
  판매자와 공유할 수 있는 객관적 리포트가 생성됨

GPU Ops 성공
  운영자가 느린 장비와 검사 필요 장비를 바로 찾음
  성능 변화와 원인을 이력으로 설명함
  장애 보고와 고객 설명에 같은 측정 데이터를 재사용함
```

개발은 공통 코어를 먼저 만들고, 제품 경험은 두 앱으로 분리한다. 초기 시장 검증은 설치와 사용이 쉬운 `GPU Check`로 빠르게 진행하고, 반복 사용과 구독성이 있는 `GPU Ops`를 같은 측정 데이터 위에 확장한다. 두 앱의 화면을 하나의 거대한 모드 선택 앱으로 만들지 않는다.

---

## 3. 현재 저장소의 출발점

현재 프로젝트에는 다음 기반이 있다.

- `application/gpu_measurer/collector.py`
  - `GpuCollector` 프로토콜
  - NVIDIA `nvidia-smi` 기반 장치 정보와 센서 수집
  - `NvidiaCollector` 구현
- `application/gpu_measurer/service.py`
  - 장치 조회, 정적 정보 조회, 현재 스냅샷, 시간 측정 서비스
- `application/gpu_measurer/models.py`
  - `GpuDevice`, `SensorSnapshot`, `BenchmarkMatch`, `MeasurementResult`
- `application/gpu_measurer/reporting.py`
  - 센서 샘플의 최소값, 평균값, 최대값 계산
  - 로컬 실행 리포트 저장
- `application/gpu_measurer/serialization.py`
  - `schema_version: 1.0` 응답 봉투
  - UUID와 호스트명 마스킹
- `data/static/benchmarks/`
  - PassMark 및 Compute API 정적 비교 데이터
- `application/main.py`
  - `health`, `list`, `inspect`, `snapshot`, `report` JSON CLI

현재 `report`는 실제 GPU 연산 벤치마크가 아니다. 일정 시간 동안 센서를 샘플링하고 요약하는 기능이다. 정적 벤치마크 CSV도 현재 장비에서 측정한 값이 아니라 참고용 데이터다. 이 구분을 절대 흐리지 않는다.

---

## 4. 개발 목표

### P0: 반드시 구현할 것

#### 4.1 GPU 식별과 측정 환경 기록

측정 결과가 어느 장치와 환경에서 생성되었는지 재현할 수 있어야 한다.

기본 정보:

- GPU index
- GPU name
- UUID는 내부 저장 가능하나 자동화 출력에서는 계속 마스킹
- VBIOS version
- driver version
- PCI bus id 및 link 정보
- VRAM total
- 최대 graphics 및 memory clock
- compute capability
- OS, Python, collector provider
- 측정 시작과 종료 시각

CPU 성능 정보는 이번 범위에 포함하지 않는다. 환경에 CPU 이름이 이미 포함되어 있다면 기록은 가능하지만, CPU 점수나 CPU 병목 판정에 사용하지 않는다.

#### 4.2 실시간 센서 수집

기존 센서 수집을 유지하고, 진단에 필요한 항목을 확장한다.

- temperature
- GPU utilization
- memory controller utilization
- VRAM used/free/total
- power draw 및 power limit
- graphics clock 및 memory clock
- performance state
- fan speed
- encoder/decoder utilization
- 가능한 경우 active clock throttle reason
- 가능한 경우 XID, ECC, 메모리 오류 관련 상태

각 센서 값에는 값 자체뿐 아니라 timestamp, 단위, 수집 가능 여부를 포함한다. 지원하지 않는 값은 추정하지 말고 `null`로 반환한다.

#### 4.3 실제 GPU 연산 측정

센서 수집과 실제 연산 실행을 분리한다. 새로운 추상화를 다음과 같이 둔다.

```text
GpuCollector
  장치 식별, 정적 정보, 센서와 환경 수집

GpuWorkloadRunner
  GPU에서 통제된 연산을 실행하고 실제 경과 시간을 측정

MeasurementOrchestrator
  사전 확인, 워밍업, 연산, 센서 샘플링, 결과 결합

DiagnosticEngine
  센서와 측정 결과를 근거로 이상 징후와 원인을 분류

ReportBuilder
  JSON 및 사람이 읽는 검사 리포트 생성
```

초기 workload는 장치에 데이터를 미리 할당한 뒤 GPU 내부에서 반복 실행하는 통제된 행렬 연산 또는 동등한 CUDA workload로 시작한다. host-to-device 데이터 복사와 파일 I/O가 결과를 지배하지 않도록 한다.

측정 결과에는 최소한 다음을 포함한다.

- workload name
- backend 및 dtype
- shape 또는 workload configuration
- warmup count
- measured iteration count
- GPU event 기준 elapsed time
- operation count
- achieved TFLOPS
- 측정 중 센서 요약
- 측정 신뢰성 상태: `valid`, `inconclusive`, `failed`
- 실패 또는 무효화 사유

공식은 명시적으로 기록한다.

```text
achieved_tflops = operation_count / elapsed_seconds / 1e12
```

행렬 곱셈의 operation count를 계산할 때 multiply-add를 2개 연산으로 볼지 여부도 workload metadata에 기록한다. 같은 측정 프로토콜끼리만 비교할 수 있어야 한다.

#### 4.4 쓰로틀링 및 원인 진단

단순히 “느리다”라고 표시하지 말고, 측정 중 관찰된 근거를 함께 제시한다.

초기 규칙 기반 진단의 예:

| 진단 | 관찰 근거 |
|---|---|
| thermal throttling 의심 | 온도 상승과 graphics clock 하락이 같은 구간에 반복됨 |
| power limit 의심 | power draw가 power limit에 근접하고 clock이 제한됨 |
| cooling issue 의심 | 동일 workload에서 온도 상승 속도와 고온 유지 시간이 큼 |
| workload invalid | GPU utilization이 충분하지 않거나 측정 시간이 너무 짧음 |
| driver/runtime issue 의심 | 측정 전후 환경이 다르거나 workload 실행 오류 발생 |
| no_gpu_evidence | GPU 측정값만으로 원인을 결정할 수 없음 |

진단 결과는 다음 구조를 따른다.

```json
{
  "category": "thermal",
  "severity": "warning",
  "title": "고온 구간에서 클럭이 하락했습니다",
  "evidence": {
    "temperature_peak_c": 84.0,
    "graphics_clock_min_mhz": 1190.0,
    "throttle_samples": 12
  },
  "confidence": "medium",
  "recommendation": "냉각팬, 방열판, 써멀패드와 케이스 airflow를 점검하세요"
}
```

원인 진단은 확률적 추정이다. 물리적 고장, 채굴 이력, 실제 사용 연수와 같은 사실을 센서만으로 단정하지 않는다.

---

## 5 TFLOPS, peak utilization, MFU 정의

이 세 가지를 혼동하지 않는다.

### 정적 theoretical peak

GPU 모델과 dtype에 따라 계산되는 제조사 또는 사양 데이터상의 이론적 최대 성능이다. `data/static/benchmarks`의 값은 이 범주 또는 외부 참고 벤치마크에 해당한다.

이 값은 현재 장비가 실제로 달성한 성능이 아니다.

### achieved TFLOPS

통제된 GPU workload를 실제 실행해 측정한 유효 연산 성능이다. 초기 제품의 핵심 측정값이다.

### peak utilization

동일 dtype과 동일한 산정 기준에서 다음처럼 계산한다.

```text
peak_utilization = achieved_tflops / theoretical_peak_tflops * 100
```

정적 peak 값의 출처와 산정 기준이 불명확하면 percentage를 표시하지 않고 `unknown` 또는 `not_comparable`로 표시한다.

### Model FLOPs Utilization, MFU

MFU는 임의의 GPU workload에서 자동으로 얻어지는 값이 아니다. 특정 모델의 forward 또는 training workload, 모델 FLOPs 계산 방식, batch size, sequence length, precision, throughput이 있어야 한다.

따라서 초기 GEMM 진단 결과를 MFU라고 부르지 않는다. 초기에는 `achieved_tflops`와 `peak_utilization`을 제공한다. 실제 모델 workload adapter가 추가된 뒤에만 MFU를 제공한다.

MFU를 표시할 때는 반드시 다음을 기록한다.

- model name 및 version
- inference 또는 training
- batch size
- sequence length 또는 input shape
- precision
- model FLOPs 계산 출처
- measured throughput
- theoretical peak 기준
- MFU 계산식

---

## 6 기준선과 1년 전 비교

현재 측정 결과를 저장해 미래의 비교 기반을 만든다. 그러나 비교 데이터가 없는데도 성능 하락을 추정하지 않는다.

### 기준선 생성

검사 리포트마다 다음을 저장한다.

- baseline id
- GPU identity
- workload protocol id 또는 hash
- driver/runtime 정보
- workload configuration
- achieved TFLOPS
- 센서 요약
- 진단 결과
- 생성 시각

### 비교 가능 조건

다음 조건이 맞을 때만 이전 결과와 delta를 계산한다.

- 같은 GPU identity 또는 명확하게 추적 가능한 장치
- 같은 workload protocol
- 같은 dtype
- 같은 shape/configuration
- 비교 가능한 driver/runtime 조건
- 유효한 측정 상태

조건이 맞지 않으면 “비교 불가”라고 표시한다. GPU 모델이 다르거나, 과거 baseline이 없거나, CPU와 데이터 파이프라인의 영향이 제거되지 않은 경우에는 상대 가치나 성능 하락률을 계산하지 않는다.

이번 단계의 목표는 비교 알고리즘이 아니라 **나중에 비교할 수 있는 재현 가능한 기록을 쌓는 것**이다.

---

## 7 이번 단계에서 구현하지 않는 것

다음 기능은 데이터와 검증 프로토콜이 충분히 쌓인 뒤의 후속 범위다.

### CPU bottleneck 분석

- CPU benchmark
- CPU utilization과 GPU starvation의 인과 판정
- data loader, PCIe transfer, host scheduling 분석
- CPU 때문에 TFLOPS가 낮다고 자동 결론 내리는 기능

초기 workload는 CPU 영향을 줄이도록 GPU resident data와 GPU event를 사용한다. 그래도 CPU 또는 host 영향이 배제되지 않으면 결과를 `inconclusive`로 표시한다.

### 장비 간 상대 가치 및 순위

- 서로 다른 GPU 모델의 단일 종합 점수
- “A GPU가 B GPU보다 몇 퍼센트 더 가치 있다”는 판단
- 시장 가격과 결합한 자동 매입가
- 사용자 전체 장비 순위
- 서로 다른 workload 간 직접 비교

초기에는 정적 참고 데이터와 현재 장비의 실제 측정 데이터를 별도 영역에 표시한다. 순위나 가격 의사결정은 실제 측정 데이터, 거래 결과, workload별 기준선이 쌓인 뒤에 개발한다.

### 과도한 진단 주장

- 정확한 사용 기간 추정
- 채굴 이력 추정
- 제조사 보증 수준의 인증
- 센서만으로 VRAM 물리 결함 확정
- GPU가 느린 모든 이유를 단일 원인으로 확정

---

## 8 권장 API와 데이터 계약

현재 `schema_version: 1.0` 응답 봉투를 유지한다.

```json
{
  "schema_version": "1.0",
  "ok": true,
  "provider": "nvidia-smi",
  "data": {},
  "error": null
}
```

기존 `health`, `list`, `inspect`, `snapshot`, `report` 동작을 깨뜨리지 않는다. 센서 시간 측정인 `report`와 실제 GPU workload 측정은 의미가 다르므로 새 명령 또는 명시적인 measurement mode로 구분한다. 기존 `report`가 실제 benchmark인 것처럼 조용히 의미를 변경하지 않는다.

향후 추가할 수 있는 P0 명령의 예:

```text
validate_gpu       통제된 GPU workload 실행 및 진단
baseline_gpu       유효한 측정 결과를 기준선으로 저장
read_gpu_history   동일 장치의 저장된 측정 이력 조회
```

응답에는 최소한 다음 영역이 있어야 한다.

```text
device
environment
workload
telemetry_summary
performance
findings
baseline
limitations
```

`limitations`는 필수다. 측정하지 않은 항목, 비교 불가 사유, 지원되지 않는 센서를 명시해야 한다.

---

## 9 최종 프론트엔드 방향

현재 `application/gpu_measurer/ui.py`의 Tkinter 화면은 측정 엔진을 점검하기 위한 중간 UI다. GPU-Z와 비슷한 `Graphics Card`, `Sensors`, `Advanced`, `Validation` 탭 구조를 최종 제품 화면으로 확장하지 않는다.

최종 프론트엔드는 **GPU 상태를 읽는 화면이 아니라, GPU를 검사하고 결과를 판단하며 리포트를 만드는 Windows 데스크톱 운영 앱**이어야 한다.

### 9.1 두 앱의 프론트엔드 제품 결정

- 최종 제품: PySide6/Qt 기반 Windows 데스크톱 앱 2종
- 개인 구매자용 앱: `GPU Check`
- AI 서버 운영자용 앱: `GPU Ops`
- 데이터 연결: UI adapter가 `GpuMeasurementService`를 직접 호출
- 실행 형태: GPU가 있는 컴퓨터에서 하나의 로컬 앱을 실행
- 기존 Tkinter UI: 개발용 smoke test와 긴급 fallback으로 유지 가능하지만 최종 UX 기준으로 삼지 않음
- 장기 확장: 현재 서비스 경계를 유지해 향후 Web API나 원격 agent를 추가할 수 있게 설계

프론트엔드는 collector를 직접 호출하지 않는다. UI는 `nvidia-smi`를 실행하지 않으며, 진단 규칙과 TFLOPS 계산을 자체적으로 다시 구현하지 않는다. 모든 측정, 진단, 비교 가능성 판단은 서비스와 측정 엔진이 수행하고 프론트엔드는 결과를 명확하게 보여준다.

실제 workload 측정은 UI thread에서 실행하지 않는다. PySide6의 `QThreadPool` 또는 동등한 worker 구조로 백그라운드에서 실행하고, signal 또는 명시적인 상태 이벤트로 화면을 갱신한다. 검사 중에도 사용자가 앱을 이동하거나 취소할 수 있어야 한다.

공통 UI component를 사용할 수는 있지만 두 앱의 시작 화면과 전역 내비게이션은 분리한다. 개인 구매자에게 fleet 운영 메뉴를 보여주지 않고, 운영자에게 1회성 구매 wizard만 보여주지 않는다.

#### `GPU Check` 앱의 화면 구조

개인용 앱은 앱을 실행한 뒤 구매 전 확인 또는 수령 후 검수로 바로 들어가는 단일 목적 앱이다.

```text
GPU Check
  검사 시작 | 최근 결과 | 구매 기록 | 설정
```

권장 흐름:

```text
앱 실행 -> 검사 모드 선택 -> GPU 검사 -> 결과 확인 -> 거래·반품 리포트 공유
```

첫 화면은 다음 네 가지를 중심으로 한다.

- 감지된 GPU
- `현장 간이 확인` 또는 `수령 후 정밀 검수` 버튼
- 최근 검사 결과
- 기준선 또는 과거 결과가 없는 경우의 안내

개인용 앱의 화면은 다음 원칙을 따른다.

- 장비 목록은 기본적으로 단일 GPU 중심으로 보여준다.
- workload, dtype, warmup 같은 전문 설정은 “고급 설정” 안에 둔다.
- 검사 결과는 `통과`, `주의`, `판정 불가`, `실패`로 먼저 보여준다.
- 결과 화면에는 “이 GPU를 사도 된다”라고 단정하지 않고 관찰된 사실과 한계를 보여준다.
- 구매가, 판매자 메모, 검사 장소 같은 입력은 결과를 방해하지 않도록 검사 전후 별도 단계에 둔다.
- 외부 공유용 리포트 생성이 주요 행동이다.

#### `GPU Ops` 앱의 화면 구조

운영자용 앱은 반복 검사와 장비 이력을 중심으로 하는 업무 앱이다.

```text
GPU Ops
  운영 현황 | 장비 | 검사 작업 | 이력 | 리포트 | 설정
```

권장 흐름:

```text
운영 현황 -> 검사 필요 장비 확인 -> 검사 작업 실행 -> 원인 확인 -> 조치와 리포트 기록
```

운영자용 앱은 다음을 우선한다.

- 여러 GPU와 서버를 표 형태로 빠르게 확인
- 검사 필요, 주의, 실패 상태를 작업 목록으로 제공
- 장비별 기준선과 반복 검사 이력 연결
- 장시간 workload 검사의 진행률과 취소 제공
- 내부 운영용 상세 리포트와 고객 공유용 리포트 분리
- 장비 간 순위를 표시하지 않고 상태와 근거를 표시

두 앱의 동일한 결과라도 문구가 달라질 수 있다.

```text
GPU Check:
  “검사 중 고온 구간에서 graphics clock 하락이 관찰되었습니다.”

GPU Ops:
  “GPU 47번에서 최근 3회 검사 중 2회 thermal event와 clock drop이 반복되었습니다.”
```

### 9.2 `GPU Ops`의 첫 화면

`GPU Ops`의 첫 화면은 제품 소개나 GPU 사양 표가 아니다. 운영자가 지금 무엇을 해야 하는지 바로 알 수 있는 **검사 작업 화면**이다. `GPU Check`의 첫 화면은 앞서 정의한 단일 GPU 검사 시작 화면을 사용한다.

첫 화면에서 보여줄 핵심 정보:

- 검사 대기 장비 수
- 최근 측정에서 주의가 필요한 장비
- 현재 검사 중인 작업
- 최근 생성된 리포트
- 기준선이 아직 없는 장비
- 측정 실패 또는 지원되지 않는 센서가 있는 장비

기본 문장은 사양 중심의 “RTX 4090, 24GB”가 아니라 상태 중심이어야 한다.

```text
검사 필요       3대
주의 필요       1대
검사 진행 중    1건
최근 검사       12분 전
```

이 화면에는 전체 GPU 순위나 장비 간 상대 점수를 넣지 않는다. 지금 단계에서 사용자가 해야 할 일은 순위를 보는 것이 아니라, 검사하지 않은 장비를 검사하고 이상 장비의 리포트를 확인하는 것이다.

### 9.3 정보 구조와 주요 화면

#### A. 검사 작업 목록

장비를 행 단위로 비교할 수 있는 운영 목록이다. 장식적인 카드보다 스캔하기 쉬운 표와 상태 배지를 우선한다.

필수 열:

- 장비 이름과 GPU 모델
- 마지막 검사 시각
- 검사 상태
- achieved TFLOPS 또는 `미측정`
- 주요 진단 요약
- 기준선 상태
- 리포트 열기

상태는 다음처럼 제한된 의미를 가진다.

```text
검사 필요 | 검사 중 | 정상 | 주의 | 측정 불가 | 실패 | 비교 기준 없음
```

#### B. 장비 상세 화면

특정 GPU를 선택했을 때의 기본 화면이다. 원시 센서 전체를 먼저 보여주지 말고, 결론과 근거를 위에서 아래로 배치한다.

권장 순서:

1. GPU identity와 마지막 검사 상태
2. 가장 중요한 결과: achieved TFLOPS, workload, 측정 시각
3. 진단 요약: 정상, 주의, 측정 불가
4. “왜 이런 결과인가” 영역
5. 온도, 전력, 클럭, utilization 시계열
6. 측정 프로토콜과 환경
7. 기준선 및 이력
8. 리포트 생성 및 내보내기

상단의 주요 행동은 하나로 둔다.

```text
GPU 검사 실행
```

정적 사양과 외부 벤치마크 참고값은 실제 측정 결과 아래의 별도 영역에 표시하고, `참고값`, `현재 측정값`, `비교 불가`를 시각적으로 구분한다.

#### C. GPU 검사 실행 화면

검사 시작 전에 사용자가 검사 조건을 확인할 수 있어야 한다.

- 대상 GPU
- workload 이름
- dtype
- shape 또는 workload 설정
- warmup 수
- 측정 반복 수 또는 시간
- 저장할 리포트 이름

검사 중에는 단순한 spinner 대신 다음을 보여준다.

- 현재 단계: 사전 확인, warmup, workload 실행, 센서 수집, 진단, 리포트 저장
- 경과 시간
- 현재 온도, 전력, graphics clock
- 일시적인 throttle 이벤트
- 취소 버튼

검사 완료 후에는 숫자만 보여주지 않고 다음 세 가지를 한 화면에서 보여준다.

```text
결과        achieved TFLOPS: 27.8
판정        주의
이유        고온 구간에서 graphics clock 하락이 반복됨
```

#### D. 장비 이력 화면

같은 장비에 대해 저장된 검사 이력을 시간순으로 보여준다.

- 최초 기준선
- 최근 검사
- 검사 프로토콜
- achieved TFLOPS 변화
- 온도와 클럭 변화
- 진단 이벤트
- 리포트 다운로드 또는 공유

기준선이 없으면 차트를 억지로 그리지 않고 다음을 표시한다.

```text
아직 비교 가능한 기준선이 없습니다.
이번 검사를 기준선으로 저장할 수 있습니다.
```

기준선이 있더라도 protocol, dtype, workload가 다르면 delta를 표시하지 않는다. 이력 화면은 장비 간 순위 화면이 아니라 **한 장비의 변화 추적 화면**이다.

#### E. 리포트 화면

리포트는 내부 운영용과 외부 공유용을 분리한다.

내부 운영용:

- 전체 센서 시계열
- throttle reason
- runtime 및 driver 정보
- 원시 workload 설정
- 실패 로그
- 진단 confidence

외부 공유용:

- GPU identity의 필요한 부분
- 검사 시각
- 검사 workload
- achieved TFLOPS
- 정상 또는 주의 판정
- 관찰된 원인
- 측정 한계
- UUID, hostname 등 민감 정보 마스킹

외부 리포트는 “제조사 인증” 또는 “절대적 정상 보증”처럼 보이면 안 된다. 제목과 문구는 다음처럼 작성한다.

```text
통제된 workload 기반 GPU 성능 검사 리포트
이 결과는 검사 시점의 소프트웨어와 환경에서 관찰된 상태를 설명합니다.
```

### 9.4 시각적 디자인 방향

최종 프론트엔드는 하드웨어 애호가용 정보 패널이 아니라 반복 작업을 위한 B2B 운영 도구다.

- 어두운 콘솔 테마보다 밝고 차분한 운영 화면을 기본으로 한다.
- 초록색 하나로 모든 상태를 표현하지 않는다. 정상, 주의, 실패, 측정 불가를 구분한다.
- 큰 숫자는 achieved TFLOPS, 마지막 검사 상태, 주요 진단에만 사용한다.
- 센서 그래프는 목적이 있을 때만 사용한다. 모든 센서를 항상 그리지 않는다.
- 화면마다 주 행동을 하나만 강조한다.
- 사양, 실제 측정값, 진단, 제한사항을 서로 다른 영역으로 분리한다.
- 읽기 어려운 탭과 깊은 설정 메뉴를 줄이고, 작업 흐름에 따라 이동한다.
- 로딩, 빈 상태, 실패, 부분 센서 지원, 측정 불가 상태를 처음부터 디자인한다.
- 색상만으로 상태를 전달하지 않고 텍스트와 아이콘을 함께 사용한다.
- 반응형 레이아웃을 지원하되, 첫 MVP는 데스크톱 운영 환경을 우선한다.

앱별 내비게이션은 다음을 사용한다.

```text
GPU Check: 검사 시작 | 최근 결과 | 구매 기록 | 설정
GPU Ops:   운영 현황 | 장비 | 검사 작업 | 이력 | 리포트 | 설정
```

`Benchmark CSV`, `Advanced`, `System` 같은 현재 탭 이름은 내부 개발자용 상세 패널로 이동시킨다.

### 9.5 프론트엔드 상태 계약

프론트엔드는 다음 상태를 명시적으로 처리해야 한다.

- 로컬 서비스 초기화 전
- GPU collector 없음
- GPU 없음
- 장비 목록 로딩
- 검사 대기
- 검사 진행 중
- 검사 성공
- 주의 진단
- 측정 불가
- 검사 실패
- 센서 일부 미지원
- 기준선 없음
- 비교 프로토콜 불일치

프론트엔드가 임의로 `정상`, `성능 저하`, `노후화`를 계산하지 않는다. 백엔드가 반환한 `findings`, `confidence`, `limitations`를 표시한다.

### 9.6 데스크톱 앱과 비동기 검사 흐름

센서 조회는 짧은 요청으로 처리할 수 있지만 실제 workload 측정은 장시간 실행될 수 있다. 따라서 데스크톱 UI에서 검사 요청과 검사 결과 처리를 분리한다.

권장 흐름:

```text
사용자: GPU 검사 실행 클릭
  -> Desktop Controller
  -> Background Worker
  -> MeasurementOrchestrator
  -> progress signal: 단계, 진행률, 현재 센서, 이벤트
  -> completed signal: MeasurementResult, report_id
  -> 화면 갱신 및 리포트 표시
```

검사 작업은 취소 가능해야 한다. 취소 시 GPU workload cleanup과 센서 수집 종료를 수행하고 결과를 성공으로 저장하지 않는다. 중요한 것은 workload 실행 동안 UI가 멈추지 않는 것이다.

현재 앱은 HTTP 호출 없이 `GpuMeasurementService`를 직접 사용한다. JSON 응답 봉투는 CLI와 향후 LLM 도구를 위한 공통 계약으로 유지한다. 향후 Web API가 추가되더라도 현재 데스크톱 UI를 HTTP 호출에 종속시키지 않는다.

프론트엔드는 결과 모델의 다음 영역을 직접 소비한다.

```text
device
workload
performance
telemetry_summary
findings
baseline
limitations
```

원시 센서 값이 없는 경우 빈 그래프를 그리지 말고, 해당 센서가 지원되지 않거나 수집되지 않았다는 상태를 보여준다.

### 9.7 데스크톱 프론트엔드 구현 순서

1. PySide6/Qt 앱 shell과 기존 서비스 연결용 UI adapter를 만든다.
2. `application/gpu_measurer/desktop/` 아래에 `shared`, `buyer`, `operator`를 분리하고, 각 앱의 `main_window`, `controllers`, `workers`, `viewmodels`를 둔다.
3. mock service와 mock JSON으로 `GPU Check`의 단일 검사 흐름을 먼저 만든다.
4. 실제 장치 목록과 snapshot을 `GpuMeasurementService`에 연결한다.
5. 백그라운드 validation worker와 `GPU Check` 결과 리포트를 연결한다.
6. achieved TFLOPS, telemetry, findings, limitations를 조합한 결과 화면을 만든다.
7. 공통 core를 유지한 채 `GPU Ops`의 장비 목록, 검사 작업, baseline 이력을 추가한다.
8. 내부용 및 외부 공유용 리포트 화면을 각 앱의 목적에 맞게 분리한다.
9. 빈 상태, 실패 상태, 측정 불가 상태를 실제 서비스 응답으로 검증한다.
10. 기존 Tkinter UI는 새 화면으로 교체하기 전까지 smoke test용으로만 유지한다.

각 앱의 첫 수직 흐름은 다음과 같다.

```text
GPU Check:
  검사 모드 선택 -> 장치 선택 -> 진행 상태 -> 결론과 근거 -> 거래·반품 리포트

GPU Ops:
  운영 현황 -> 검사 필요 장비 선택 -> 반복 검사 -> 원인과 이력 -> 운영 리포트
```

정적 사양 전체를 옮기거나 현재 Tkinter 탭을 새 데스크톱 화면에 그대로 복제하는 것은 첫 수직 흐름이 완료된 뒤에도 우선순위가 낮다.

---

## 10 구현 원칙

1. `nvidia-smi`는 장치 상태와 센서 수집 도구이지 benchmark가 아니다.
2. 정적 CSV 값과 실제 측정값을 서로 다른 필드와 화면 영역으로 유지한다.
3. GPU workload 실행과 센서 수집을 별도 컴포넌트로 분리한다.
4. 측정 프로토콜을 기록하지 않은 숫자는 미래 비교의 기준으로 사용하지 않는다.
5. 값이 없으면 추정하지 말고 `null`, `unknown`, `not_comparable` 중 적절한 상태를 반환한다.
6. 진단 결과에는 반드시 근거, 심각도, confidence, 권장 조치를 포함한다.
7. 실제 GPU가 없는 환경에서도 fake collector와 fake workload runner로 단위 테스트가 가능해야 한다.
8. 기존 JSON envelope와 개인정보 마스킹 규칙을 유지한다.
9. 새로운 기능은 `GpuMeasurementService`를 통해 데스크톱 UI, CLI, 향후 Web API와 LLM 도구가 공통으로 사용할 수 있게 한다.
10. 구현 전 관련 코드와 테스트를 읽고, 필요한 범위만 수정한다.

---

## 11 완료 기준

P0 구현은 다음을 만족해야 한다.

- 실제 NVIDIA GPU에서 통제된 workload가 실행된다.
- 측정 전 warmup과 측정 후 cleanup이 수행된다.
- GPU event 기준 시간이 사용된다.
- workload 설정과 operation count가 리포트에 남는다.
- achieved TFLOPS가 계산된다.
- 센서 샘플과 workload 결과의 시간 범위가 연결된다.
- 온도, 전력, 클럭, throttle reason을 근거로 진단이 생성된다.
- 측정 실패와 측정 무효가 성공 결과와 구분된다.
- baseline이 저장되며, 비교 조건이 맞지 않을 때 delta를 만들지 않는다.
- 기존 CLI와 테스트가 깨지지 않는다.
- GPU가 없는 CI 환경에서도 테스트가 통과한다.
- 사람과 LLM 모두가 읽을 수 있는 JSON 리포트가 생성된다.

실제 GPU에서의 수동 검증은 별도로 수행한다. 자동화 테스트만으로 실제 TFLOPS의 정확성을 보증한다고 표현하지 않는다.

---

## 12 협업 LLM에 대한 작업 지시

이 문서를 프로젝트의 개발 방향 기준으로 사용한다.

작업을 시작할 때 다음 순서를 따른다.

1. 현재 저장소의 관련 코드와 테스트를 읽는다.
2. 기존 계약을 유지하면서 변경 범위를 제안한다.
3. P0 기능을 가장 작은 수직 흐름으로 구현한다.
4. fake collector 또는 fake runner 테스트를 먼저 추가한다.
5. 실제 GPU 검증이 필요한 부분과 로컬 환경에서 검증한 부분을 구분한다.
6. 결과 JSON, 리포트, 문서를 함께 갱신한다.
7. 구현하지 않은 기능을 구현된 것처럼 설명하지 않는다.

특히 다음 질문에 대해 임의로 기능을 추가하지 않는다.

- CPU 병목을 어떻게 판정할 것인가?
- 서로 다른 GPU의 상대 가치를 어떻게 점수화할 것인가?
- 실제 데이터가 없는 상태에서 1년 전보다 몇 퍼센트 느려졌다고 어떻게 말할 것인가?

이 질문들은 현재 구현 목표가 아니다. 지금 만들어야 하는 것은 **나중에 그 질문에 답할 수 있도록, 재현 가능하고 설명 가능한 GPU 측정 데이터를 쌓는 시스템**이다.

최종적으로 사용자가 받아야 하는 문장은 다음과 같아야 한다.

> 이 GPU의 현재 상태는 무엇이며, 통제된 workload에서 실제 성능은 얼마였고, 성능에 영향을 준 관찰 가능한 원인은 무엇이며, 다음 측정을 위해 어떤 기준으로 기록되었는가?
