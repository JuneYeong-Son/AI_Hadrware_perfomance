# 비교용 GPU 데이터 소스 (Cold Start 해결)

## 문제

성능을 "다른 GPU / 신제품 대비"로 비교하려면 기준이 되는 다른 GPU들의 데이터가 필요하다.
서비스 초기엔 이 데이터가 없는 **cold start 문제**가 발생한다.
→ 외부의 공개 데이터를 미리 가져와(seed) 백엔드에 넣어두는 방식으로 해결한다.

## 채택: `dbgpu` (스펙 비교, 1순위) ✅ 검증 완료

- 설치: `pip install "dbgpu[tabulate,fuzz]"` (약 170KB, 오프라인 DB 내장 → 스크래핑 불필요)
- 2000개 이상 GPU, GPU당 60개+ 필드
- 데이터 출처: TechPowerUp (업계에서 가장 신뢰받는 GPU 스펙 DB)
- 라이선스: **MIT** (자유 사용)
- 주요 필드: `single_float_performance_gflop_s`(FP32 성능), `memory_bandwidth_gb_s`, `thermal_design_power_w`, `memory_size_gb`, `architecture`, `release_date`, 텐서/RT 코어 수, 클럭 등

### 사용 예 (검증됨)
```python
from dbgpu import GPUDatabase
db = GPUDatabase.default()
g = db.search("GeForce RTX 3060 Ti")   # fuzzy 검색 지원
print(g.single_float_performance_gflop_s, g.memory_bandwidth_gb_s, g.thermal_design_power_w)
```

### 검증 결과 (2026-07-09, 내 RTX 3060 Ti = 16.2 TFLOPS 기준)
| GPU | 출시 | TFLOPS | 대역폭(GB/s) | TDP | 3060 Ti 대비 |
|-----|------|--------|------|-----|------|
| RTX 3060 Ti | 2020 | 16.2 | 448 | 200 | 1.00x |
| RTX 4060 | 2023 | 15.1 | 272 | 115 | 0.93x |
| RTX 4070 | 2023 | 29.1 | 504 | 200 | 1.80x |
| RTX 5070 | 2025 | 30.9 | 672 | 250 | 1.91x |
| RTX 4090 | 2022 | 82.6 | 1010 | 450 | 5.10x |

→ **스펙(이론 성능) 기반 비교는 dbgpu만으로 즉시 가능.**

## 보완: 실사용 벤치마크 점수 (2순위, 선택)

dbgpu는 이론 스펙이므로, 실제 게임/워크로드 점수는 별도 소스로 보완 가능.

- **Kaggle - GPU Benchmarks (alanjo/gpu-benchmarks)**: PassMark G3D Mark 실사용 점수 CSV, 매일 업데이트, 무료 다운로드.
  - https://www.kaggle.com/datasets/alanjo/gpu-benchmarks
- **PassMark 공식 데이터 라이선스**: 상업용, CSV 덤프 (유료).
  - https://www.passmark.com/services/market-analysis.php

## 정리: 데이터 전략

1. **기준 데이터(seed)**: dbgpu의 GPU 스펙을 백엔드 DB에 적재 → 다른/신제품 GPU 비교 기준.
2. **(선택) 실사용 점수**: Kaggle PassMark CSV를 병합해 실측 벤치마크 점수 비교 보강.
3. **사용자 GPU 실측**: `nvidia-smi`/`pynvml`로 내 GPU의 실시간 값(발열·클럭·가동률) + 자체 벤치마크 점수 수집.
4. **비교**: 사용자 실측 ↔ seed 데이터로 상대 수준 산출.

---

## 참고 출처
- [dbgpu (GitHub, MIT)](https://github.com/painebenjamin/dbgpu)
- [PassMark GPU Mega Page](https://www.videocardbenchmark.net/GPU_mega_page.html)
- [PassMark 데이터 라이선스](https://www.passmark.com/services/market-analysis.php)
- [Kaggle GPU Benchmarks 데이터셋](https://www.kaggle.com/datasets/alanjo/gpu-benchmarks)
- [TechPowerUp 데이터베이스 라이선스](https://www.techpowerup.com/database-licensing/)

_최초 작성: 2026-07-09_
