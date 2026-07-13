# 웹 및 AI 에이전트 개발 백로그

- 상태: `planned`
- 우선순위: High
- 작성자: Codex
- 기준일: 2026-07-13

## 다음 AI 에이전트에 대한 명시적 지시

다음 작업을 맡는 AI 에이전트는 이 문서를 구현 지시서로 사용한다. 단순 제안으로 끝내지 말고 아래 순서대로 코드 구현, 테스트, 실제 실행 검증, 관련 문서와 업무일지 갱신까지 완료한다. 작업 전 현재 코드와 `docs/technical-designs/gpu-measurer.md`를 읽고 기존 `GpuMeasurementService`와 JSON 계약을 재사용한다.

## 현재 기반

- `GpuCollector` 공통 계약과 `CollectorRegistry`
- NVIDIA `nvidia-smi` 수집기
- `GpuMeasurementService`
- `schema_version: 1.0` JSON CLI
- 데스크톱 UI와 로컬 측정 로그

## Epic 1: 로컬 Web API

### 구현 지시

- `GpuMeasurementService`를 호출하는 로컬 HTTP API를 만든다.
- 기본 바인딩은 `127.0.0.1`로 제한한다.
- OpenAPI 문서를 제공하고 요청·응답 모델을 JSON Schema로 고정한다.
- 다음 API를 구현한다.

```text
GET  /api/v1/health
GET  /api/v1/gpus
GET  /api/v1/gpus/{gpu_index}
GET  /api/v1/gpus/{gpu_index}/snapshot
POST /api/v1/measurements
GET  /api/v1/reports/{report_id}
```

- 측정 요청에는 GPU 번호, 측정 시간, 간격, 파일 저장 여부를 받는다.
- 측정 시간과 호출 빈도에 상한을 두고 잘못된 GPU 번호는 구조화된 오류로 반환한다.
- 장시간 측정은 작업 ID를 반환하고 상태 조회 방식으로 처리한다.

### 완료 조건

- 서비스 계층 외부에서 `nvidia-smi`를 직접 호출하지 않는다.
- 모든 API 응답에 버전과 오류 계약이 있다.
- 정상·잘못된 입력·수집기 부재 테스트가 있다.
- 실제 GPU에서 API 스모크 테스트를 통과한다.

## Epic 2: Web 프런트엔드

### 구현 지시

- `web/`에 TypeScript 기반 GPU 대시보드를 만든다.
- 첫 화면은 마케팅 페이지가 아니라 실제 GPU 진단 화면이어야 한다.
- 데스크톱 UI의 네 정보 영역을 웹에 맞게 재구성한다.

```text
Overview     장치 정보와 현재 핵심 지표
Sensors      시간축 센서 차트와 최소·최대·평균
Benchmarks   정확한 CSV 비교와 데이터 출처
Reports      측정 실행, 상태, 이전 결과
```

- 실시간 센서는 초기에는 1초 폴링으로 구현하고, 필요성이 확인되면 SSE로 전환한다.
- 모바일과 데스크톱에서 표·버튼·긴 GPU 이름이 겹치지 않도록 검증한다.
- 측정 실행 중 취소, 실패, 빈 데이터, 수집기 없음 상태를 구현한다.

### 완료 조건

- 실제 GPU 값이 화면에 표시된다.
- 차트와 표가 360px 및 1440px 뷰포트에서 잘리지 않는다.
- API 오류와 로딩 상태가 사용자에게 명확히 보인다.
- 주요 사용자 흐름의 브라우저 테스트와 화면 검증을 통과한다.

## Epic 3: AI 에이전트 호출

### 구현 지시

- 1차로 기존 JSON CLI를 에이전트용 안정 인터페이스로 유지한다.
- 2차로 `GpuMeasurementService`를 호출하는 MCP 서버 어댑터를 추가한다.
- MCP 도구는 다음 이름과 책임을 사용한다.

```text
gpu_health             수집기와 장치 상태 확인
list_gpus              GPU 목록 조회
inspect_gpu            정적 정보와 비교 데이터 조회
read_gpu_snapshot      단일 센서 조회
run_gpu_measurement    제한된 시간 측정 실행
```

- 모든 도구에 `inputSchema`와 `outputSchema`를 선언한다.
- 읽기 도구와 파일 생성·장시간 측정 도구를 구분한다.
- 파일 저장이나 부하 측정은 명시적 인수를 요구하고 기본값은 비저장·짧은 측정으로 둔다.
- 장시간 또는 부하를 유발하는 작업은 사용자 확인을 요구한다.

MCP 도구 규격은 구조화된 출력과 출력 스키마 검증을 지원하며, 영향 있는 호출에는 사람이 개입할 수 있어야 한다. 참고: [MCP Tools Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)

### 완료 조건

- 다섯 도구가 서비스 계층만 호출한다.
- JSON Schema와 실제 응답이 일치한다.
- 읽기 도구는 파일을 만들거나 하드웨어 설정을 바꾸지 않는다.
- 오류가 모델이 해석 가능한 코드·메시지·복구 힌트로 반환된다.
- MCP 클라이언트에서 실제 도구 검색과 호출을 검증한다.

## Epic 4: 제조사 확장

### 구현 지시

- NVIDIA 직접 NVML, AMD SMI, Intel Level Zero Sysman 수집기를 순서대로 추가한다.
- 공급자별 센서 누락은 `null`로 반환하고 공통 필드의 단위를 통일한다.
- 공급자 선택 결과와 기능 목록을 `health` 응답에 포함한다.

### 완료 조건

- 수집기별 계약 테스트가 동일한 테스트 묶음을 통과한다.
- 지원하지 않는 제조사 환경에서도 앱이 종료되지 않고 제한 상태를 보여준다.

## 공통 작업 규칙

- 기능 변경 시 기술 설계, 데이터 스키마, 요청 기록, 업무일지를 함께 갱신한다.
- 생성 데이터와 외부 데이터의 출처·라이선스·갱신일을 기록한다.
- 비밀키와 개인 식별 정보는 로그·JSON·화면에 포함하지 않는다.
- 완료 후 테스트 결과와 잔여 위험을 기록하고 커밋·PR로 제출한다.
