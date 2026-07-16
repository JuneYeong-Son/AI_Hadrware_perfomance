"""Dialog that offers to download the benchmark engine on demand."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .engine_installer import install_engine
from .theme import APP_STYLESHEET


class _InstallWorker(QThread):
    log = Signal(str)
    done = Signal(bool)

    def run(self) -> None:  # executed on the worker thread
        ok = install_engine(log=lambda message: self.log.emit(message))
        self.done.emit(ok)


class EngineInstallDialog(QDialog):
    """Explains the engine download and runs it off the UI thread.

    After a successful run ``installed`` is True; the caller should rebuild its
    service so the freshly installed torch backend is used.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.installed = False
        self._worker: _InstallWorker | None = None

        self.setWindowTitle("벤치마크 엔진 설치")
        self.setStyleSheet(APP_STYLESHEET)
        self.setMinimumWidth(460)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        title = QLabel("성능 측정 엔진이 필요해요")
        title.setObjectName("H1")
        root.addWidget(title)

        info = QLabel(
            "GPU 성능(TFLOPS) 측정에는 벤치마크 엔진(PyTorch+CUDA)이 필요합니다.\n"
            "앱을 가볍게 유지하려고 기본 설치에는 포함하지 않았어요.\n\n"
            "지금 한 번만 내려받으면(수 GB, 몇 분 소요) 이후로는 바로 측정할 수 있어요.\n"
            "NVIDIA GPU와 최신 드라이버가 필요합니다."
        )
        info.setObjectName("Muted")
        info.setWordWrap(True)
        root.addWidget(info)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setVisible(False)
        self.logbox.setMaximumHeight(120)
        root.addWidget(self.logbox)

        self.install_button = QPushButton("엔진 다운로드·설치")
        self.install_button.clicked.connect(self._start_install)
        root.addWidget(self.install_button)

        self.close_button = QPushButton("나중에")
        self.close_button.setObjectName("Secondary")
        self.close_button.clicked.connect(self.reject)
        root.addWidget(self.close_button)

    def _append(self, message: str) -> None:
        self.logbox.appendPlainText(message)

    def _start_install(self) -> None:
        self.install_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.progress.setVisible(True)
        self.logbox.setVisible(True)
        self._worker = _InstallWorker(self)
        self._worker.log.connect(self._append)
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, ok: bool) -> None:
        self.progress.setVisible(False)
        self.installed = ok
        if ok:
            self._append("이제 벤치마크를 시작할 수 있어요.")
            self.accept()
        else:
            self.install_button.setEnabled(True)
            self.close_button.setEnabled(True)
            self.install_button.setText("다시 시도")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        # Don't leave a background install thread dangling on close.
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(50)
        super().closeEvent(event)
