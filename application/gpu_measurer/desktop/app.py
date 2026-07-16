"""Entry helpers that launch each desktop app."""

from __future__ import annotations

import sys


def _run(window_factory) -> int:
    from PySide6.QtWidgets import QApplication

    from .shared.auth_flow import authenticate, install_account_bar

    app = QApplication.instance() or QApplication(sys.argv)
    # Set an app identity so QStandardPaths resolves a stable config directory
    # for the saved session (used by auth_store).
    app.setOrganizationName("GpuPerf")
    app.setApplicationName("GpuPerf")

    # Login gate. Looping lets "logout" (or "log in" from offline mode) return
    # to the login screen instead of quitting the app.
    while True:
        session = authenticate()
        if session is None:
            return 0  # user closed the login screen
        window = window_factory()
        install_account_bar(window, session)
        window.show()
        app.exec()
        if not session.wants_relogin:
            return 0



def run_buyer() -> int:
    from .buyer.main_window import GpuCheckWindow

    return _run(GpuCheckWindow)


def run_operator() -> int:
    from .operator.main_window import GpuOpsWindow

    return _run(GpuOpsWindow)
