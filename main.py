import asyncio
import logging
import sys
from functools import partial
from pathlib import Path

from androidtvremote2 import CannotConnect, ConnectionClosed
from PyQt5.QtCore import QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from qasync import QEventLoop

from remote_control import RemoteControl
from ui_widgets import (
    CARD_COLOR,
    FONT_FAMILIES,
    SHADOW_PAD,
    DigitPad,
    DPadWidget,
    NeuCircleButton,
    NeuPill,
)

_LOGGER = logging.getLogger(__name__)

WINDOW_MARGIN = 24  # transparent frame around the card, room for the painted shadow
CARD_RADIUS = 30
WINDOW_WIDTH = 388
WINDOW_HEIGHT = 760
DRAG_ZONE_HEIGHT = 140  # window area (from the top) that can be used to drag the frameless window


class MainWindow(QWidget):
    availability_changed = pyqtSignal(bool)
    invalid_auth = pyqtSignal()

    def __init__(self):
        super().__init__()

        Path('keys').mkdir(parents=True, exist_ok=True)

        self.is_connected = False
        self._device_name: str | None = None
        self._pair_task: asyncio.Task | None = None
        self._remote_buttons: list[QWidget] = []
        self._drag_offset = None
        self.remote_control = RemoteControl()
        self.remote_control.set_callbacks(
            on_availability=self.availability_changed.emit,
            on_invalid_auth=self.invalid_auth.emit,
        )
        self.availability_changed.connect(self._on_availability)
        self.invalid_auth.connect(self._on_invalid_auth)

        self._main_window_configure()
        self._create_tray()
        self._build_ui()
        self._set_remote_buttons_enabled(False)

    def _build_ui(self) -> None:
        content = QVBoxLayout()
        content.setContentsMargins(WINDOW_MARGIN + 24, WINDOW_MARGIN + 26, WINDOW_MARGIN + 24, WINDOW_MARGIN + 26)
        content.setSpacing(2)

        content.addLayout(self._build_header())
        content.addLayout(self._build_button_rows())
        content.addLayout(self._build_middle_row(), stretch=1)

        dpad_row = QHBoxLayout()
        self.dpad = DPadWidget()
        self.dpad.activated.connect(self._send_key)
        dpad_row.addWidget(self.dpad, alignment=Qt.AlignHCenter)
        self._remote_buttons.append(self.dpad)
        content.addLayout(dpad_row)
        self.setLayout(content)

        self.digit_pad = DigitPad(292, parent=self)
        self.digit_pad.move(
            (self.width() - self.digit_pad.width()) // 2,
            WINDOW_HEIGHT - WINDOW_MARGIN - 26 - self.digit_pad.height() + SHADOW_PAD,
        )
        self.digit_pad.digit.connect(self._send_key)
        self.digit_pad.closed.connect(self.digit_pad.hide)
        self.digit_pad.hide()
        self._remote_buttons.append(self.digit_pad)

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setSpacing(0)

        titles = QVBoxLayout()
        titles.setSpacing(3)
        self.title_label = QLabel('TV Remote Control')
        self.title_label.setStyleSheet(
            f'color: #DCDCE2; font-size: 16px; background: transparent; font-family: "{FONT_FAMILIES[0]}";'
        )
        self.search_label = QLabel('Not connected')
        self.search_label.setStyleSheet('color: #84848D; font-size: 11px; background: transparent;')
        titles.addWidget(self.title_label)
        titles.addWidget(self.search_label)
        header.addLayout(titles)

        header.addStretch()
        self.search_button = NeuCircleButton(36, icon='refresh', kind='ghost')
        self.search_button.clicked.connect(self._on_search)
        header.addWidget(self.search_button, alignment=Qt.AlignTop)
        return header

    def _build_button_rows(self) -> QVBoxLayout:
        rows = QVBoxLayout()
        rows.setSpacing(2)

        first_row = QHBoxLayout()
        first_row.setSpacing(0)
        power = NeuCircleButton(icon='power', kind='accent')
        power.clicked.connect(partial(self._send_key, RemoteControl.POWER))
        back = NeuCircleButton(icon='back')
        back.clicked.connect(partial(self._send_key, RemoteControl.BACK))
        menu = NeuCircleButton(icon='menu')
        menu.clicked.connect(partial(self._send_key, RemoteControl.MENU))
        for button in (power, back, menu):
            first_row.addWidget(button, alignment=Qt.AlignHCenter)
            self._remote_buttons.append(button)
        rows.addLayout(first_row)

        second_row = QHBoxLayout()
        second_row.setSpacing(0)
        mute = NeuCircleButton(icon='mute')
        mute.clicked.connect(partial(self._send_key, RemoteControl.VOLUME_MUTE))
        home = NeuCircleButton(icon='home')
        home.clicked.connect(partial(self._send_key, RemoteControl.HOME))
        pad_button = NeuCircleButton(text='123')
        pad_button.clicked.connect(self._toggle_digit_pad)
        second_row.addWidget(mute, alignment=Qt.AlignHCenter)
        second_row.addWidget(home, alignment=Qt.AlignHCenter)
        second_row.addWidget(pad_button, alignment=Qt.AlignHCenter)
        self._remote_buttons.extend((mute, home, pad_button))
        rows.addLayout(second_row)

        return rows

    def _build_middle_row(self) -> QHBoxLayout:
        middle = QHBoxLayout()

        pill_ch = NeuPill('CH', 'chevron-up', 'chevron-down')
        pill_ch.top_button.clicked.connect(partial(self._send_key, RemoteControl.CHANNEL_UP))
        pill_ch.bottom_button.clicked.connect(partial(self._send_key, RemoteControl.CHANNEL_DOWN))
        self._remote_buttons.append(pill_ch)

        pill_vol = NeuPill('VOL', 'plus', 'minus')
        pill_vol.top_button.clicked.connect(partial(self._send_key, RemoteControl.VOLUME_UP))
        pill_vol.bottom_button.clicked.connect(partial(self._send_key, RemoteControl.VOLUME_DOWN))
        self._remote_buttons.append(pill_vol)

        middle.addStretch(1)
        middle.addWidget(pill_ch, alignment=Qt.AlignVCenter)
        middle.addStretch(1)
        middle.addWidget(pill_vol, alignment=Qt.AlignVCenter)
        middle.addStretch(1)
        return middle

    def _toggle_digit_pad(self) -> None:
        if self.digit_pad.isVisible():
            self.digit_pad.hide()
        else:
            self.digit_pad.show()
            self.digit_pad.raise_()

    def closeEvent(self, event):  # noqa: N802
        event.ignore()
        self.hide()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        margin = float(WINDOW_MARGIN)
        card = QRectF(margin, margin, self.width() - 2 * margin, self.height() - 2 * margin)

        painter.setPen(Qt.NoPen)
        for inflate, alpha in ((20, 14), (12, 22), (6, 30)):
            shadow = card.adjusted(-inflate, -inflate, inflate, inflate + 3)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(shadow, CARD_RADIUS + inflate, CARD_RADIUS + inflate)

        painter.setBrush(QColor(CARD_COLOR))
        painter.drawRoundedRect(card, CARD_RADIUS, CARD_RADIUS)
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 12), 1))
        painter.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), CARD_RADIUS, CARD_RADIUS)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and event.pos().y() <= DRAG_ZONE_HEIGHT:
            handle = self.windowHandle()
            if handle is None or not handle.startSystemMove():
                self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def _main_window_configure(self) -> None:
        self.setWindowTitle('TV Remote Control')
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setStyleSheet("""
            QLabel {
                color: #DCDCE2;
                background: transparent;
            }
            QInputDialog, QDialog {
                background-color: #242429;
            }
            QInputDialog QLabel {
                color: #CACAD0;
                font-size: 13px;
            }
            QDialog QPushButton {
                background-color: #2B2B31;
                color: #E6E6EB;
                font-size: 13px;
                padding: 8px 18px;
                border: none;
                border-radius: 17px;
            }
            QDialog QPushButton:hover {
                background-color: #33333A;
            }
            QDialog QPushButton:pressed {
                background-color: #1D1D22;
            }
            QDialog QLineEdit {
                font-size: 16px;
                padding: 8px 12px;
                border: 1px solid #3A3A42;
                border-radius: 12px;
                color: #E6E6EB;
                background-color: #1C1D22;
                selection-background-color: #FF6B3B;
            }
        """)

    def _on_tray_icon_activated(self, reason: int) -> None:
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self._show()

    def _show(self) -> None:
        self.show()
        self.activateWindow()

    def _exit_app(self) -> None:
        self.tray_icon.hide()
        try:
            self.remote_control.disconnect()
        except Exception as exc:
            _LOGGER.error('Disconnect Error: %s', exc)
        QApplication.instance().quit()

    def _create_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon('resources/icon32.ico'))

        tray_menu = QMenu()

        open_action = QAction('Open', self)
        open_action.triggered.connect(self._show)
        tray_menu.addAction(open_action)

        exit_action = QAction('Exit', self)
        exit_action.triggered.connect(self._exit_app)
        tray_menu.addAction(exit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        self.tray_icon.activated.connect(self._on_tray_icon_activated)

    def _set_connection_state(self, connected: bool, label: str) -> None:
        self.is_connected = connected
        self.search_label.setText(label)
        self._set_remote_buttons_enabled(connected)

    def _set_remote_buttons_enabled(self, enabled: bool) -> None:
        for button in self._remote_buttons:
            button.setEnabled(enabled)

    def _on_availability(self, is_available: bool) -> None:
        if is_available and self._device_name:
            self._set_connection_state(True, self._device_name)
        elif is_available:
            self._set_connection_state(False, 'Not connected')
        else:
            self._set_connection_state(False, 'Reconnecting...')

    def _on_invalid_auth(self) -> None:
        self._set_connection_state(False, 'Re-pairing...')
        self._on_search()

    def _send_key(self, key_code: str) -> None:
        try:
            self.remote_control.send_key(key_code)
        except Exception as exc:
            _LOGGER.error('Send key error: %s', exc)
            self._set_connection_state(False, 'Error')

    def _on_search(self) -> None:
        if self._pair_task and not self._pair_task.done():
            return
        self._pair_task = asyncio.create_task(self._pair())

    async def _pair(self) -> None:
        self.search_button.setEnabled(False)
        try:
            self._set_connection_state(False, 'Search...')
            addrs = await self.remote_control.find_android_tv()
            if not addrs:
                self.search_label.setText('Android TV not found')
                return

            self.search_label.setText(f'Pair to {addrs[0]}')
            await self.remote_control.pair(
                addrs[0],
                lambda: QInputDialog.getText(self, 'TV Remote Control', 'Enter the code:'),
            )
            device_info = self.remote_control.device_info()
            if device_info:
                self._device_name = f'{device_info["manufacturer"]} {device_info["model"]}'
                self._set_connection_state(True, self._device_name)
            else:
                self.search_label.setText('Not connected')
        except RuntimeError as exc:
            _LOGGER.info('Pairing interrupted: %s', exc)
            self.search_label.setText('Not connected')
        except (CannotConnect, ConnectionClosed) as exc:
            _LOGGER.error('Connect error: %s', exc)
            self.search_label.setText('Not connected')
        except Exception as exc:
            _LOGGER.error('Pair error: %s', exc)
            self.search_label.setText('Error')
        finally:
            self.search_button.setEnabled(True)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s,%(msecs)d %(levelname)s %(name)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        level=logging.INFO,
        handlers=[
            logging.FileHandler('app.log'),
            logging.StreamHandler(sys.stdout),
        ],
    )

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    font = app.font()
    font.setFamilies(FONT_FAMILIES)
    app.setFont(font)

    app.setWindowIcon(QIcon('resources/icon32.ico'))

    window = MainWindow()
    window.show()

    with loop:
        sys.exit(loop.run_forever())
