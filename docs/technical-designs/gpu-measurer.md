# GPU Measurer 기술 설계

- 상태: `implemented - extensible foundation`
- 작성자: Codex
- 최종 갱신: 2026-07-13

## 설계 목표

- GPU 제조사별 수집 방식과 화면·자동화 인터페이스를 분리한다.
- 데스크톱, 웹, AI 에이전트가 동일한 측정 규칙과 데이터 모델을 사용한다.
- 사람이 읽는 로그와 기계가 읽는 JSON을 모두 제공한다.
- 지원하지 않는 센서와 정확하지 않은 벤치마크 비교를 명시적으로 표시한다.

## 아키텍처

```text
collector.py
  GpuCollector Protocol
  CollectorRegistry
  NvidiaCollector
        ↓
service.py
  GpuMeasurementService
        ↓
serialization.py
  schema_version 1.0 JSON
        ↓
ui.py | main.py | future Web API | future MCP server
```

### 수집기 계약

모든 제조사 수집기는 다음 인터페이스를 구현한다.

- `is_available()`
- `list_devices()`
- `static_info(gpu_index)`
- `snapshot(gpu_index)`
- `environment()`
- `provider_name`

`CollectorRegistry`가 실행 환경에서 사용할 수 있는 수집기를 선택한다. 현재는 `NvidiaCollector`가 등록되어 있으며 AMD·Intel 구현은 같은 계약으로 추가한다.

### 공식 수집 경로

- NVIDIA: 현재 `nvidia-smi`, 향후 직접 NVML 어댑터
- AMD: AMD SMI Python API
- Intel: Level Zero Sysman API

NVIDIA는 NVML을 `nvidia-smi`의 기반 프로그래밍 인터페이스로 설명한다. AMD SMI는 GPU 정보와 성능 모니터링용 Python API를 제공하고, Intel Level Zero의 Sysman API는 장치 관리·원격 측정 기능을 제공한다.

참고:

- [NVIDIA NVML API](https://docs.nvidia.com/deploy/nvml-api/nvml-api-reference.html)
- [AMD SMI 문서](https://rocmdocs.amd.com/projects/amdsmi/en/latest/index.html)
- [Intel Level Zero Sysman](https://oneapi-src.github.io/level-zero-spec/level-zero/0.91/core/INTRO.html)

## 서비스 계층

`GpuMeasurementService`는 UI 종류와 무관한 다음 기능을 제공한다.

- GPU 목록 조회
- GPU 정적 정보와 벤치마크 조회
- 단일 센서 스냅샷
- 일정 시간 측정과 요약

웹 API와 MCP 서버는 수집기를 직접 호출하지 않고 이 서비스를 호출해야 한다.

## JSON 호출 계약

CLI 자동화 응답은 다음 봉투를 사용한다.

```json
{
  "schema_version": "1.0",
  "ok": true,
  "provider": "nvidia-smi",
  "data": {},
  "error": null
}
```

지원 명령:

```powershell
python application/main.py --health --json
python application/main.py --list --json
python application/main.py --inspect --gpu 0 --json
python application/main.py --snapshot --gpu 0 --json
python application/main.py --report --gpu 0 --duration 5 --interval 1 --json --no-save
```

`--no-save`는 보고서 파일을 만들지 않아 에이전트의 읽기 중심 호출에 적합하다. 오류도 같은 봉투 형식으로 반환하고 프로세스 종료 코드는 1로 설정한다.

자동화 JSON과 저장 로그에서는 GPU UUID와 컴퓨터 호스트명을 기본적으로 `[redacted]`로 마스킹한다.

## 데스크톱 UI

- Graphics Card: 핵심 지표, 장치 상세, 스크롤, 정적 비교
- Sensors: 현재·최소·최대·평균과 CSV 기록
- Advanced: General, PCIe, Memory, Runtime, Benchmark, System
- Validation: 시간 측정과 로컬 로그

## 측정과 비교

1. 선택된 수집기에서 GPU와 환경을 식별한다.
2. 단조 시계를 기준으로 지정 시간 동안 센서를 수집한다.
3. 숫자 센서의 최소·최대·평균을 계산한다.
4. GPU 모델명을 정규화하고 CSV에서 정확히 매칭한다.
5. 정확한 행이 없으면 유사 이름만 제시하고 점수는 할당하지 않는다.
6. 로그 또는 버전형 JSON으로 결과를 반환한다.

## 현재 제한

- 실행 가능한 수집기는 아직 NVIDIA `nvidia-smi` 하나다.
- 현재 측정은 센서 샘플링이며 GPU 부하 벤치마크가 아니다.
- RTX 4060 Laptop GPU의 정확한 정적 CSV 행이 없다.
- 웹 API와 MCP 서버는 백로그 상태다.
- 온라인 검증, BIOS 저장, 오버클럭 제어는 범위 밖이다.

## 검증

- Python 문법 검사
- 단위 테스트 8개
- 실제 NVIDIA GPU에서 JSON `health/list/inspect/snapshot/report` 확인
- UI 스모크 테스트와 실제 렌더링 확인

다음 구현 계획과 완료 조건은 [웹 및 AI 에이전트 개발 백로그](../backlogs/web-and-agent-development.md)에서 관리한다.
