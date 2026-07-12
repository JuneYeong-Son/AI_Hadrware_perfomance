# 요청 기록

프로젝트에서 받은 요청과 처리 결과를 날짜순으로 기록한다. 구현 계획은 `docs/backlogs/`, 실제 수행 기록은 `docs/worklog/`에서 관리한다.

## 2026-07-09

- 한국어 응답을 기본으로 사용하도록 요청받았다.
- GitHub 저장소를 연결하고 프로젝트 개요를 작성했다.
- 협업자 컴퓨터의 RTX 3060 Ti 환경을 참고 문서로 기록했다.
- GPU 비교 데이터와 cold start 문제를 조사했다.
- 정적 사양, 동적 센서, 벤치마크 결과의 데이터 스키마 초안을 작성했다.

## 2026-07-13

- 정적 GPU CSV 2개를 `data/static/benchmarks/`에 정리했다.
- 문서를 역할별 디렉터리로 분류하고 업무일지 공간을 만들었다.
- GPU-Z 흐름을 참고한 GPU Measurer 데스크톱 MVP를 구현했다.
- 실시간 센서, 정적 CSV 비교, 로그 리포트, Device details 스크롤을 구현했다.
- 현재 PC의 RTX 4060 Laptop GPU에서 실행 결과를 생성했다.
- 확장 가능한 `GpuCollector`, `CollectorRegistry`, `GpuMeasurementService` 구조를 구현했다.
- 웹과 AI 에이전트가 사용할 `schema_version: 1.0` JSON CLI를 구현했다.
- `docs/logs/`를 추가 디렉터리 없이 `docs/backlogs/`로 변경했다.
- `requests-log.md`를 `docs/worklog/`로 이동했다.
- 웹 개발과 AI 에이전트 호출을 위한 명시적 실행 백로그를 작성했다.

## 관련 문서

- [프로젝트 개요](../overview/project-overview.md)
- [GPU Measurer 기술 설계](../technical-designs/gpu-measurer.md)
- [웹 및 AI 에이전트 개발 백로그](../backlogs/web-and-agent-development.md)
- [데이터 스키마](../data/dataset-schema.md)
