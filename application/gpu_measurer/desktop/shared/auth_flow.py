"""Authentication flow glue: auto-login, the login gate, and the account bar.

Kept separate from the app windows so the buyer/operator windows need no
changes — the login gate runs in ``app._run`` and the account bar (name +
logout) is injected into the window's status bar here.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QWidget,
)

from .api_client import ApiClient, ApiError
from .auth_dialog import LoginDialog
from .auth_store import clear_session, load_session, save_session


@dataclass
class AuthSession:
    client: ApiClient
    token: str | None = None
    user: dict | None = None
    offline: bool = False
    # Set when the user logs out (or asks to log in from offline mode) so the
    # launcher loop knows to return to the login screen instead of exiting.
    wants_relogin: bool = False

    @property
    def display_name(self) -> str:
        return (self.user or {}).get("display_name", "")

    @property
    def authenticated(self) -> bool:
        return bool(self.token and self.user)


def authenticate() -> AuthSession | None:
    """Return a session, or ``None`` if the user closed the login screen.

    Tries a stored token first (silent auto-login); falls back to the dialog.
    """
    client = ApiClient()

    stored = load_session()
    if stored and stored.get("token"):
        try:
            user = client.me(stored["token"])
            return AuthSession(client, token=stored["token"], user=user)
        except ApiError:
            clear_session()  # expired, invalidated by logout, or server rejected it

    dialog = LoginDialog(client)
    if dialog.exec() != QDialog.DialogCode.Accepted or dialog.outcome is None:
        return None
    kind, token, user = dialog.outcome
    if kind == "offline":
        return AuthSession(client, offline=True)
    save_session(token, user)
    return AuthSession(client, token=token, user=user)


def install_account_bar(window: QMainWindow, session: AuthSession) -> None:
    """Add a name label + logout/login button to the window's status bar.

    Also stores the session on the window as ``auth_session`` so features like
    result upload can reach the token and API client at click time.
    """
    window.auth_session = session
    bar = window.statusBar()
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 8, 0)
    layout.setSpacing(10)

    if session.authenticated:
        label = QLabel(f"{session.display_name} 님")
        label.setObjectName("Muted")
        action = QPushButton("로그아웃")

        def on_logout() -> None:
            if session.token:
                try:
                    session.client.logout(session.token)
                except ApiError:
                    pass  # best-effort; we log out locally regardless
            clear_session()
            session.wants_relogin = True
            window.close()

        action.clicked.connect(on_logout)
    else:
        label = QLabel("오프라인 모드")
        label.setObjectName("Muted")
        action = QPushButton("로그인")

        def on_login() -> None:
            session.wants_relogin = True
            window.close()

        action.clicked.connect(on_login)

    action.setObjectName("Secondary")
    layout.addWidget(label)
    layout.addWidget(action)
    bar.addPermanentWidget(container)
