"""Login / signup dialog shown before a desktop app window opens."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .api_client import ApiClient, ApiError
from .theme import APP_STYLESHEET


class LoginDialog(QDialog):
    """Collects credentials and authenticates against the backend.

    On success ``outcome`` is ``("auth", token, user)``. The user may instead
    choose to continue offline (``("offline", None, None)``); closing the dialog
    leaves ``outcome`` as ``None``.
    """

    def __init__(self, client: ApiClient, parent: QWidget | None = None):
        super().__init__(parent)
        self._client = client
        self.outcome: tuple[str, str | None, dict | None] | None = None

        self.setWindowTitle("GPU-Perf 로그인")
        self.setStyleSheet(APP_STYLESHEET)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        title = QLabel("GPU-Perf")
        title.setObjectName("H1")
        subtitle = QLabel("측정 결과를 안전하게 기록하고 공유하려면 로그인하세요.")
        subtitle.setObjectName("Muted")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_login_tab(), "로그인")
        self.tabs.addTab(self._build_signup_tab(), "회원가입")
        self.tabs.currentChanged.connect(lambda _i: self._set_error(""))
        root.addWidget(self.tabs)

        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet("color:#e52020; font-weight:600;")
        self.error.setVisible(False)
        root.addWidget(self.error)

        offline = QPushButton("오프라인으로 계속 (기록·공유 없이 사용)")
        offline.setObjectName("Secondary")
        offline.clicked.connect(self._continue_offline)
        root.addWidget(offline)

    # --- tabs ---------------------------------------------------------------
    def _build_login_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.login_email = QLineEdit()
        self.login_email.setPlaceholderText("you@example.com")
        self.login_password = QLineEdit()
        self.login_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_password.returnPressed.connect(self._do_login)
        form.addRow("이메일", self.login_email)
        form.addRow("비밀번호", self.login_password)
        layout.addLayout(form)
        btn = QPushButton("로그인")
        btn.clicked.connect(self._do_login)
        layout.addWidget(btn)
        return page

    def _build_signup_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.signup_name = QLineEdit()
        self.signup_name.setPlaceholderText("표시 이름")
        self.signup_email = QLineEdit()
        self.signup_email.setPlaceholderText("you@example.com")
        self.signup_password = QLineEdit()
        self.signup_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.signup_password.setPlaceholderText("8자 이상")
        self.signup_password.returnPressed.connect(self._do_signup)
        form.addRow("이름", self.signup_name)
        form.addRow("이메일", self.signup_email)
        form.addRow("비밀번호", self.signup_password)
        layout.addLayout(form)
        btn = QPushButton("회원가입")
        btn.clicked.connect(self._do_signup)
        layout.addWidget(btn)
        return page

    # --- actions ------------------------------------------------------------
    def _set_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.setVisible(bool(message))

    def _finish_auth(self, token: str) -> None:
        # Fetch the profile so the window can greet the user by name.
        try:
            user = self._client.me(token)
        except ApiError as error:
            self._set_error(str(error))
            return
        self.outcome = ("auth", token, user)
        self.accept()

    def _do_login(self) -> None:
        email = self.login_email.text().strip()
        password = self.login_password.text()
        if not email or not password:
            self._set_error("이메일과 비밀번호를 입력하세요.")
            return
        self._set_error("")
        self.setEnabled(False)
        try:
            result = self._client.login(email, password)
        except ApiError as error:
            self._set_error(str(error))
            return
        finally:
            self.setEnabled(True)
        self._finish_auth(result["access_token"])

    def _do_signup(self) -> None:
        name = self.signup_name.text().strip()
        email = self.signup_email.text().strip()
        password = self.signup_password.text()
        if not name or not email or not password:
            self._set_error("모든 항목을 입력하세요.")
            return
        if len(password) < 8:
            self._set_error("비밀번호는 8자 이상이어야 해요.")
            return
        self._set_error("")
        self.setEnabled(False)
        try:
            result = self._client.signup(email, password, name)
        except ApiError as error:
            self._set_error(str(error))
            return
        finally:
            self.setEnabled(True)
        self._finish_auth(result["access_token"])

    def _continue_offline(self) -> None:
        self.outcome = ("offline", None, None)
        self.accept()
