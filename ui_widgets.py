"""Custom-painted neumorphic widgets for the remote control UI.

Everything is drawn with QPainter instead of QSS, so the appearance is
identical on Windows, Linux and macOS and does not depend on system
themes, fonts or emoji glyphs.
"""

import math

from PyQt5.QtCore import QEvent, QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPolygonF,
    QRadialGradient,
)
from PyQt5.QtWidgets import (
    QAbstractButton,
    QGridLayout,
    QLabel,
    QWidget,
)

CARD_COLOR = '#24252A'  # single source of truth for the card fill (used by MainWindow)
BUTTON_TOP = '#2D2E35'
BUTTON_BOTTOM = '#27282E'
BUTTON_PRESSED_TOP = '#1F2025'
BUTTON_PRESSED_BOTTOM = '#191A20'
HOVER_COLOR = '#2B2C33'
TEXT_COLOR = '#CACAD0'
TEXT_BRIGHT_COLOR = '#E6E6EB'
TEXT_DIM_COLOR = '#84848D'
ACCENT_COLOR = '#FF6B3B'
PANEL_COLOR = '#2A2B31'
# D-pad look (matched to the mockup): the disk fades into the card towards the
# bottom-right, and the OK centre is a recessed well outlined by a light ring.
DPAD_DISK_BOTTOM = '#222329'
DPAD_WELL_TOP = '#292A2F'
DPAD_WELL_BOTTOM = '#202126'
DPAD_RING_COLOR = '#383A41'
DPAD_ARROW_COLOR = '#A8A9B0'
DPAD_OK_COLOR = '#BCBDC4'
# Arrow and its hover/press circle are laid out symmetrically inside the ring
# between the OK well (radius 0.23 of the diameter) and the disk edge (0.50):
# the circle sits at the mid-radius with equal gaps both ways, and the arrow
# sits inside the circle with equal margins on all sides.
_ARROW_TIP_RADIUS = 0.4105  # painted arrow-tip distance from the centre / disk diameter
_ARROW_BASE_RADIUS = 0.3195
_ARROW_HALF_WIDTH = 0.050
_ARROW_ROUNDING = 2.2  # arrow corner radius in px
_ZONE_CENTER_RADIUS = 0.365
_ZONE_DIAMETER = 0.23

SHADOW_PAD = 24  # transparent margin around each control, room for the painted halo
GHOST_PAD = 8
FONT_FAMILIES = ['Segoe UI', 'SF Pro Text', 'Ubuntu', 'Roboto', 'Noto Sans', 'DejaVu Sans']

_SECTOR_DEGREES = 45.0  # d-pad direction zones are 90-degree sectors around the center


def _ui_font(pixel_size: int, weight: QFont.Weight = QFont.Normal) -> QFont:
    font = QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


def _pt(rect: QRectF, fx: float, fy: float) -> QPointF:
    return QPointF(rect.left() + rect.width() * fx, rect.top() + rect.height() * fy)


def _paint_circle_halo(  # noqa: PLR0913
    painter: QPainter,
    rect: QRectF,
    inflate: int = 15,
    dy: int = 4,
    alpha: int = 55,
    pressed: bool = False,
    enabled: bool = True,
) -> None:
    """Soft drop shadow for a circular body, painted as a radial gradient."""
    if pressed:
        inflate, dy, alpha = 6, 2, 40
    if not enabled:
        alpha = int(alpha * 0.45)
    center = rect.center() + QPointF(0, dy)
    radius = rect.width() / 2 + inflate
    gradient = QRadialGradient(center, radius)
    gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
    gradient.setColorAt(max(0.0, rect.width() / 2 / radius - 0.15), QColor(0, 0, 0, alpha))
    gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setBrush(gradient)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(center, radius, radius)


def _paint_rounded_halo(painter: QPainter, rect: QRectF, radius: float) -> None:
    """Soft drop shadow for a rounded-rect body, as stacked translucent layers."""
    for inflate, alpha in ((16, 8), (11, 9), (6, 11), (2, 14)):
        shadow = rect.adjusted(-inflate, -inflate + 8, inflate, inflate + 8)
        painter.setBrush(QColor(0, 0, 0, alpha))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(shadow, radius + inflate, radius + inflate)


def _paint_body(painter: QPainter, rect: QRectF, pressed: bool) -> None:
    gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
    if pressed:
        gradient.setColorAt(0.0, QColor(BUTTON_PRESSED_TOP))
        gradient.setColorAt(1.0, QColor(BUTTON_PRESSED_BOTTOM))
    else:
        gradient.setColorAt(0.0, QColor(BUTTON_TOP))
        gradient.setColorAt(1.0, QColor(BUTTON_BOTTOM))
    painter.setBrush(gradient)
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(rect)


def _paint_rim(painter: QPainter, rect: QRectF, pressed: bool) -> None:
    """Uniform hairline rim around the whole circle, matching the pill style."""
    rim_rect = rect.adjusted(0.7, 0.7, -0.7, -0.7)
    light = QColor(255, 255, 255, 5 if pressed else 14)
    dark = QColor(0, 0, 0, 40 if pressed else 28)
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(light, 1.4))
    painter.drawEllipse(rim_rect)
    painter.setPen(QPen(dark, 1.4))
    painter.drawEllipse(rim_rect)
    painter.setPen(Qt.NoPen)


def _draw_power(painter: QPainter, rect: QRectF, color: QColor) -> None:
    center = rect.center()
    radius = rect.width() * 0.34
    arc_rect = QRectF(
        center.x() - radius,
        center.y() - radius + rect.height() * 0.03,
        2 * radius,
        2 * radius,
    )
    painter.drawArc(arc_rect, 125 * 16, 290 * 16)
    painter.drawLine(_pt(rect, 0.5, -0.12), QPointF(center.x(), center.y() - radius * 0.15))


def _draw_back(painter: QPainter, rect: QRectF, color: QColor) -> None:
    painter.drawLine(_pt(rect, 0.72, 0.5), _pt(rect, 0.30, 0.5))
    painter.drawPolyline(QPolygonF([_pt(rect, 0.52, 0.27), _pt(rect, 0.28, 0.5), _pt(rect, 0.52, 0.73)]))


def _draw_menu(painter: QPainter, rect: QRectF, color: QColor) -> None:
    pen = painter.pen()
    for fy in (0.28, 0.5, 0.72):
        painter.setBrush(color)
        dot_center = _pt(rect, 0.26, fy)
        painter.drawEllipse(dot_center, pen.widthF() * 0.42, pen.widthF() * 0.42)
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(_pt(rect, 0.44, fy), _pt(rect, 0.76, fy))


def _draw_mute(painter: QPainter, rect: QRectF, color: QColor) -> None:
    painter.setBrush(color)
    painter.drawPolygon(
        QPolygonF(
            [
                _pt(rect, 0.20, 0.38),
                _pt(rect, 0.36, 0.38),
                _pt(rect, 0.54, 0.22),
                _pt(rect, 0.54, 0.78),
                _pt(rect, 0.36, 0.62),
                _pt(rect, 0.20, 0.62),
            ]
        )
    )
    painter.setBrush(Qt.NoBrush)
    painter.drawLine(_pt(rect, 0.64, 0.26), _pt(rect, 0.86, 0.74))


def _draw_home(painter: QPainter, rect: QRectF, color: QColor) -> None:
    painter.setBrush(color)
    painter.drawPolygon(
        QPolygonF(
            [
                _pt(rect, 0.50, 0.16),
                _pt(rect, 0.80, 0.42),
                _pt(rect, 0.72, 0.42),
                _pt(rect, 0.72, 0.80),
                _pt(rect, 0.58, 0.80),
                _pt(rect, 0.58, 0.58),
                _pt(rect, 0.42, 0.58),
                _pt(rect, 0.42, 0.80),
                _pt(rect, 0.28, 0.80),
                _pt(rect, 0.28, 0.42),
                _pt(rect, 0.20, 0.42),
            ]
        )
    )
    painter.setBrush(Qt.NoBrush)


def _draw_refresh(painter: QPainter, rect: QRectF, color: QColor) -> None:
    arc_rect = QRectF(_pt(rect, 0.14, 0.14), _pt(rect, 0.86, 0.86))
    painter.drawArc(arc_rect, -30 * 16, 280 * 16)
    painter.setBrush(color)
    painter.drawPolygon(
        QPolygonF(
            [
                _pt(rect, 0.82, 0.10),
                _pt(rect, 0.94, 0.38),
                _pt(rect, 0.62, 0.36),
            ]
        )
    )
    painter.setBrush(Qt.NoBrush)


def _draw_chevron_up(painter: QPainter, rect: QRectF, color: QColor) -> None:
    painter.drawPolyline(QPolygonF([_pt(rect, 0.28, 0.60), _pt(rect, 0.50, 0.38), _pt(rect, 0.72, 0.60)]))


def _draw_chevron_down(painter: QPainter, rect: QRectF, color: QColor) -> None:
    painter.drawPolyline(QPolygonF([_pt(rect, 0.28, 0.40), _pt(rect, 0.50, 0.62), _pt(rect, 0.72, 0.40)]))


def _draw_plus(painter: QPainter, rect: QRectF, color: QColor) -> None:
    painter.drawLine(_pt(rect, 0.5, 0.20), _pt(rect, 0.5, 0.80))
    painter.drawLine(_pt(rect, 0.20, 0.5), _pt(rect, 0.80, 0.5))


def _draw_minus(painter: QPainter, rect: QRectF, color: QColor) -> None:
    painter.drawLine(_pt(rect, 0.20, 0.5), _pt(rect, 0.80, 0.5))


def _draw_close(painter: QPainter, rect: QRectF, color: QColor) -> None:
    painter.drawLine(_pt(rect, 0.24, 0.24), _pt(rect, 0.76, 0.76))
    painter.drawLine(_pt(rect, 0.76, 0.24), _pt(rect, 0.24, 0.76))


def _draw_check(painter: QPainter, rect: QRectF, color: QColor) -> None:
    painter.drawPolyline(QPolygonF([_pt(rect, 0.20, 0.52), _pt(rect, 0.42, 0.74), _pt(rect, 0.82, 0.28)]))


_ICON_PAINTERS = {
    'power': _draw_power,
    'back': _draw_back,
    'menu': _draw_menu,
    'mute': _draw_mute,
    'home': _draw_home,
    'refresh': _draw_refresh,
    'chevron-up': _draw_chevron_up,
    'chevron-down': _draw_chevron_down,
    'plus': _draw_plus,
    'minus': _draw_minus,
    'close': _draw_close,
    'check': _draw_check,
}


def _draw_icon(painter: QPainter, name: str, rect: QRectF, color: QColor) -> None:
    pen = QPen(color, max(2.0, rect.width() * 0.105))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter_fn = _ICON_PAINTERS.get(name)
    if painter_fn:
        painter_fn(painter, rect, color)


class NeuCircleButton(QAbstractButton):
    """Round neumorphic button with a painter-drawn icon or text label.

    kind='normal' renders the raised body, 'accent' is the same body with a
    colored icon, 'ghost' is a transparent button that only shows a body on
    hover, 'flat' has no body of its own (for embedding in NeuPill).
    """

    def __init__(  # noqa: PLR0913
        self,
        diameter: int = 47,
        icon: str | None = None,
        text: str | None = None,
        kind: str = 'normal',
        parent: QWidget | None = None,
        pad: int | None = None,
    ) -> None:
        super().__init__(parent)
        self._diameter = diameter
        self._icon_name = icon
        self._text = text
        self._kind = kind
        if pad is None:
            pad = 0 if kind == 'flat' else (GHOST_PAD if kind == 'ghost' else SHADOW_PAD)
        if text:
            self.setText(text)
        self.setFixedSize(diameter + 2 * pad, diameter + 2 * pad)
        self.setCursor(Qt.PointingHandCursor)
        self.setFont(_ui_font(max(11, int(diameter * 0.30))))

    def _content_color(self, pressed: bool) -> QColor:
        if not self.isEnabled():
            color = QColor(TEXT_COLOR)
            color.setAlpha(80)
            return color
        if self._kind == 'accent':
            return QColor(ACCENT_COLOR)
        if pressed:
            return QColor(TEXT_BRIGHT_COLOR)
        return QColor(TEXT_COLOR)

    def _paint_content(self, painter: QPainter) -> None:
        d = float(self._diameter)
        pad = (self.width() - d) / 2
        rect = QRectF(pad, pad, d, d)
        pressed = self.isDown()
        shift = 1.0 if pressed else 0.0
        color = self._content_color(pressed)
        if self._text:
            painter.setPen(QPen(color, 1))
            painter.setFont(self.font())
            painter.drawText(rect.adjusted(0, shift, 0, shift), Qt.AlignCenter, self._text)
        if self._icon_name:
            icon_rect = QRectF(
                rect.left() + d * 0.24,
                rect.top() + d * 0.24 + shift,
                d * 0.52,
                d * 0.52,
            )
            _draw_icon(painter, self._icon_name, icon_rect, color)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        d = float(self._diameter)
        pad = (self.width() - d) / 2
        rect = QRectF(pad, pad, d, d)
        pressed = self.isDown()
        hovered = self.underMouse()

        if self._kind == 'flat':
            if pressed:
                _paint_body(painter, rect, pressed=True)
                _paint_rim(painter, rect, pressed=True)
            elif hovered and self.isEnabled():
                painter.setBrush(QColor(HOVER_COLOR))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(rect)
        elif self._kind == 'ghost':
            if pressed or (hovered and self.isEnabled()):
                _paint_body(painter, rect, pressed)
                _paint_rim(painter, rect, pressed)
        else:
            _paint_circle_halo(painter, rect, pressed=pressed, enabled=self.isEnabled())
            _paint_body(painter, rect, pressed)
            _paint_rim(painter, rect, pressed)
        self._paint_content(painter)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.EnabledChange:
            self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)


class NeuPill(QWidget):
    """Vertical pill with two flat buttons and a centered caption (CH/VOL)."""

    def __init__(
        self,
        label: str,
        top_icon: str,
        bottom_icon: str,
        width: int = 60,
        height: int = 150,
    ) -> None:
        super().__init__()
        self._width = width
        self._height = height
        self.setFixedSize(width + 2 * SHADOW_PAD, height + 2 * SHADOW_PAD)

        self.top_button = NeuCircleButton(38, icon=top_icon, kind='flat', parent=self)
        self.bottom_button = NeuCircleButton(38, icon=bottom_icon, kind='flat', parent=self)
        center_x = self.width() // 2
        self.top_button.move(center_x - self.top_button.width() // 2, SHADOW_PAD + 8)
        self.bottom_button.move(
            center_x - self.bottom_button.width() // 2,
            SHADOW_PAD + height - 8 - self.bottom_button.height(),
        )

        self.caption = QLabel(label, self)
        self.caption.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.caption.setAlignment(Qt.AlignCenter)
        caption_font = _ui_font(12)
        caption_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        self.caption.setFont(caption_font)
        self.caption.setStyleSheet(f'color: {TEXT_DIM_COLOR}; background: transparent;')
        self.caption.setGeometry(0, 0, self.width(), self.height())

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(SHADOW_PAD, SHADOW_PAD, self._width, self._height)
        _paint_rounded_halo(painter, rect, rect.width() / 2)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor(BUTTON_TOP))
        gradient.setColorAt(1.0, QColor(BUTTON_BOTTOM))
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, rect.width() / 2, rect.width() / 2)
        _paint_rim_rounded(painter, rect, rect.width() / 2, pressed=False)


def _paint_rim_rounded(painter: QPainter, rect: QRectF, radius: float, pressed: bool) -> None:
    light = QColor(255, 255, 255, 5 if pressed else 14)
    dark = QColor(0, 0, 0, 40 if pressed else 28)
    painter.setBrush(Qt.NoBrush)
    pen = QPen(light, 1.4)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawRoundedRect(rect.adjusted(0.7, 0.7, -0.7, -0.7), radius, radius)
    painter.setPen(QPen(dark, 1.4))
    painter.drawRoundedRect(rect.adjusted(0.7, 0.7, -0.7, -0.7), radius, radius)
    painter.setPen(Qt.NoPen)


class DPadWidget(QWidget):
    """Large circular d-pad: four arrow zones around a raised OK center."""

    activated = pyqtSignal(str)

    KEY_BY_ZONE = {
        'up': 'DPAD_UP',
        'down': 'DPAD_DOWN',
        'left': 'DPAD_LEFT',
        'right': 'DPAD_RIGHT',
        'ok': 'DPAD_CENTER',
    }

    def __init__(self, diameter: int = 164, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._diameter = diameter
        self._inner_diameter = diameter * 0.46
        self._zone: str | None = None
        self._hover_zone: str | None = None
        self.setFixedSize(diameter + 2 * SHADOW_PAD, diameter + 2 * SHADOW_PAD)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def _arrow_polygon(self, zone: str) -> QPolygonF:
        # The polygon is drawn with a round-join pen _ARROW_ROUNDING wide, which
        # dilates it back to the painted size and rounds its corners, so the raw
        # geometry is shrunk by that amount on every side.
        d = float(self._diameter)
        tip = d * _ARROW_TIP_RADIUS - _ARROW_ROUNDING
        base = d * _ARROW_BASE_RADIUS + _ARROW_ROUNDING
        half = d * _ARROW_HALF_WIDTH - _ARROW_ROUNDING
        offsets = {
            'up': (QPointF(0, -tip), QPointF(-half, -base), QPointF(half, -base)),
            'down': (QPointF(0, tip), QPointF(-half, base), QPointF(half, base)),
            'left': (QPointF(-tip, 0), QPointF(-base, -half), QPointF(-base, half)),
            'right': (QPointF(tip, 0), QPointF(base, -half), QPointF(base, half)),
        }
        # QRect::center() truncates to integers (105 for a 212px widget); the
        # disk and the zone circles are painted from the float centre (106), so
        # the arrows must use the same exact centre to sit inside them evenly.
        center = QPointF(self.width() / 2.0, self.height() / 2.0)
        return QPolygonF([center + offset for offset in offsets[zone]])

    def _arrow_shape(self, zone: str) -> QPainterPath:
        """Filled rounded triangle: the polygon dilated by _ARROW_ROUNDING with rounded corners.

        Built as a stroked outline and filled without a pen — stroking a closed
        polygon with a pen lands a pixel off in the Qt raster engine.
        """
        path = QPainterPath()
        path.addPolygon(self._arrow_polygon(zone))
        path.closeSubpath()
        stroker = QPainterPathStroker()
        stroker.setWidth(2 * _ARROW_ROUNDING)
        stroker.setJoinStyle(Qt.RoundJoin)
        stroker.setCapStyle(Qt.RoundCap)
        return stroker.createStroke(path)

    def _paint_zone_feedback(  # noqa: PLR0913
        self,
        painter: QPainter,
        rect: QRectF,
        pressed_zone: str | None,
        hover_zone: str | None,
    ) -> None:
        """Hover/press circle behind an arrow, in the style of the pill's flat buttons."""
        zone_d = self._diameter * _ZONE_DIAMETER
        zone_radius = self._diameter * _ZONE_CENTER_RADIUS
        zone_offsets = {
            'up': QPointF(0, -zone_radius),
            'down': QPointF(0, zone_radius),
            'left': QPointF(-zone_radius, 0),
            'right': QPointF(zone_radius, 0),
        }
        for zone, offset in zone_offsets.items():
            zone_pressed = zone == pressed_zone
            zone_hovered = zone == hover_zone
            if not (zone_pressed or zone_hovered):
                continue
            zone_center = rect.center() + offset
            zone_rect = QRectF(zone_center.x() - zone_d / 2, zone_center.y() - zone_d / 2, zone_d, zone_d)
            if zone_pressed:
                _paint_body(painter, zone_rect, pressed=True)
                _paint_rim(painter, zone_rect, pressed=True)
            else:
                painter.setBrush(QColor(HOVER_COLOR))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(zone_rect)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(Qt.NoPen)

    def _paint_inner_well(self, painter: QPainter, inner: QRectF, pressed_ok: bool) -> None:
        """Recessed OK centre: dark well with a light ring along its edge."""
        well = QLinearGradient(inner.topLeft(), inner.bottomRight())
        if pressed_ok:
            well.setColorAt(0.0, QColor(BUTTON_PRESSED_TOP))
            well.setColorAt(1.0, QColor(BUTTON_PRESSED_BOTTOM))
        else:
            well.setColorAt(0.0, QColor(DPAD_WELL_TOP))
            well.setColorAt(1.0, QColor(DPAD_WELL_BOTTOM))
        painter.setBrush(well)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(inner)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(DPAD_RING_COLOR), 2))
        painter.drawEllipse(inner)
        painter.setPen(Qt.NoPen)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        d = float(self._diameter)
        pad = (self.width() - d) / 2
        rect = QRectF(pad, pad, d, d)
        enabled = self.isEnabled()
        pressed_zone = self._zone if enabled else None
        hover_zone = self._hover_zone if enabled else None

        _paint_circle_halo(painter, rect, inflate=16, dy=5, alpha=60, enabled=enabled)

        body = QLinearGradient(rect.topLeft(), rect.bottomRight())
        body.setColorAt(0.0, QColor(BUTTON_TOP))
        body.setColorAt(1.0, QColor(DPAD_DISK_BOTTOM))
        painter.setBrush(body)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect)
        self._paint_zone_feedback(painter, rect, pressed_zone, hover_zone)

        inner = QRectF(
            rect.center().x() - self._inner_diameter / 2,
            rect.center().y() - self._inner_diameter / 2,
            self._inner_diameter,
            self._inner_diameter,
        )
        self._paint_inner_well(painter, inner, pressed_zone == 'ok')

        for zone in ('up', 'down', 'left', 'right'):
            color = QColor(TEXT_BRIGHT_COLOR if zone == pressed_zone else DPAD_ARROW_COLOR)
            if not enabled:
                color.setAlpha(60)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            shape = self._arrow_shape(zone)
            painter.drawPath(shape)
            painter.drawPolygon(self._arrow_polygon(zone))

        ok_color = QColor(TEXT_BRIGHT_COLOR if pressed_zone == 'ok' else DPAD_OK_COLOR)
        if not enabled:
            ok_color.setAlpha(60)
        ok_font = _ui_font(int(self._inner_diameter * 0.20))
        ok_font.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
        painter.setFont(ok_font)
        painter.setPen(QPen(ok_color, 1))
        painter.drawText(inner, Qt.AlignCenter, 'OK')

    def _zone_at(self, pos) -> str | None:
        center = self.rect().center()
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        distance = math.hypot(dx, dy)
        if distance > self._diameter / 2:
            return None
        if distance <= self._inner_diameter / 2 + 6:
            return 'ok'
        angle = math.degrees(math.atan2(-dy, dx))
        sector = _SECTOR_DEGREES
        if sector <= angle < 3 * sector:
            return 'up'
        if -sector <= angle < sector:
            return 'right'
        if -3 * sector <= angle < -sector:
            return 'down'
        return 'left'

    def mousePressEvent(self, event) -> None:  # noqa: N802
        zone = self._zone_at(event.pos())
        if zone and self.isEnabled():
            self._zone = zone
            self.activated.emit(self.KEY_BY_ZONE[zone])
            self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        zone = self._zone_at(event.pos())
        if self._zone:
            self._zone = zone
            self.update()
        if zone != self._hover_zone:
            self._hover_zone = zone
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._zone = None
        self._hover_zone = self._zone_at(event.pos())
        self.update()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_zone = None
        self.update()
        super().leaveEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.EnabledChange:
            self._hover_zone = None
            self.update()


class DigitPad(QWidget):
    """Overlay panel with channel number buttons."""

    digit = pyqtSignal(str)
    closed = pyqtSignal()

    def __init__(self, width: int = 292, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        button_size = 45
        cell = button_size + 2 * 16  # lighter halo inside the panel: smaller shadow pad
        margin = 12
        spacing = 10
        panel_width = 3 * cell + 2 * spacing + 2 * margin
        panel_height = 4 * cell + 3 * spacing + 2 * margin
        self.setFixedSize(panel_width + 2 * SHADOW_PAD, panel_height + 2 * SHADOW_PAD)

        layout = QGridLayout(self)
        layout.setContentsMargins(SHADOW_PAD + margin, SHADOW_PAD + margin, SHADOW_PAD + margin, SHADOW_PAD + margin)
        layout.setSpacing(spacing)

        for number in range(1, 10):
            button = NeuCircleButton(button_size, text=str(number), parent=self, pad=16)
            button.clicked.connect(lambda _checked=False, n=str(number): self.digit.emit(n))
            layout.addWidget(button, (number - 1) // 3, (number - 1) % 3)

        zero_button = NeuCircleButton(button_size, text='0', parent=self, pad=16)
        zero_button.clicked.connect(lambda _checked=False: self.digit.emit('0'))
        layout.addWidget(zero_button, 3, 1)

        close_button = NeuCircleButton(button_size, icon='close', kind='ghost', parent=self, pad=16)
        close_button.clicked.connect(self.closed.emit)
        layout.addWidget(close_button, 3, 0)

        done_button = NeuCircleButton(button_size, icon='check', parent=self, pad=16)
        done_button.clicked.connect(self.closed.emit)
        layout.addWidget(done_button, 3, 2)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(
            SHADOW_PAD,
            SHADOW_PAD,
            self.width() - 2 * SHADOW_PAD,
            self.height() - 2 * SHADOW_PAD,
        )
        _paint_rounded_halo(painter, rect, 26)
        painter.setBrush(QColor(PANEL_COLOR))
        painter.setPen(QPen(QColor(255, 255, 255, 14), 1))
        painter.drawRoundedRect(rect, 26, 26)
