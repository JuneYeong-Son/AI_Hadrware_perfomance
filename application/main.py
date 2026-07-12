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
    parser.add_argument("--gpu", type=int, default=0, help="GPU index")
    parser.add_argument("--duration", type=float, default=5.0, help="measurement duration in seconds")
    parser.add_argument("--interval", type=float, default=1.0, help="sample interval in seconds")
    parser.add_argument("--output", type=Path, help="report output path")
    parser.add_argument("--json", action="store_true", help="write a versioned JSON response to stdout")
    parser.add_argument("--no-save", action="store_true", help="do not write a report file")
    parser.add_argument("--smoke-test", action="store_true", help="create and close the UI without entering the event loop")
    return parser


def _write_json(payload: object, *, stream: object = sys.stdout) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream)


def main() -> int:
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

    if not any((args.health, args.list, args.inspect, args.snapshot, args.report)):
        from gpu_measurer.ui import launch

        launch()
        return 0

    provider = "unavailable"
    try:
        collector = get_default_collector()
        provider = collector.provider_name
        service = build_service(ROOT, collector)

        if args.health:
            devices = service.list_devices()
            data = {"status": "ready", "device_count": len(devices)}
        elif args.list:
            data = {"devices": service.list_devices()}
        elif args.inspect:
            data = service.inspect_device(args.gpu)
        elif args.snapshot:
            _snapshot, data = service.current_snapshot(args.gpu)
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

        if args.json or args.list or args.inspect or args.snapshot or args.health:
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
