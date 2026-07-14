"""Light, calm operational theme and status vocabulary.

Per the brief's visual direction: a bright operational surface (not a dark
enthusiast console), and status conveyed by more than one green — 통과 / 주의 /
판정 불가 / 실패 / 측정 불가 each get a distinct color, plus text (never color
alone).
"""

from __future__ import annotations

# Verdict / status -> (label, foreground, background) for badges.
STATUS_STYLES = {
    "통과": ("통과", "#0f5132", "#d1e7dd"),
    "주의": ("주의", "#664d03", "#fff3cd"),
    "판정 불가": ("판정 불가", "#41464b", "#e2e3e5"),
    "실패": ("실패", "#842029", "#f8d7da"),
    "측정 불가": ("측정 불가", "#495057", "#e9ecef"),
    "검사 필요": ("검사 필요", "#084298", "#cfe2ff"),
    "검사 중": ("검사 중", "#055160", "#cff4fc"),
    "기준선 없음": ("기준선 없음", "#495057", "#e9ecef"),
}


def status_style(status: str) -> tuple[str, str, str]:
    return STATUS_STYLES.get(status, (status, "#41464b", "#e2e3e5"))


APP_STYLESHEET = """
* { font-family: 'Segoe UI', 'Malgun Gothic', sans-serif; }
QMainWindow, QWidget#Page { background: #f5f7fa; }
QLabel { color: #212529; }
QLabel#H1 { font-size: 22px; font-weight: 700; color: #16202c; }
QLabel#H2 { font-size: 15px; font-weight: 600; color: #16202c; }
QLabel#Muted { color: #6c757d; }
QLabel#InfoDot { color: #2f6fed; font-size: 15px; font-weight: 800; }
QToolTip {
    background: #16202c; color: #ffffff; border: none; border-radius: 6px;
    padding: 8px 10px; font-size: 12px;
}
QLabel#BigStat { font-size: 40px; font-weight: 800; color: #16202c; }
QLabel#StatCaption { color: #6c757d; font-size: 12px; }
QFrame#Card {
    background: #ffffff; border: 1px solid #e3e8ef; border-radius: 12px;
}
QPushButton {
    background: #2f6fed; color: white; border: none; border-radius: 8px;
    padding: 10px 18px; font-size: 14px; font-weight: 600;
}
QPushButton:hover { background: #2760d4; }
QPushButton:disabled { background: #b9c6e3; }
QPushButton#Secondary { background: #eef1f6; color: #2f3a4a; }
QPushButton#Secondary:hover { background: #e2e7f0; }
QPushButton#Danger { background: #e5533c; }
QPushButton#ModeButton {
    background: #eef1f6; color: #2f3a4a; text-align: left;
    border: 2px solid #e3e8ef; padding: 12px 16px;
}
QPushButton#ModeButton:hover { background: #e6ebf3; }
QPushButton#ModeButton:checked {
    background: #e7f0ff; color: #16408f; border: 2px solid #2f6fed;
}
QTableWidget {
    background: #ffffff; border: 1px solid #e3e8ef; border-radius: 8px;
    gridline-color: #eef1f6;
}
QHeaderView::section {
    background: #f0f3f8; color: #41505f; padding: 8px; border: none;
    font-weight: 600;
}
QProgressBar {
    border: 1px solid #e3e8ef; border-radius: 6px; background: #eef1f6;
    text-align: center; height: 18px;
}
QProgressBar::chunk { background: #2f6fed; border-radius: 6px; }
"""
