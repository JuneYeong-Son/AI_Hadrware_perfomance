# 사용자 GPU 정보

## 현재 사용 GPU: NVIDIA GeForce RTX 3060 Ti

> 사용자는 "RTX 3060"으로 알고 있었으나 `nvidia-smi` 조회 결과 실제로는 **3060 Ti** 모델.

### 정적 스펙 (2026-07-09 조회)

| 항목 | 값 |
|------|-----|
| 모델명 | NVIDIA GeForce RTX 3060 Ti |
| 드라이버 버전 | 576.52 |
| CUDA 버전 | 12.9 |
| VRAM | 8192 MiB (8 GB) |
| 전력 한계(Power Limit) | 220 W |
| 그래픽 클럭 최대 | 2100 MHz |
| 메모리 클럭 최대 | 7001 MHz |
| PCIe | Gen4 x16 지원 (유휴 시 Gen1로 다운클럭) |
| 디스플레이 모델 | WDDM |

### 측정 시점 값 (유휴 상태, 참고용)

| 항목 | 값 |
|------|-----|
| 온도 | 35°C |
| GPU 가동률 | 10% |
| 전력 소비 | ~22 W |
| 그래픽 클럭(현재) | 210 MHz |
| 메모리 클럭(현재) | 405 MHz |
| VRAM 사용 | 561 MiB / 8192 MiB |

## 수집 방법

NVIDIA GPU이므로 `nvidia-smi` 사용 가능. CSV로 파싱하기 좋은 형태:

```powershell
nvidia-smi --query-gpu=name,driver_version,memory.total,temperature.gpu,utilization.gpu,power.draw,power.limit,clocks.gr,clocks.max.gr,clocks.mem,clocks.max.mem,pcie.link.gen.current,pcie.link.width.current --format=csv
```

- 프로그램에서 수집 시: Python `pynvml`(=NVIDIA NVML 바인딩) 또는 `nvidia-smi` CSV 출력 파싱.
- 실시간 모니터링(발열·가동률·클럭)도 같은 도구로 주기적 폴링 가능.
