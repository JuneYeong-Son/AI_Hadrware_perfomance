# 요청 기록 (Requests Log)

이 파일은 사용자가 Claude에게 한 요청/지시를 시간 순으로 기록합니다.
Claude는 새 작업을 시작하기 전에 이 파일을 참고해 이전 맥락을 이어갑니다.

> 형식: `- [날짜] 요청 원문 — (처리 결과/메모)`

---

## 2026-07-09

- 한글로 대화하고 싶음 — "내가 하는 말에 한글로 왠만하면 알려줘" → 앞으로 한글로 응답.
- 로그인 상태 확인 요청 — "로그인 됐지" → Claude Code 정상 연결 확인.
- GitHub 연결 요청 — "github에 연결해줘".
- 현재 저장소(`AI_perfo`)를 아래 GitHub 저장소에 연결 요청
  - URL: https://github.com/JuneYeong-Son/AI_Hadrware_perfomance
  - → `git init` + `origin` 연결 + 첫 커밋(README, .gitignore, application/web 폴더) push 완료. 브랜치: `main`.
- 내가 하는 말들을 `docs` 폴더에 저장해서 나중에 기억해 쓸 수 있게 해달라 — → 이 파일(`docs/requests-log.md`) 생성. 앞으로 요청이 들어올 때마다 여기에 추가.
- 프로젝트 개요 설명 — GPU 성능 진단/벤치마크 서비스. (1) 사용자 GPU 정보 및 성능 영향 요소 모두 수집, (2) 벤치마크 프로그램 실행해 신제품/다른 GPU 대비 수준 평가(발열·속도·가동률 등), (3) 성능 정보 백엔드 저장. → [docs/project-overview.md](project-overview.md) 작성.
- "RTX 3060 사용 중" 언급 — `nvidia-smi` 조회 결과 실제로는 **RTX 3060 Ti**(VRAM 8GB, 드라이버 576.52, CUDA 12.9). → [docs/gpu-info.md](gpu-info.md) 작성.
- Cold start 문제 제기 — "성능 비교하려면 데이터 필요, cold start 발생할 듯, 데이터를 다른 곳에서 가져오고 싶다." → 조사 결과 **dbgpu**(pip, 2000+ GPU 스펙 오프라인 DB, MIT) 채택하기로. RTX 3060 Ti 조회·비교 검증 완료. 실사용 점수는 Kaggle PassMark CSV로 보완 가능. → [docs/data-sources.md](data-sources.md) 작성.
- "데이터셋 구조를 보여줘" — dbgpu GPU 1개 = 54개 필드(식별/아키텍처/클럭/메모리/연산유닛/전력/API/성능지표) 전체 덤프해 확인. 정적 스펙(dbgpu) + 동적 실측(nvidia-smi) + 저장 스키마 초안(gpu_specs / measurements / benchmark_results 3테이블) 정리. → [docs/dataset-schema.md](dataset-schema.md) 작성.

---

## 메모 / 알아둘 점

- 프로젝트 루트: `c:\Users\손\Desktop\AI_perfo`
- 구조: `application/` (백엔드), `web/` (프론트) — 현재는 비어 있음.
- ⚠️ 홈 디렉토리(`C:\Users\손`)에 다른 프로젝트(`nb04-seven-team1`)의 git 저장소가 실수로 생성되어 있음. `AI_perfo`는 자체 저장소로 분리됨.
