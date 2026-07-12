from __future__ import annotations

import csv
import threading
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .benchmarks import BenchmarkRepository
from .collector import CollectorError, get_default_collector
from .models import BenchmarkMatch, GpuDevice, SensorSnapshot
from .reporting import write_log
from .service import GpuMeasurementService


SENSOR_LABELS = {
    "temperature_c": ("GPU Temperature", "C"),
    "gpu_utilization_pct": ("GPU Load", "%"),
    "memory_controller_pct": ("Memory Controller", "%"),
    "memory_used_mib": ("Memory Used", "MiB"),
    "memory_free_mib": ("Memory Free", "MiB"),
    "power_draw_w": ("Board Power Draw", "W"),
    "power_limit_w": ("Power Limit", "W"),
    "graphics_clock_mhz": ("GPU Clock", "MHz"),
    "memory_clock_mhz": ("Memory Clock", "MHz"),
    "fan_speed_pct": ("Fan Speed", "%"),
    "encoder_utilization_pct": ("Video Encode", "%"),
    "decoder_utilization_pct": ("Video Decode", "%"),
    "performance_state": ("Performance State", ""),
}


class GpuMeasurerApp:
    BG = "#f4f6f8"
    SURFACE = "#ffffff"
    INK = "#18232f"
    MUTED = "#66717e"
    LINE = "#d9e0e6"
    GREEN = "#2f9e65"
    GREEN_DARK = "#23784d"
    BLUE = "#2775ca"
    AMBER = "#d98b22"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.repo_root = Path(__file__).resolve().parents[2]
        self.reports_dir = self.repo_root / "application" / "reports"
        self.collector = get_default_collector()
        self.benchmarks = BenchmarkRepository(
            self.repo_root / "data" / "static" / "benchmarks"
        )
        self.service = GpuMeasurementService(self.collector, self.benchmarks)
        self.devices: list[GpuDevice] = []
        self.current_info: dict[str, str] = {}
        self.current_match = BenchmarkMatch("")
        self.sensor_history: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=120))
        self.latest_snapshot: SensorSnapshot | None = None
        self.collecting = False
        self.sensor_logging = False
        self.sensor_log_rows: list[SensorSnapshot] = []
        self.ui_events: Queue[tuple[str, object]] = Queue()

        self.root.title("GPU Measurer 0.1")
        self.root.geometry("980x720")
        self.root.minsize(880, 640)
        self.root.configure(bg=self.BG)
        self._configure_style()
        self._build_shell()
        self.refresh_devices()
        self.root.after(100, self._drain_ui_events)
        self.root.after(800, self._schedule_sensor_update)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG)
        style.configure("Surface.TFrame", background=self.SURFACE)
        style.configure("TLabel", background=self.BG, foreground=self.INK, font=("Segoe UI", 10))
        style.configure("Surface.TLabel", background=self.SURFACE, foreground=self.INK)
        style.configure("Muted.TLabel", background=self.SURFACE, foreground=self.MUTED)
        style.configure("Title.TLabel", background=self.BG, foreground=self.INK, font=("Segoe UI Semibold", 18))
        style.configure("Subhead.TLabel", background=self.SURFACE, foreground=self.INK, font=("Segoe UI Semibold", 11))
        style.configure("Metric.TLabel", background=self.SURFACE, foreground=self.INK, font=("Segoe UI Semibold", 20))
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=(12, 7))
        style.configure("Accent.TButton", background=self.GREEN, foreground="white", bordercolor=self.GREEN)
        style.map("Accent.TButton", background=[("active", self.GREEN_DARK)])
        style.configure("TNotebook", background=self.BG, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI Semibold", 10), padding=(18, 9), background="#e8edf1")
        style.map("TNotebook.Tab", background=[("selected", self.SURFACE)], foreground=[("selected", self.GREEN_DARK)])
        style.configure("Treeview", background=self.SURFACE, fieldbackground=self.SURFACE, foreground=self.INK, rowheight=28, borderwidth=0)
        style.configure("Treeview.Heading", background="#e9eef2", foreground=self.INK, font=("Segoe UI Semibold", 9), relief="flat")
        style.map("Treeview", background=[("selected", "#dcefe5")], foreground=[("selected", self.INK)])

    def _build_shell(self) -> None:
        header = ttk.Frame(self.root, padding=(20, 15, 20, 10))
        header.pack(fill="x")

        logo = tk.Canvas(header, width=42, height=42, bg=self.BG, highlightthickness=0)
        logo.pack(side="left")
        logo.create_rectangle(5, 5, 37, 37, fill=self.GREEN, outline="")
        logo.create_rectangle(12, 12, 30, 30, fill=self.SURFACE, outline="")
        for offset in (10, 17, 24, 31):
            logo.create_line(offset, 1, offset, 5, fill=self.GREEN_DARK, width=2)
            logo.create_line(offset, 37, offset, 41, fill=self.GREEN_DARK, width=2)
            logo.create_line(1, offset, 5, offset, fill=self.GREEN_DARK, width=2)
            logo.create_line(37, offset, 41, offset, fill=self.GREEN_DARK, width=2)

        title_box = ttk.Frame(header)
        title_box.pack(side="left", padx=(10, 20))
        ttk.Label(title_box, text="GPU Measurer", style="Title.TLabel").pack(anchor="w")
        self.status_label = ttk.Label(title_box, text="Detecting hardware...", foreground=self.MUTED)
        self.status_label.pack(anchor="w")

        ttk.Button(header, text="Refresh", command=self.refresh_devices).pack(side="right")
        self.device_var = tk.StringVar()
        self.device_combo = ttk.Combobox(header, textvariable=self.device_var, state="readonly", width=36)
        self.device_combo.pack(side="right", padx=(0, 10))
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_selected)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        self.overview_tab = ttk.Frame(self.notebook, style="Surface.TFrame", padding=18)
        self.sensors_tab = ttk.Frame(self.notebook, style="Surface.TFrame", padding=18)
        self.advanced_tab = ttk.Frame(self.notebook, style="Surface.TFrame", padding=18)
        self.validation_tab = ttk.Frame(self.notebook, style="Surface.TFrame", padding=18)
        self.notebook.add(self.overview_tab, text="Graphics Card")
        self.notebook.add(self.sensors_tab, text="Sensors")
        self.notebook.add(self.advanced_tab, text="Advanced")
        self.notebook.add(self.validation_tab, text="Validation")
        self._build_overview()
        self._build_sensors()
        self._build_advanced()
        self._build_validation()

        footer = ttk.Frame(self.root, padding=(20, 0, 20, 12))
        footer.pack(fill="x")
        self.footer_label = ttk.Label(footer, text="Local-only hardware inspection", foreground=self.MUTED)
        self.footer_label.pack(side="left")
        ttk.Button(footer, text="Close", command=self.root.destroy).pack(side="right")

    def _build_overview(self) -> None:
        hero = ttk.Frame(self.overview_tab, style="Surface.TFrame")
        hero.pack(fill="x")
        left = ttk.Frame(hero, style="Surface.TFrame")
        left.pack(side="left", fill="x", expand=True)
        self.gpu_name_label = ttk.Label(left, text="No GPU", style="Surface.TLabel", font=("Segoe UI Semibold", 20))
        self.gpu_name_label.pack(anchor="w")
        self.gpu_meta_label = ttk.Label(left, text="", style="Muted.TLabel")
        self.gpu_meta_label.pack(anchor="w", pady=(3, 0))
        self.api_frame = ttk.Frame(hero, style="Surface.TFrame")
        self.api_frame.pack(side="right")

        ttk.Separator(self.overview_tab).pack(fill="x", pady=15)
        metrics = ttk.Frame(self.overview_tab, style="Surface.TFrame")
        metrics.pack(fill="x")
        self.metric_labels: dict[str, ttk.Label] = {}
        for index, (key, title, color) in enumerate([
            ("temperature_c", "Temperature", self.AMBER),
            ("gpu_utilization_pct", "GPU Load", self.BLUE),
            ("memory_used_mib", "VRAM Used", self.GREEN),
            ("power_draw_w", "Power", self.INK),
        ]):
            card = tk.Frame(metrics, bg="#f7f9fa", highlightbackground=self.LINE, highlightthickness=1)
            card.grid(row=0, column=index, padx=(0 if index == 0 else 5, 5), sticky="nsew")
            metrics.columnconfigure(index, weight=1)
            tk.Label(card, text=title, bg="#f7f9fa", fg=self.MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=12, pady=(10, 0))
            label = tk.Label(card, text="--", bg="#f7f9fa", fg=color, font=("Segoe UI Semibold", 18))
            label.pack(anchor="w", padx=12, pady=(2, 10))
            self.metric_labels[key] = label

        content = ttk.Frame(self.overview_tab, style="Surface.TFrame")
        content.pack(fill="both", expand=True, pady=(16, 0))
        specs_box = ttk.Frame(content, style="Surface.TFrame")
        specs_box.pack(side="left", fill="both", expand=True, padx=(0, 12))
        ttk.Label(specs_box, text="Device details", style="Subhead.TLabel").pack(anchor="w", pady=(0, 8))
        specs_table = ttk.Frame(specs_box, style="Surface.TFrame")
        specs_table.pack(fill="both", expand=True)
        self.spec_tree = ttk.Treeview(specs_table, columns=("property", "value"), show="headings", height=11)
        self.spec_tree.heading("property", text="Property")
        self.spec_tree.heading("value", text="Value")
        self.spec_tree.column("property", width=180, stretch=False)
        self.spec_tree.column("value", width=320)
        spec_scrollbar = ttk.Scrollbar(specs_table, orient="vertical", command=self.spec_tree.yview)
        self.spec_tree.configure(yscrollcommand=spec_scrollbar.set)
        self.spec_tree.pack(side="left", fill="both", expand=True)
        spec_scrollbar.pack(side="right", fill="y")

        benchmark_box = ttk.Frame(content, style="Surface.TFrame", width=300)
        benchmark_box.pack(side="right", fill="both")
        benchmark_box.pack_propagate(False)
        ttk.Label(benchmark_box, text="Benchmark reference", style="Subhead.TLabel").pack(anchor="w", pady=(0, 8))
        self.benchmark_text = tk.Text(benchmark_box, width=34, height=13, bg="#f7f9fa", fg=self.INK, relief="flat", font=("Consolas", 10), padx=12, pady=10, wrap="word")
        self.benchmark_text.pack(fill="both", expand=True)
        self.benchmark_text.configure(state="disabled")

    def _build_sensors(self) -> None:
        toolbar = ttk.Frame(self.sensors_tab, style="Surface.TFrame")
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(toolbar, text="Live telemetry", style="Subhead.TLabel").pack(side="left")
        self.logging_button = ttk.Button(toolbar, text="Start log", command=self.toggle_sensor_log)
        self.logging_button.pack(side="right")
        ttk.Label(toolbar, text="Refreshes every second", style="Muted.TLabel").pack(side="right", padx=12)

        columns = ("sensor", "current", "minimum", "maximum", "average", "unit")
        self.sensor_tree = ttk.Treeview(self.sensors_tab, columns=columns, show="headings")
        widths = {"sensor": 240, "current": 105, "minimum": 105, "maximum": 105, "average": 105, "unit": 70}
        for column in columns:
            self.sensor_tree.heading(column, text=column.title())
            self.sensor_tree.column(column, width=widths[column], anchor="w" if column == "sensor" else "center")
        self.sensor_tree.pack(fill="both", expand=True)
        self.sensor_tree.tag_configure("even", background="#f7f9fa")

    def _build_advanced(self) -> None:
        toolbar = ttk.Frame(self.advanced_tab, style="Surface.TFrame")
        toolbar.pack(fill="x", pady=(0, 10))
        ttk.Label(toolbar, text="Information category", style="Subhead.TLabel").pack(side="left")
        self.advanced_var = tk.StringVar(value="General")
        categories = ["General", "PCIe", "Memory", "Runtime", "Benchmark CSV", "System"]
        combo = ttk.Combobox(toolbar, textvariable=self.advanced_var, values=categories, state="readonly", width=24)
        combo.pack(side="right")
        combo.bind("<<ComboboxSelected>>", lambda _event: self._populate_advanced())
        self.advanced_tree = ttk.Treeview(self.advanced_tab, columns=("property", "value"), show="headings")
        self.advanced_tree.heading("property", text="Property")
        self.advanced_tree.heading("value", text="Value")
        self.advanced_tree.column("property", width=290, stretch=False)
        self.advanced_tree.column("value", width=520)
        self.advanced_tree.pack(fill="both", expand=True)
        self.advanced_tree.tag_configure("section", background="#e9eef2", font=("Segoe UI Semibold", 10))

    def _build_validation(self) -> None:
        top = ttk.Frame(self.validation_tab, style="Surface.TFrame")
        top.pack(fill="x")
        copy = ttk.Frame(top, style="Surface.TFrame")
        copy.pack(side="left", fill="x", expand=True)
        ttk.Label(copy, text="Local validation report", style="Subhead.TLabel").pack(anchor="w")
        ttk.Label(copy, text="Collects five sensor samples and writes a shareable key=value log.", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        self.run_report_button = ttk.Button(top, text="Run 5s measurement", style="Accent.TButton", command=self.run_quick_report)
        self.run_report_button.pack(side="right")

        self.validation_text = tk.Text(self.validation_tab, bg="#101820", fg="#d6e2e9", insertbackground="white", relief="flat", font=("Consolas", 10), padx=14, pady=12, wrap="none")
        self.validation_text.pack(fill="both", expand=True, pady=(14, 10))
        actions = ttk.Frame(self.validation_tab, style="Surface.TFrame")
        actions.pack(fill="x")
        ttk.Button(actions, text="Save copy", command=self.save_validation_copy).pack(side="right")
        self.validation_path_label = ttk.Label(actions, text="No report generated", style="Muted.TLabel")
        self.validation_path_label.pack(side="left")

    def refresh_devices(self) -> None:
        try:
            self.devices = [GpuDevice(**device) for device in self.service.list_devices()]
        except CollectorError as error:
            self.status_label.configure(text=str(error), foreground="#b94343")
            return
        self.device_combo["values"] = [f"GPU {d.index}  |  {d.name}" for d in self.devices]
        if self.devices:
            self.device_combo.current(0)
            self._load_device(self.devices[0])

    def _on_device_selected(self, _event: object = None) -> None:
        selection = self.device_combo.current()
        if 0 <= selection < len(self.devices):
            self._load_device(self.devices[selection])

    def _load_device(self, device: GpuDevice) -> None:
        try:
            details = self.service.inspect_device(device.index)
            self.current_info = details["gpu"]
            self.current_match = self.service.benchmark_match(device.name)
        except CollectorError as error:
            self.status_label.configure(text=str(error), foreground="#b94343")
            return
        self.status_label.configure(text="Hardware detected - live sensors active", foreground=self.GREEN_DARK)
        self.gpu_name_label.configure(text=device.name)
        self.gpu_meta_label.configure(
            text=f"Driver {self.current_info.get('driver_version', 'N/A')}   |   CUDA capability {self.current_info.get('compute_cap', 'N/A')}"
        )
        self._populate_apis()
        self._populate_specs()
        self._populate_benchmark()
        self._populate_advanced()
        self._populate_validation_status()

    def _populate_apis(self) -> None:
        for child in self.api_frame.winfo_children():
            child.destroy()
        statuses = [
            ("CUDA", self.current_info.get("compute_cap") not in {None, "[N/A]", "N/A"}),
            ("OpenCL", bool(self.current_match.compute and self.current_match.compute.get("OpenCL"))),
            ("Vulkan", bool(self.current_match.compute and self.current_match.compute.get("Vulkan"))),
        ]
        for name, supported in statuses:
            bg = "#dcefe5" if supported else "#edf0f2"
            fg = self.GREEN_DARK if supported else self.MUTED
            tk.Label(self.api_frame, text=name, bg=bg, fg=fg, font=("Segoe UI Semibold", 9), padx=9, pady=5).pack(side="left", padx=3)

    def _replace_tree(self, tree: ttk.Treeview, rows: list[tuple[str, str]]) -> None:
        tree.delete(*tree.get_children())
        for index, row in enumerate(rows):
            tree.insert("", "end", values=row, tags=("even",) if index % 2 == 0 else ())

    def _populate_specs(self) -> None:
        rows = [
            ("Name", self.current_info.get("name", "N/A")),
            ("GPU UUID", self.current_info.get("uuid", "N/A")),
            ("VBIOS", self.current_info.get("vbios_version", "N/A")),
            ("PCI Device ID", self.current_info.get("pci.device_id", "N/A")),
            ("Bus ID", self.current_info.get("pci.bus_id", "N/A")),
            ("Memory Size", f"{self.current_info.get('memory.total', 'N/A')} MiB"),
            ("Max GPU Clock", f"{self.current_info.get('clocks.max.graphics', 'N/A')} MHz"),
            ("Max Memory Clock", f"{self.current_info.get('clocks.max.memory', 'N/A')} MHz"),
            ("Display Active", self.current_info.get("display_active", "N/A")),
            ("Compute Mode", self.current_info.get("compute_mode", "N/A")),
        ]
        self._replace_tree(self.spec_tree, rows)

    def _set_benchmark_text(self, text: str) -> None:
        self.benchmark_text.configure(state="normal")
        self.benchmark_text.delete("1.0", "end")
        self.benchmark_text.insert("1.0", text)
        self.benchmark_text.configure(state="disabled")

    def _populate_benchmark(self) -> None:
        lines = []
        if self.current_match.passmark:
            row = self.current_match.passmark
            lines.extend([
                "EXACT PASSMARK ROW",
                f"G3D Mark       {row.get('G3Dmark', 'N/A')}",
                f"G2D Mark       {row.get('G2Dmark', 'N/A')}",
                f"TDP            {row.get('TDP', 'N/A')} W",
                f"Power perf.    {row.get('powerPerformance', 'N/A')}",
            ])
        if self.current_match.compute:
            row = self.current_match.compute
            lines.extend([
                "",
                "COMPUTE API",
                f"CUDA           {row.get('CUDA') or 'N/A'}",
                f"OpenCL         {row.get('OpenCL') or 'N/A'}",
                f"Vulkan         {row.get('Vulkan') or 'N/A'}",
            ])
        if not self.current_match.exact:
            lines.append("NO EXACT CSV ROW")
            lines.append("")
            lines.append("Nearest names (not scores):")
            for name, score in self.current_match.suggestions:
                lines.append(f"{score:>5.1%}  {name}")
            lines.extend(["", "Comparison remains unassigned to avoid mixing different GPU models."])
        self._set_benchmark_text("\n".join(lines))

    def _advanced_rows(self) -> list[tuple[str, str]]:
        category = self.advanced_var.get()
        snapshot = self.latest_snapshot.values if self.latest_snapshot else {}
        if category == "General":
            return [
                ("Driver Version", self.current_info.get("driver_version", "N/A")),
                ("VBIOS Version", self.current_info.get("vbios_version", "N/A")),
                ("Compute Capability", self.current_info.get("compute_cap", "N/A")),
                ("Display Mode", self.current_info.get("display_mode", "N/A")),
                ("Display Active", self.current_info.get("display_active", "N/A")),
                ("Compute Mode", self.current_info.get("compute_mode", "N/A")),
            ]
        if category == "PCIe":
            return [
                ("Bus ID", self.current_info.get("pci.bus_id", "N/A")),
                ("Device ID", self.current_info.get("pci.device_id", "N/A")),
                ("GPU UUID", self.current_info.get("uuid", "N/A")),
            ]
        if category == "Memory":
            return [
                ("Total", f"{self.current_info.get('memory.total', 'N/A')} MiB"),
                ("Used", self._format_value(snapshot.get("memory_used_mib"), "MiB")),
                ("Free", self._format_value(snapshot.get("memory_free_mib"), "MiB")),
                ("Current Clock", self._format_value(snapshot.get("memory_clock_mhz"), "MHz")),
                ("Maximum Clock", f"{self.current_info.get('clocks.max.memory', 'N/A')} MHz"),
            ]
        if category == "Runtime":
            return [(SENSOR_LABELS[key][0], self._format_value(snapshot.get(key), SENSOR_LABELS[key][1])) for key in SENSOR_LABELS]
        if category == "Benchmark CSV":
            rows = [("Exact model match", "Yes" if self.current_match.exact else "No")]
            if self.current_match.passmark:
                rows.extend((f"PassMark {key}", value or "N/A") for key, value in self.current_match.passmark.items())
            if self.current_match.compute:
                rows.extend((f"Compute {key}", value or "N/A") for key, value in self.current_match.compute.items())
            rows.extend((f"Nearest {index}", f"{name} ({score:.1%})") for index, (name, score) in enumerate(self.current_match.suggestions, 1))
            return rows
        environment = self.service.environment()
        return [(key.replace("_", " ").title(), str(value)) for key, value in environment.items()]

    def _populate_advanced(self) -> None:
        if not hasattr(self, "advanced_tree"):
            return
        self._replace_tree(self.advanced_tree, self._advanced_rows())

    def _populate_validation_status(self) -> None:
        if not hasattr(self, "validation_text"):
            return
        lines = [
            "GPU MEASURER / LOCAL VALIDATION",
            "================================",
            f"[OK] NVIDIA device: {self.current_info.get('name', 'N/A')}",
            f"[OK] Driver: {self.current_info.get('driver_version', 'N/A')}",
            f"[OK] Sensor provider: nvidia-smi",
            ("[OK] Exact benchmark row available" if self.current_match.exact else "[INFO] Exact CSV benchmark row is not available"),
            "[READY] Press 'Run 5s measurement' to generate a report.",
        ]
        self.validation_text.delete("1.0", "end")
        self.validation_text.insert("1.0", "\n".join(lines))

    def _selected_device(self) -> GpuDevice | None:
        index = self.device_combo.current()
        return self.devices[index] if 0 <= index < len(self.devices) else None

    def _schedule_sensor_update(self) -> None:
        if not self.collecting and self._selected_device() is not None:
            self.collecting = True
            device = self._selected_device()
            threading.Thread(target=self._collect_sensor_worker, args=(device.index,), daemon=True).start()
        self.root.after(1000, self._schedule_sensor_update)

    def _collect_sensor_worker(self, gpu_index: int) -> None:
        try:
            snapshot, _payload = self.service.current_snapshot(gpu_index)
            self.ui_events.put(("snapshot", snapshot))
        except CollectorError as error:
            self.ui_events.put(("sensor_error", str(error)))
        finally:
            self.collecting = False

    def _drain_ui_events(self) -> None:
        try:
            while True:
                event, payload = self.ui_events.get_nowait()
                if event == "snapshot":
                    self._apply_snapshot(payload)
                elif event == "sensor_error":
                    self.status_label.configure(text=str(payload), foreground="#b94343")
                elif event == "report_complete":
                    output, content = payload
                    self._report_complete(output, content)
                elif event == "report_failed":
                    self._report_failed(str(payload))
        except Empty:
            pass
        if self.root.winfo_exists():
            self.root.after(100, self._drain_ui_events)

    def _apply_snapshot(self, snapshot: SensorSnapshot) -> None:
        self.latest_snapshot = snapshot
        if self.sensor_logging:
            self.sensor_log_rows.append(snapshot)
        for key, value in snapshot.values.items():
            if isinstance(value, (int, float)):
                self.sensor_history[key].append(float(value))
        self._populate_sensor_tree(snapshot)
        self._update_metric_cards(snapshot)
        if self.advanced_var.get() in {"Memory", "Runtime"}:
            self._populate_advanced()

    def _populate_sensor_tree(self, snapshot: SensorSnapshot) -> None:
        self.sensor_tree.delete(*self.sensor_tree.get_children())
        for index, (key, (label, unit)) in enumerate(SENSOR_LABELS.items()):
            current = snapshot.values.get(key)
            history = list(self.sensor_history[key])
            if history:
                minimum = f"{min(history):.1f}"
                maximum = f"{max(history):.1f}"
                average = f"{sum(history) / len(history):.1f}"
            else:
                minimum = maximum = average = "--"
            current_text = f"{current:.1f}" if isinstance(current, (int, float)) else str(current or "N/A")
            self.sensor_tree.insert("", "end", values=(label, current_text, minimum, maximum, average, unit), tags=("even",) if index % 2 == 0 else ())

    def _update_metric_cards(self, snapshot: SensorSnapshot) -> None:
        formats = {
            "temperature_c": ("{:.0f} C",),
            "gpu_utilization_pct": ("{:.0f}%",),
            "memory_used_mib": ("{:.0f} MiB",),
            "power_draw_w": ("{:.1f} W",),
        }
        for key, label in self.metric_labels.items():
            value = snapshot.values.get(key)
            label.configure(text=formats[key][0].format(value) if isinstance(value, (int, float)) else "N/A")

    @staticmethod
    def _format_value(value: object, unit: str = "") -> str:
        if value is None or value == "":
            return "N/A"
        if isinstance(value, (int, float)):
            return f"{value:.1f} {unit}".strip()
        return f"{value} {unit}".strip()

    def toggle_sensor_log(self) -> None:
        if not self.sensor_logging:
            self.sensor_log_rows = []
            self.sensor_logging = True
            self.logging_button.configure(text="Stop & save")
            return
        self.sensor_logging = False
        self.logging_button.configure(text="Start log")
        if not self.sensor_log_rows:
            return
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        output = self.reports_dir / f"sensor-log-{datetime.now():%Y%m%d-%H%M%S}.csv"
        fields = ["timestamp", *SENSOR_LABELS.keys()]
        with output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for snapshot in self.sensor_log_rows:
                writer.writerow({"timestamp": snapshot.timestamp.isoformat(timespec="seconds"), **snapshot.values})
        self.footer_label.configure(text=f"Sensor log saved: {output.name}")

    def run_quick_report(self) -> None:
        device = self._selected_device()
        if device is None:
            return
        self.run_report_button.configure(state="disabled", text="Measuring...")
        self.validation_text.delete("1.0", "end")
        self.validation_text.insert("1.0", "Collecting five samples...\n")
        threading.Thread(target=self._report_worker, args=(device.index,), daemon=True).start()

    def _report_worker(self, gpu_index: int) -> None:
        try:
            result, _payload = self.service.measure(gpu_index, 5.0, 1.0)
            output = self.reports_dir / f"gpu-measurement-{datetime.now():%Y%m%d-%H%M%S}.log"
            write_log(result, output)
            text = output.read_text(encoding="utf-8")
            self.ui_events.put(("report_complete", (output, text)))
        except Exception as error:
            self.ui_events.put(("report_failed", str(error)))

    def _report_complete(self, output: Path, text: str) -> None:
        self.validation_text.delete("1.0", "end")
        self.validation_text.insert("1.0", text)
        self.validation_path_label.configure(text=str(output))
        self.run_report_button.configure(state="normal", text="Run 5s measurement")
        self.footer_label.configure(text=f"Report generated: {output.name}")

    def _report_failed(self, message: str) -> None:
        self.validation_text.delete("1.0", "end")
        self.validation_text.insert("1.0", f"Measurement failed:\n{message}")
        self.run_report_button.configure(state="normal", text="Run 5s measurement")

    def save_validation_copy(self) -> None:
        content = self.validation_text.get("1.0", "end").strip()
        if not content:
            return
        path = filedialog.asksaveasfilename(
            title="Save validation report",
            defaultextension=".log",
            filetypes=[("Log file", "*.log"), ("Text file", "*.txt")],
        )
        if path:
            Path(path).write_text(content + "\n", encoding="utf-8")
            messagebox.showinfo("GPU Measurer", "Report copy saved.")


def launch() -> None:
    root = tk.Tk()
    GpuMeasurerApp(root)
    root.mainloop()
