# 프로젝트 개요: AI Hardware Performance

- 상태: GPU Measurer MVP 구현 및 확장 기반 준비
- 최종 갱신: 2026-07-13

## 목적

사용자의 GPU 상태를 로컬에서 수집하고, 실제 센서와 정적 비교 데이터를 함께 사용해 현재 성능 상태를 설명한다. 장기적으로는 데스크톱 UI, 웹 UI, AI 에이전트가 동일한 측정 서비스를 공유하도록 한다.

## 현재 제공 기능

- GPU 이름, UUID, 드라이버, VBIOS, PCI, VRAM, 최대 클럭 조회
- 온도, 사용률, 메모리, 전력, 클럭, P-state 실시간 수집
- 센서 현재·최소·최대·평균값 표시
- 센서 CSV와 시간 측정 로그 생성
- PassMark 및 Compute API CSV의 정확한 모델 매칭
- Graphics Card, Sensors, Advanced, Validation 데스크톱 UI
- `health`, `list`, `inspect`, `snapshot`, `report` JSON CLI

## 확장 구조

```text
제조사 수집기
  NVIDIA nvidia-smi / NVML
  AMD AMD SMI (계획)
  Intel Level Zero Sysman (계획)
        ↓
GpuCollector 공통 계약
        ↓
GpuMeasurementService
        ↓
Desktop UI | JSON CLI | Web API (계획) | MCP tools (계획)
```

수집기와 사용자 인터페이스 사이에 서비스 계층을 둬 웹이나 에이전트가 Tk UI를 직접 호출하지 않도록 한다.

## 데이터 원칙

- 정적 GPU 사양·비교 점수와 현재 컴퓨터의 동적 센서를 구분한다.
- 모델명이 정확히 일치하지 않으면 다른 GPU의 점수를 현재 GPU 점수로 사용하지 않는다.
- 측정 결과에는 시각, 표본 수, 간격, 환경과 원시 샘플을 함께 남긴다.
- 자동화 출력은 `schema_version`이 있는 JSON 계약으로 제공한다.

## 다음 단계

웹 UI와 AI 에이전트 도구 호출 개발은 [웹 및 AI 에이전트 개발 백로그](../backlogs/web-and-agent-development.md)에 정의한다.
