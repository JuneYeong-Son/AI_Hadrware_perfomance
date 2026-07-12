# GPU Measurer

Windows에서 NVIDIA GPU 정보와 실시간 센서를 확인하고 로컬 측정 리포트를 생성하는 데스크톱 도구입니다. Python 표준 라이브러리와 NVIDIA 드라이버의 `nvidia-smi`만 사용합니다.

## 실행

```powershell
python application/main.py
```

## 리포트 생성

```powershell
python application/main.py --report --duration 5 --interval 1
```

## 웹·AI 연동용 JSON

모든 JSON 응답은 `schema_version`, `ok`, `provider`, `data`, `error` 필드를 가진다.

```powershell
python application/main.py --health --json
python application/main.py --list --json
python application/main.py --inspect --gpu 0 --json
python application/main.py --snapshot --gpu 0 --json
python application/main.py --report --gpu 0 --duration 5 --interval 1 --json --no-save
```

`--no-save`를 사용하면 측정은 실행하지만 파일을 생성하지 않아 읽기 중심의 에이전트 호출에 적합하다.

## 테스트

```powershell
python -m unittest discover -s application/tests -v
python application/main.py --smoke-test
```

지원 기능은 GPU 선택, 기본 사양, 실시간 센서, 최소·최대·평균값, 센서 CSV 기록, 고급 정보 분류, 정적 벤치마크 CSV 매칭, 로컬 검증 로그입니다.
