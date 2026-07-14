from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from gpu_measurer.collector import CollectorError, get_default_collector
from gpu_measurer.reporting import write_log
from gpu_measurer.serialization import redact_sensitive_data, response_envelope
from gpu_measurer.service import build_service


ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GPU Measurer desktop and report utility")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--health", action="store_true", help="check collector availability")
    actions.add_argument("--list", action="store_true", help="list detected GPUs")
    actions.add_argument("--inspect", action="store_true", help="inspect one GPU")
    actions.add_argument("--snapshot", action="store_true", help="read one sensor snapshot")
    actions.add_argument("--report", action="store_true", help="run a timed measurement")
    actions.add_argument("--validate", action="store_true", help="run a controlled GPU workload and diagnose it")
    actions.add_argument("--baseline", action="store_true", help="validate and store the result as a baseline")
    actions.add_argument("--history", action="store_true", help="read stored measurement history for a device")
    actions.add_argument("--overview", action="store_true", help="print a readable console overview (default)")
    parser.add_argument("--ui", action="store_true", help="launch the developer Tkinter GUI")
    parser.add_argument("--gpu", type=int, default=0, help="GPU index")
    parser.add_argument("--duration", type=float, default=5.0, help="measurement duration in seconds")
    parser.add_argument("--interval", type=float, default=1.0, help="sample interval in seconds")
    parser.add_argument("--dtype", default="float32", help="workload dtype (float32, float16, bfloat16)")
    parser.add_argument("--size", type=int, default=4096, help="square matrix size for the GEMM workload")
    parser.add_argument("--warmup", type=int, default=20, help="workload warmup iterations")
    parser.add_argument("--iterations", type=int, default=300, help="measured workload iterations")
    parser.add_argument("--output", type=Path, help="report output path")
    parser.add_argument("--json", action="store_true", help="write a versioned JSON response to stdout")
    parser.add_argument("--no-save", action="store_true", help="do not write a report file")
    parser.add_argument("--smoke-test", action="store_true", help="create and close the UI without entering the event loop")
    return parser


def _ensure_utf8_streams() -> None:
    # The Windows console defaults to a legacy code page; force UTF-8 so the
    # Korean report text and JSON are not mojibake.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _write_json(payload: object, *, stream: object = sys.stdout) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream)


def _fmt(value: object, unit: str = "") -> str:
    if value is None or value == "":
        return "확인 불가"
    return f"{value}{unit}"


def _print_overview(service, provider: str, gpu_index: int) -> None:
    """Readable console summary shown when main.py runs with no action."""
    devices = service.list_devices()
    print("GPU Measurer — 개요")
    print(f"provider: {provider} | GPU {len(devices)}대 감지")

    print("\n[감지된 GPU]")
    if not devices:
        print("  감지된 GPU가 없습니다.")
        return
    for device in devices:
        print(f"  {device['index']}  {device['name']}")

    # Detailed view of the selected GPU.
    try:
        info = service.inspect_device(gpu_index)
    except CollectorError as error:
        print(f"\nGPU {gpu_index} 정보를 읽을 수 없습니다: {error}")
        return
    gpu = info["gpu"]
    print(f"\n[장치 상세]  GPU {gpu_index}")
    print(f"  이름          {gpu.get('name')}")
    print(f"  VRAM          {_fmt(gpu.get('memory.total'), ' MiB')}")
    print(f"  driver        {_fmt(gpu.get('driver_version'))}")
    print(f"  VBIOS         {_fmt(gpu.get('vbios_version'))}")
    print(f"  compute cap   {_fmt(gpu.get('compute_cap'))}")
    print(f"  max clock     {_fmt(gpu.get('clocks.max.graphics'), ' MHz')} graphics")

    try:
        _snapshot, snap = service.current_snapshot(gpu_index)
        values = snap["values"]
        print(f"\n[현재 상태]  {snap['timestamp']}")
        print(f"  온도            {_fmt(values.get('temperature_c'), ' °C')}")
        print(f"  GPU 사용률      {_fmt(values.get('gpu_utilization_pct'), ' %')}")
        print(
            f"  전력            {_fmt(values.get('power_draw_w'))} / "
            f"{_fmt(values.get('power_limit_w'), ' W')}"
        )
        print(f"  graphics clock  {_fmt(values.get('graphics_clock_mhz'), ' MHz')}")
        print(f"  memory clock    {_fmt(values.get('memory_clock_mhz'), ' MHz')}")
        print(f"  perf state      {_fmt(values.get('performance_state'))}")
        print(f"  throttle        {_fmt(values.get('throttle_reasons_active'))}")
    except CollectorError as error:
        print(f"\n[현재 상태] 센서를 읽을 수 없습니다: {error}")

    benchmark = info.get("benchmark", {})
    print("\n[참고 벤치마크]  (정적 참고값이며 현재 장비의 측정값이 아닙니다)")
    if benchmark.get("exact_match") and benchmark.get("passmark"):
        passmark = benchmark["passmark"]
        print(f"  PassMark G3Dmark: {passmark.get('G3Dmark', '확인 불가')}")
    else:
        suggestions = benchmark.get("suggestions", [])
        if suggestions:
            names = ", ".join(item["name"] for item in suggestions[:3])
            print(f"  정확히 일치하는 참고 데이터가 없습니다. 유사: {names}")
        else:
            print("  참고 데이터가 없습니다.")

    print("\n[측정 이력]")
    history = service.read_gpu_history(gpu_index)
    if history["record_count"] == 0:
        print("  아직 저장된 기준선이 없습니다. `python main.py --baseline`으로 저장하세요.")
    else:
        latest = history["records"][-1]
        latest_tflops = latest.get("achieved_tflops")
        latest_str = f"{latest_tflops:.3f}" if isinstance(latest_tflops, (int, float)) else "확인 불가"
        print(
            f"  저장된 기준선 {history['record_count']}건 | "
            f"최근 achieved {latest_str} TFLOPS "
            f"(protocol {latest.get('protocol_id')})"
        )
        delta = history["comparison"].get("delta")
        if delta:
            print(f"  최근 변화: {delta['relative_pct']:+.2f}% (같은 protocol 비교)")

    print("\n[다음 명령]")
    print("  python main.py --validate     통제된 GPU workload 실행 및 진단")
    print("  python main.py --baseline     결과를 기준선으로 저장")
    print("  python main.py --history      저장된 측정 이력 조회")
    print("  python main.py --snapshot     현재 센서 스냅샷 (JSON)")
    print("  python main.py --ui           개발용 GUI 실행")


def main() -> int:
    _ensure_utf8_streams()
    args = build_parser().parse_args()
    if args.smoke_test:
        import tkinter as tk
        from gpu_measurer.ui import GpuMeasurerApp

        root = tk.Tk()
        root.withdraw()
        GpuMeasurerApp(root)
        root.update_idletasks()
        root.destroy()
        print("UI smoke test passed")
        return 0

    if args.ui:
        from gpu_measurer.ui import launch

        launch()
        return 0

    # With no explicit action, show a readable console overview instead of the
    # developer GUI (use --ui for the GUI).
    if not any(
        (
            args.health,
            args.list,
            args.inspect,
            args.snapshot,
            args.report,
            args.validate,
            args.baseline,
            args.history,
            args.overview,
        )
    ):
        args.overview = True

    provider = "unavailable"
    try:
        collector = get_default_collector()
        provider = collector.provider_name
        service = build_service(ROOT, collector)

        if args.overview:
            _print_overview(service, provider, args.gpu)
            return 0
        if args.health:
            devices = service.list_devices()
            data = {"status": "ready", "device_count": len(devices)}
        elif args.list:
            data = {"devices": service.list_devices()}
        elif args.inspect:
            data = service.inspect_device(args.gpu)
        elif args.snapshot:
            _snapshot, data = service.current_snapshot(args.gpu)
        elif args.validate or args.baseline:
            from gpu_measurer.models import WorkloadSpec

            spec = WorkloadSpec(
                dtype=args.dtype,
                size=args.size,
                warmup_iterations=args.warmup,
                measured_iterations=args.iterations,
            )
            if args.baseline:
                result, data = service.baseline_gpu(args.gpu, spec)
            else:
                result, data = service.validate_gpu(args.gpu, spec)
            report_path = None
            if not args.no_save:
                output = args.output or (
                    ROOT
                    / "application"
                    / "reports"
                    / f"gpu-validation-{datetime.now():%Y%m%d-%H%M%S}.txt"
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(service.text_report(result), encoding="utf-8")
                report_path = str(output)
            data["report_path"] = report_path
            data["shared_report"] = service.shared_report(result)
        elif args.history:
            data = service.read_gpu_history(args.gpu)
        else:
            result, measurement = service.measure(
                args.gpu,
                args.duration,
                args.interval,
            )
            report_path = None
            if not args.no_save:
                output = args.output or (
                    ROOT
                    / "application"
                    / "reports"
                    / f"gpu-measurement-{datetime.now():%Y%m%d-%H%M%S}.log"
                )
                report_path = str(write_log(result, output))
            data = {"measurement": measurement, "report_path": report_path}

        json_actions = (
            args.list or args.inspect or args.snapshot or args.health
            or args.validate or args.baseline or args.history
        )
        if args.json or json_actions:
            _write_json(response_envelope(redact_sensitive_data(data), provider))
        else:
            print(data["report_path"] or "Measurement completed without saving")
        return 0
    except (CollectorError, ValueError, OSError) as error:
        payload = response_envelope(
            None,
            provider,
            ok=False,
            error={"type": type(error).__name__, "message": str(error)},
        )
        if args.json:
            _write_json(payload, stream=sys.stderr)
        else:
            print(f"GPU Measurer error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
