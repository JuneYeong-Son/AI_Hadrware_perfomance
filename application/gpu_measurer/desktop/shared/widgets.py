"""Small reusable widgets shared by both apps."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QLabel,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from .theme import status_style


class RangeGauge(QWidget):
    """A 0–100% bar with a shaded 'normal range' band and a value marker.

    Makes a factual number like 55% instantly readable as "inside the normal
    range for this test" without needing the user to interpret it.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._value: float | None = None
        self._low = 40.0
        self._high = 70.0
        self.setMinimumHeight(52)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_values(self, value: float | None, low: float, high: float) -> None:
        self._value = value
        self._low = float(low)
        self._high = float(high)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        track_h = 14
        top = 22
        radius = track_h / 2

        def x_at(pct: float) -> float:
            return max(0.0, min(1.0, pct / 100.0)) * w

        # Track (angular 2px corners per NVIDIA design)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f7f7f7"))
        painter.drawRoundedRect(0, top, w, track_h, 2, 2)

        # Normal-range band (pale NVIDIA green)
        band_x = x_at(self._low)
        band_w = x_at(self._high) - band_x
        painter.setBrush(QColor("#e0efc4"))
        painter.drawRoundedRect(int(band_x), top, int(band_w), track_h, 2, 2)

        # Band caption
        painter.setPen(QColor("#757575"))
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(int(band_x), top - 6, f"정상 범위 {int(self._low)}~{int(self._high)}%")

        # Value marker
        if self._value is not None:
            mx = x_at(self._value)
            inside = self._value >= self._low
            color = QColor("#5a8d00") if inside else QColor("#b25200")
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(int(mx) - 7, top - 3, 14, 20)
            painter.setPen(color)
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)
            label = f"{self._value:.0f}%"
            tx = min(max(0, int(mx) - 12), w - 30)
            painter.drawText(tx, top + track_h + 16, label)
        painter.end()


class StatusBadge(QLabel):
    """A pill showing a status with both color and text (never color alone)."""

    def __init__(self, status: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.set_status(status)

    def set_status(self, status: str) -> None:
        label, fg, bg = status_style(status)
        self.setText(f"  {label}  " if label else "")
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:2px;"
            f"padding:3px 10px; font-weight:700;"
        )


class InfoDot(QLabel):
    """A small 'ⓘ' that shows an explanation the instant you hover over it.

    Qt's default tooltip has a ~0.7s wake-up delay and can fail to appear over
    small widgets; we show it immediately on mouse-enter (and on click) instead.
    """

    def __init__(self, tooltip_html: str, parent: QWidget | None = None):
        super().__init__("ⓘ", parent)
        self.setObjectName("InfoDot")
        self._tip = tooltip_html
        self.setToolTip(tooltip_html)
        self.setCursor(Qt.WhatsThisCursor)

    def _show_tip(self) -> None:
        QToolTip.showText(self.mapToGlobal(QPoint(0, self.height())), self._tip, self)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._show_tip()
        super().enterEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._show_tip()
        super().mousePressEvent(event)


class Card(QFrame):
    """A white, hairline-bordered container with a green corner square.

    Per the NVIDIA design system, every reusable card carries a small solid
    green square anchored to its top-left corner — the system's signature
    ornamental "identity tag". The container itself is flat (no shadow) with a
    2px radius and a 1px hairline border (styled via ``QFrame#Card``).
    """

    _CORNER = 12  # px — 12x12 corner square per DESIGN-nvidia.md

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 16, 18, 16)
        self._layout.setSpacing(8)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#76b900"))
        # Inset by the 1px border so the square sits cleanly inside the corner.
        painter.drawRect(1, 1, self._CORNER, self._CORNER)
        painter.end()

    def layout(self) -> QVBoxLayout:  # type: ignore[override]
        return self._layout

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)


class BigStat(QWidget):
    """A large headline number with a caption, for the one key result."""

    def __init__(self, caption: str, value: str = "—", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._value = QLabel(value)
        self._value.setObjectName("BigStat")
        self._caption = QLabel(caption)
        self._caption.setObjectName("StatCaption")
        layout.addWidget(self._value)
        layout.addWidget(self._caption)

    def set_value(self, value: str) -> None:
        self._value.setText(value)


def collapsible(title: str, checked: bool = False) -> tuple[QGroupBox, QVBoxLayout]:
    """A checkable section whose contents are truly hidden when unchecked.

    A plain checkable QGroupBox only *disables* its children when unchecked (they
    stay visible); this wraps the content so it is shown/hidden with the toggle.
    Returns the box (add to a layout) and the inner layout (add content to).
    """
    box = QGroupBox(title)
    box.setCheckable(True)
    box.setChecked(checked)
    inner = QWidget()
    inner_layout = QVBoxLayout(inner)
    inner_layout.setContentsMargins(0, 6, 0, 0)
    outer = QVBoxLayout(box)
    outer.setContentsMargins(10, 6, 10, 6)
    outer.addWidget(inner)
    inner.setVisible(checked)
    box.toggled.connect(inner.setVisible)
    return box, inner_layout


def h1(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("H1")
    return label


def h2(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("H2")
    return label


def muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label
