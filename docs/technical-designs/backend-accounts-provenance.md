# 백엔드 · 계정 · 측정 진위 증명 · 성능 분석

GPU 측정 앱에 사용자 계정, 측정 결과 진위 증명, 사용자 전체 성능 분석을 더하는
백엔드와 그 데스크톱 연동을 정리한다. 구현체는 `application/backend/`(서버)와
`application/gpu_measurer/desktop/shared/`(클라이언트 연동)에 있다.

## 목표

- 각 사용자가 계정으로 로그인하고, 자신의 측정을 서버에 기록한다.
- 공유된 벤치마크 결과가 특정 기기에서 나온 진짜 값이며 위조되지 않았음을 검증한다.
- 사용자들의 achieved TFLOPS를 모아 모델·프로토콜별 성능 분포를 분석한다.

## 스택

- FastAPI + SQLAlchemy 2.0 + SQLite(개발) — 측정 엔진과 같은 Python 생태계.
- 인증: `PyJWT`(HS256) + `bcrypt`. 데스크톱 클라이언트는 stdlib `urllib`만 사용.

## 데이터 모델

- **User** — email, display_name, bcrypt password_hash, `token_version`.
- **Device** — owner, 하드웨어 `fingerprint`(클라이언트가 GPU UUID를 해시한 값),
  공유용 `public_code`(`NV-XXXX-XXXX`), 기기 전용 `hmac_secret`(서버 밖으로 안 나감).
- **Measurement** — owner, device, gpu_name, dtype, matrix_size, `protocol_id`,
  achieved/peak TFLOPS, peak_utilization_pct, reliability, 환경(driver/torch/cuda),
  telemetry_summary, `payload_hash`, `signature`, 공유용 `verify_code`(`M-XXXX-XXXX`).

## API

### 인증 — `/api/auth`
| Method | Path | Auth | 설명 |
|---|---|---|---|
| POST | `/signup` | – | 계정 생성 + 토큰 |
| POST | `/login` | – | 이메일·비밀번호 → 토큰 |
| POST | `/logout` | ✔ | `token_version` 증가 → 기존 토큰 전부 무효화 |
| GET | `/me` | ✔ | 현재 사용자 |

로그아웃은 클라이언트 토큰 삭제가 아니라 **서버측**에서 강제된다. 각 사용자의
`token_version`이 모든 토큰에 `tv`로 박혀 있고, 로그아웃이 이를 증가시키면 이전
토큰은 다음 요청에서 검증에 실패한다.

### 기기 — `/api/devices`
| Method | Path | Auth | 설명 |
|---|---|---|---|
| POST | `/register` | ✔ | `fingerprint`(GPU UUID의 **클라이언트측** 해시, 원본은 서버에 안 옴)로 기기 등록. 공유용 `public_code` 반환. (owner, fingerprint) 기준 멱등 |
| GET | `` | ✔ | 내 기기 목록 |

### 측정 · 검증 — `/api/measurements`, `/api/verify`
| Method | Path | Auth | 설명 |
|---|---|---|---|
| POST | `/api/measurements` | ✔ | 내 기기의 측정 제출. 핵심값을 해시하고 기기 시크릿으로 HMAC-SHA256 서명, 공유용 `verify_code` 반환 |
| GET | `/api/measurements` | ✔ | 내 측정 목록 |
| GET | `/api/verify/{verify_code}` | – (공개) | 한 결과의 위조 불가 정본 조회 |
| GET | `/api/verify/device/{public_code}` | – (공개) | 한 기기의 모든 검증된 결과 |

**진위 증명 원리.** 서버가 진실의 원천이다. 검증 코드(또는 기기 코드)를 받은
상대가 공개 verify 엔드포인트를 호출해 정본 수치를 서버에서 직접 읽는다. 공유된
리포트·스크린샷·PDF가 verify 결과와 다르면 위조다. HMAC 서명이 각 결과를 그것을
만든 특정 기기에 묶는다.

### 성능 분석 — `/api/analytics`
| Method | Path | Auth | 설명 |
|---|---|---|---|
| GET | `/models?protocol_id=` | – | 모델별 count·avg·median·p10·p90·max TFLOPS |
| GET | `/leaderboard?gpu_name=&protocol_id=&limit=` | – | 상위 결과 |
| GET | `/me/percentile?measurement_id=` | ✔ | 같은 GPU+프로토콜에서 내 결과의 백분위 |

**비교 가능성.** 측정 엔진과 동일한 규칙 — 같은 `protocol_id`이고 `reliability ==
"valid"`인 결과끼리만 모은다. 서로 다른 워크로드의 수치는 절대 비교하지 않는다.

## 데스크톱 연동

- **로그인 게이트**: `desktop/app.py`의 `_run`이 창을 띄우기 전에 로그인/회원가입
  다이얼로그(`auth_dialog.py`)를 보여준다. 저장된 토큰이 있으면 조용히 자동 로그인
  (`auth_store.py`). "오프라인으로 계속"으로 기록·공유 없이 사용도 가능하다.
- **계정바**: `auth_flow.install_account_bar`가 창 상태바에 이름 + 로그아웃(오프라인이면
  로그인) 버튼을 주입한다. 메인 윈도우 클래스는 수정하지 않는다. 세션을
  `window.auth_session`에 저장해 업로드가 토큰에 접근한다.
- **결과 업로드**: GPU Check 결과 화면의 "결과 기록 · 공유(진위 증명)" 카드에서
  버튼을 누르면 GPU UUID를 해시해 기기를 자동 등록하고 측정을 제출한 뒤, 검증 코드와
  확인 링크를 화면에 표시한다. valid 측정만 기록하며 UUID 원본은 전송하지 않는다.

## 실행

```bash
cd application/backend
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload                    # http://127.0.0.1:8000/docs
```

데스크톱 앱은 기본으로 `http://127.0.0.1:8000`에 연결한다(`GPUPERF_API_URL`로 변경).

## 설정 (환경 변수)

| 변수 | 기본값 | 비고 |
|---|---|---|
| `GPUPERF_SECRET_KEY` | 개발용 키 | **운영에선 랜덤 ≥32바이트로 설정.** 회전 시 모든 토큰 무효화 |
| `GPUPERF_DATABASE_URL` | `sqlite:///./gpuperf.db` | 임의 SQLAlchemy URL(예: Postgres) |
| `GPUPERF_TOKEN_TTL_MIN` | `43200` (30일) | 액세스 토큰 수명 |
| `GPUPERF_CORS_ORIGINS` | `*` | 콤마 구분 허용 목록 또는 `*` |
| `GPUPERF_API_URL` (앱) | `http://127.0.0.1:8000` | 데스크톱이 연결할 서버 주소 |

## 후속 작업

- 결과 화면에 "내 백분위 / 모델 평균 대비" 표시.
- GPU Ops 업로드 연동. Alembic 마이그레이션. 운영 배포 및 시크릿 구성.
