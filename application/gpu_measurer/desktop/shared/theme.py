"""NVIDIA-design-analysis theme and status vocabulary.

Applies the DESIGN-nvidia.md system to the desktop apps: a single, saturated
NVIDIA Green (#76b900) carrying every primary CTA and active state, an
aggressively angular 2px radius on every surface, hairline (#cccccc) borders
instead of shadows, and a black / white / gray monochrome base. Status is still
conveyed by more than one color plus text (never color alone) — 통과 / 주의 /
판정 불가 / 실패 / 측정 불가 each get a distinct, NVIDIA-semantic color.
"""

from __future__ import annotations

# --- NVIDIA-design-analysis tokens (see docs/DESIGN-nvidia.md) --------------
PRIMARY = "#76b900"          # NVIDIA Green — the single accent
PRIMARY_HOVER = "#6fac00"
PRIMARY_DARK = "#5a8d00"     # pressed state
ON_PRIMARY = "#000000"       # text on the green fill
INK = "#000000"              # headlines on canvas
BODY = "#1a1a1a"             # long-form body text
CANVAS = "#ffffff"           # card surface
SURFACE_SOFT = "#f7f7f7"     # page background, strips, disabled fill
SURFACE_DARK = "#000000"     # dark chapters, tooltip
HAIRLINE = "#cccccc"         # 1px card / table border
HAIRLINE_STRONG = "#5e5e5e"
MUTE = "#757575"             # metadata, captions
ASH = "#a7a7a7"              # disabled text
LINK_BLUE = "#0046a4"        # info / inline links only
ERROR = "#e52020"
ERROR_DEEP = "#650b0b"
WARNING = "#df6500"
WARNING_TEXT = "#b25200"     # darker warning for readable text on white
SUCCESS_DEEP = "#3f8500"

# Verdict / status -> (label, foreground, background) for badges.
# Aligned to NVIDIA semantic colors; each status stays visually distinct.
STATUS_STYLES = {
    "통과": ("통과", "#356d00", "#e4f0cc"),
    "주의": ("주의", "#8a3f00", "#feeeb2"),
    "판정 불가": ("판정 불가", "#41464b", "#ececec"),
    "실패": ("실패", "#650b0b", "#fadcdc"),
    "측정 불가": ("측정 불가", "#5e5e5e", "#efefef"),
    "검사 필요": ("검사 필요", "#0046a4", "#d9e5f6"),
    "검사 중": ("검사 중", "#055160", "#cff4fc"),
    "기준선 없음": ("기준선 없음", "#5e5e5e", "#efefef"),
}


def status_style(status: str) -> tuple[str, str, str]:
    return STATUS_STYLES.get(status, (status, "#41464b", "#ececec"))


APP_STYLESHEET = """
* { font-family: 'Segoe UI', 'Malgun Gothic', Arial, sans-serif; }
QMainWindow, QWidget#Page { background: #f7f7f7; }
QLabel { color: #1a1a1a; }
QLabel#H1 { font-size: 24px; font-weight: 700; color: #000000; }
QLabel#H2 { font-size: 16px; font-weight: 700; color: #000000; }
QLabel#Muted { color: #757575; }
QLabel#InfoDot { color: #5a8d00; font-size: 15px; font-weight: 800; }
QToolTip {
    background: #000000; color: #ffffff; border: none; border-radius: 2px;
    padding: 8px 10px; font-size: 12px;
}
QLabel#BigStat { font-size: 40px; font-weight: 800; color: #000000; }
QLabel#StatCaption { color: #757575; font-size: 12px; }
QFrame#Card {
    background: #ffffff; border: 1px solid #cccccc; border-radius: 2px;
}
QPushButton {
    background: #76b900; color: #000000; border: none; border-radius: 2px;
    padding: 11px 24px; font-size: 16px; font-weight: 700;
}
QPushButton:hover { background: #6fac00; }
QPushButton:pressed { background: #5a8d00; }
QPushButton:disabled { background: #f7f7f7; color: #a7a7a7; }
QPushButton#Secondary {
    background: transparent; color: #000000; border: 2px solid #76b900;
    padding: 9px 22px;
}
QPushButton#Secondary:hover { background: #f2f8e6; }
QPushButton#Secondary:disabled { border-color: #cccccc; color: #a7a7a7; }
QPushButton#Danger { background: #e52020; color: #ffffff; }
QPushButton#Danger:hover { background: #c91b1b; }
QPushButton#Danger:pressed { background: #650b0b; }
QPushButton#ModeButton {
    background: #ffffff; color: #000000; text-align: left;
    border: 1px solid #cccccc; border-radius: 2px; padding: 12px 16px;
    font-weight: 700;
}
QPushButton#ModeButton:hover { background: #f7f7f7; }
QPushButton#ModeButton:checked {
    background: #ffffff; color: #000000; border: 2px solid #76b900;
}
QTableWidget {
    background: #ffffff; border: 1px solid #cccccc; border-radius: 2px;
    gridline-color: #e6e6e6;
}
QHeaderView::section {
    background: #f7f7f7; color: #1a1a1a; padding: 8px; border: none;
    border-bottom: 1px solid #cccccc; font-weight: 700;
}
QGroupBox {
    border: 1px solid #cccccc; border-radius: 2px; margin-top: 10px;
    font-weight: 700; color: #000000;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 10px; padding: 0 4px;
}
QProgressBar {
    border: 1px solid #cccccc; border-radius: 2px; background: #f7f7f7;
    text-align: center; height: 18px; color: #000000;
}
QProgressBar::chunk { background: #76b900; border-radius: 0px; }
"""
