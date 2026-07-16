# 배포 가이드 (Distribution)

다른 사람이 앱을 설치해서 쓰려면 **두 가지**가 필요합니다.

1. **백엔드 서버**를 인터넷에 호스팅 (계정·진위증명·성능분석의 공용 저장소)
2. **데스크톱 앱**을 설치파일로 패키징하고, 위 서버를 바라보게 설정

---

## 1단계 — 백엔드 호스팅 (Render, 무료 티어)

저장소 루트의 [`render.yaml`](../render.yaml)이 배포를 자동화합니다.

1. 이 저장소를 GitHub에 푸시한다(이미 되어 있음).
2. [render.com](https://render.com) 로그인 → **New +** → **Blueprint** → 이 저장소 선택.
3. Render가 `render.yaml`을 읽어 Docker 이미지를 빌드하고 `GPUPERF_SECRET_KEY`
   (자동 랜덤)를 설정한다.
4. **DB 연결**: Render 무료 Postgres는 계정당 1개 제한이라 블루프린트가 DB를
   자동 생성하지 않는다. 배포 중/후에 서비스의 **Environment**에서
   `GPUPERF_DATABASE_URL` 값에 Postgres 연결 문자열을 넣는다.
   - 기존 Render Postgres가 있으면 그 **Internal Database URL**을 복사해 넣기, 또는
   - [neon.tech](https://neon.tech)·[supabase.com](https://supabase.com)에서 무료
     Postgres를 새로 만들어 그 URL 넣기.
   - 비워두면 SQLite로 동작하지만 재배포 때마다 데이터가 초기화된다(테스트용만).
5. 배포되면 서비스 URL을 확인한다. 예: `https://gpu-perf-api.onrender.com`
6. 브라우저로 `https://<서비스URL>/docs`가 열리면 성공.

> Railway·Fly.io 등 다른 플랫폼도 같은 [`Dockerfile`](../application/backend/Dockerfile)로
> 배포할 수 있다. 환경변수 `GPUPERF_SECRET_KEY`(≥32바이트 랜덤)와 Postgres용
> `DATABASE_URL`만 주면 된다. (`postgres://`는 자동으로 정규화됨)

> 로컬 도커로 확인만 하려면:
> ```bash
> cd application/backend
> docker build -t gpu-perf-api .
> docker run -p 8000:8000 -e GPUPERF_SECRET_KEY=$(openssl rand -hex 24) gpu-perf-api
> ```

---

## 2단계 — 데스크톱 앱 패키징 (PyInstaller)

⚠️ **PyInstaller는 크로스 컴파일이 안 됩니다.** Windows용 `.exe`는 Windows에서,
macOS용 `.app`은 Mac에서 각각 빌드해야 합니다.

### 서버 주소 설정 방법 (재컴파일 불필요)
앱은 실행 파일 옆의 `gpuperf.config.json`에서 서버 주소를 읽습니다. 빌드 스크립트가
[`gpuperf.config.example.json`](gpuperf.config.example.json)을 복사해 넣으니, 값만
1단계에서 얻은 URL로 바꾸면 됩니다:
```json
{ "api_url": "https://gpu-perf-api.onrender.com" }
```
(환경변수 `GPUPERF_API_URL`이 있으면 그 값이 우선합니다.)

### Windows 빌드
```powershell
# 작은 빌드 (정보·센서·계정만, 벤치마크 비활성):
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1

# 풀 빌드 (torch+CUDA 포함 → 용량 큼 ~2-4GB, 벤치마크 동작):
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -WithTorch
```
결과: `dist\GPU Check\`, `dist\GPU Ops\` 폴더. 각 폴더를 zip으로 압축해 배포한다.
사용자는 압축을 풀고 `GPU Check.exe`를 실행, `gpuperf.config.json`에서 서버 주소 확인.

### macOS 빌드
```bash
bash packaging/build_macos.sh
```
결과: `dist/GPU Check.app`, `dist/GPU Ops.app`.

> **torch(벤치마크 엔진) 참고**: achieved TFLOPS 측정은 NVIDIA CUDA용 torch가
> 필요합니다. 그래서 `-WithTorch` 풀 빌드는 Windows(+NVIDIA GPU) 대상에서만
> 의미가 있고 용량이 큽니다. macOS는 CUDA가 없어 벤치마크가 동작하지 않으며,
> 앱은 GPU 정보·센서·계정·검증 코드 확인 용도로 쓰입니다.

---

## 3단계 — 설치파일(installer)로 감싸기 (선택)

zip 배포 대신 더 깔끔한 설치 경험을 원하면:

- **Windows**: [Inno Setup](https://jrsoftware.org/isinfo.php)으로 `dist\GPU Check\`를
  감싸 `Setup.exe`를 만든다.
- **macOS**: [`create-dmg`](https://github.com/create-dmg/create-dmg)로 `.app`을
  `.dmg`로 패키징한다. (배포 시 코드 서명/공증이 없으면 Gatekeeper 경고가 뜬다.)

---

## 사용자 관점 요약

1. 배포자가 준 zip(또는 설치파일)을 풀고 `GPU Check`를 실행한다.
2. 첫 화면에서 회원가입/로그인한다(서버가 1단계에서 호스팅되어 있어야 함).
3. 벤치마크를 돌리고 "결과 서버에 기록"을 누르면 공유용 검증 코드가 나온다.
4. 그 코드를 받은 사람은 `https://<서버>/api/verify/<코드>`에서 진위를 확인한다.
