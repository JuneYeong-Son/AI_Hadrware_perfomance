"""Entry helpers that launch each desktop app."""

from __future__ import annotations

import sys


def _run(window_factory) -> int:
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    window = window_factory()
    window.show()
    return app.exec()


def run_buyer() -> int:
    from .buyer.main_window import GpuCheckWindow

    return _run(GpuCheckWindow)


def run_operator() -> int:
    from .operator.main_window import GpuOpsWindow

    return _run(GpuOpsWindow)
