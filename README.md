# AI Hardware Performance

현재 컴퓨터의 GPU 정보와 실시간 센서를 수집하고, 정적 벤치마크 데이터와 비교하는 로컬 진단 프로젝트입니다.

## 현재 상태

- NVIDIA `nvidia-smi` 기반 GPU 정보·센서 수집
- GPU-Z 흐름을 참고한 데스크톱 UI
- PassMark 및 Compute API CSV 비교
- 센서 CSV와 측정 로그 생성
- 웹·AI 에이전트 연동을 위한 버전형 JSON CLI
- 제조사별 수집기를 추가할 수 있는 공통 수집기 계약과 서비스 계층

## 실행

```powershell
python application/main.py
```

## 자동화 인터페이스

```powershell
python application/main.py --health --json
python application/main.py --list --json
python application/main.py --inspect --gpu 0 --json
python application/main.py --snapshot --gpu 0 --json
python application/main.py --report --gpu 0 --duration 5 --interval 1 --json --no-save
```

## 구조

```text
application/              데스크톱 앱, 수집기, 서비스, CLI
data/static/benchmarks/   정적 GPU 비교 데이터
docs/overview/            프로젝트 개요
docs/data/                데이터 출처와 스키마
docs/technical-designs/   구현 설계
docs/backlogs/            앞으로 실행할 개발 계획
docs/worklog/             요청 기록과 날짜별 업무일지
docs/reference/           특정 환경의 참고 정보
web/                      웹 클라이언트 예정 공간
```

다음 개발 단계는 [웹 및 AI 에이전트 개발 백로그](docs/backlogs/web-and-agent-development.md)를 기준으로 진행합니다.
