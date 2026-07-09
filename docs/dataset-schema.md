# 데이터셋 구조 (Dataset Schema)

우리 서비스가 다루는 데이터는 두 종류로 나뉜다.

1. **정적 스펙 데이터** — 비교 기준(seed). `dbgpu`에서 가져옴. GPU 모델별로 고정.
2. **동적 실측 데이터** — 사용자 GPU를 실제로 측정. `nvidia-smi`/`pynvml`로 수집. 시점마다 변함.

---

## 1. 정적 스펙 데이터 (dbgpu, GPU당 54개 필드)

출처: TechPowerUp (via `dbgpu`, MIT). GPU 모델 하나당 아래 필드를 가진다.
아래는 RTX 3060 Ti 실제 값 예시.

### 식별
| 필드 | 예시 | 설명 |
|------|------|------|
| `manufacturer` | NVIDIA | 제조사 |
| `name` | GeForce RTX 3060 Ti | 모델명 |
| `gpu_name` | GA104 | 칩 코드명 |
| `generation` | GeForce 30 | 세대 |
| `tpu_id` / `tpu_url` | c3681 / techpowerup… | 원본 출처 |

### 아키텍처·제조
| 필드 | 예시 |
|------|------|
| `architecture` | Ampere |
| `foundry` | Samsung |
| `process_size_nm` | 8 |
| `transistor_count_m` | 17400 |
| `transistor_density_k_mm2` | 44400 |
| `die_size_mm2` | 392 |
| `chip_package` | BGA-2713 |
| `release_date` | 2020-12-01 |

### 클럭
| 필드 | 예시 |
|------|------|
| `base_clock_mhz` | 1410 |
| `boost_clock_mhz` | 1665 |
| `memory_clock_mhz` | 1750 |

### 메모리
| 필드 | 예시 |
|------|------|
| `memory_size_gb` | 8 |
| `memory_type` | GDDR6 |
| `memory_bus_bits` | 256 |
| `memory_bandwidth_gb_s` | 448 |

### 연산 유닛
| 필드 | 예시 | 설명 |
|------|------|------|
| `shading_units` | 4864 | CUDA 코어 수 |
| `tensor_cores` | 152 | 텐서 코어 (AI 연산) |
| `ray_tracing_cores` | 38 | RT 코어 |
| `streaming_multiprocessors` | 38 | SM 수 |
| `texture_mapping_units` | 152 | TMU |
| `render_output_processors` | 80 | ROP |
| `l1_cache_kb` | 128 | L1 캐시 |
| `l2_cache_mb` | 4 | L2 캐시 |

### 전력·물리
| 필드 | 예시 |
|------|------|
| `thermal_design_power_w` | 200 |
| `suggested_psu_w` | 550 |
| `power_connectors` | 1x 12-pin |
| `board_length_mm` | 242 |
| `board_slot_width` | Dual-slot |
| `display_connectors` | 1x HDMI 2.1, 3x DP 1.4a |
| `bus_interface` | PCIe 4.0 x16 |

### API 지원 (major.minor로 저장됨)
`directx` 12.2 · `opengl` 4.6 · `vulkan` 1.4 · `opencl` 3.0 · `cuda` 8.6 · `shader_model` 6.8

### 성능 지표 (⭐ 비교의 핵심)
| 필드 | 예시 | 설명 |
|------|------|------|
| `single_float_performance_gflop_s` | 16200 | FP32 이론 성능 |
| `half_float_performance_gflop_s` | 16200 | FP16 |
| `double_float_performance_gflop_s` | 253 | FP64 |
| `pixel_rate_gpixel_s` | 133.2 | 픽셀 처리율 |
| `texture_rate_gtexel_s` | 253.1 | 텍스처 처리율 |

---

## 2. 동적 실측 데이터 (nvidia-smi / pynvml)

사용자 GPU를 실제로 측정. 측정 시점마다 값이 변한다.

| 필드 | 예시(유휴) | 설명 |
|------|------|------|
| `timestamp` | 2026-07-09T14:43 | 측정 시각 |
| `name` | RTX 3060 Ti | 측정된 GPU |
| `temperature_c` | 35 | 발열 |
| `utilization_pct` | 10 | GPU 가동률 |
| `power_draw_w` | 22 | 실시간 전력 소비 |
| `clock_graphics_mhz` | 210 | 현재 코어 클럭 |
| `clock_memory_mhz` | 405 | 현재 메모리 클럭 |
| `memory_used_mib` | 561 | VRAM 사용량 |
| `pcie_gen` / `pcie_width` | 1 / 16 | 현재 PCIe 링크 |
| `driver_version` | 576.52 | 드라이버 |

---

## 3. 우리 서비스가 저장할 스키마 (초안)

세 테이블로 나누는 것을 제안:

### `gpu_specs` — 정적 스펙 (dbgpu seed 적재)
dbgpu의 54개 필드를 그대로 저장. 비교 기준. (신제품/타 GPU 포함)

### `measurements` — 동적 실측 (측정할 때마다 1행)
위 2번 필드들 + 사용자 식별자. 시계열로 쌓임.

### `benchmark_results` — 벤치마크 점수 (2단계)
| 필드 | 설명 |
|------|------|
| `id`, `timestamp`, `gpu_name` | 식별 |
| `benchmark_name` | 어떤 벤치마크인지 |
| `score` | 측정 점수 |
| `max_temp_c`, `avg_util_pct`, `avg_clock_mhz` | 벤치 중 발열·가동률·속도 |

→ 비교 결과("내 GPU는 5070의 52% 수준")는 저장값이 아니라, `measurements`/`benchmark_results`를 `gpu_specs`와 대조해 계산.

---

_최초 작성: 2026-07-09 (dbgpu 실측 기반)_
