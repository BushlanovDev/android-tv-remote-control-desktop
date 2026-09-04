import asyncio
import logging
import sys
from functools import partial
from pathlib import Path
from typing import Callable

from androidtvremote2 import CannotConnect, ConnectionClosed
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from qasync import QEventLoop

from remote_control import RemoteControl

_LOGGER = logging.getLogger(__name__)


class MainWindow(QWidget):
    availability_changed = pyqtSignal(bool)
    invalid_auth = pyqtSignal()

    def __init__(self):
        super().__init__()

        Path('keys').mkdir(parents=True, exist_ok=True)

        self.is_connected = False
        self._device_name: str | None = None
        self._pair_task: asyncio.Task | None = None
        self._remote_buttons: list[QPushButton] = []
        self.remote_control = RemoteControl()
        self.remote_control.set_callbacks(
            on_availability=self.availability_changed.emit,
            on_invalid_auth=self.invalid_auth.emit,
        )
        self.availability_changed.connect(self._on_availability)
        self.invalid_auth.connect(self._on_invalid_auth)

        self._main_window_configure()
        self._create_tray()

        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(20, 0, 20, 0)

        self.search_label = QLabel('Not connected')
        top_layout.addWidget(self.search_label)

        self.search_button = QPushButton('⟲')
        self.search_button.setFixedSize(32, 32)
        self.search_button.clicked.connect(self._on_search)
        top_layout.addWidget(self.search_button)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        grid_layout = QGridLayout()
        grid_layout.setSpacing(15)
        grid_layout.setVerticalSpacing(15)

        self.add_button(grid_layout, 'Power', 0, 0, partial(self._send_key, RemoteControl.POWER))
        self.add_button(grid_layout, 'Back', 0, 1, partial(self._send_key, RemoteControl.BACK))
        self.add_button(grid_layout, 'Menu', 0, 2, partial(self._send_key, RemoteControl.MENU))

        self.add_button(grid_layout, 'CH▲', 1, 0, partial(self._send_key, RemoteControl.CHANNEL_UP))
        self.add_button(grid_layout, 'Home', 1, 1, partial(self._send_key, RemoteControl.HOME))
        self.add_button(grid_layout, 'VOL+', 1, 2, partial(self._send_key, RemoteControl.VOLUME_UP))

        self.add_button(grid_layout, 'CH▼', 2, 0, partial(self._send_key, RemoteControl.CHANNEL_DOWN))
        self.add_button(grid_layout, 'Mute', 2, 1, partial(self._send_key, RemoteControl.VOLUME_MUTE))
        self.add_button(grid_layout, 'VOL-', 2, 2, partial(self._send_key, RemoteControl.VOLUME_DOWN))

        navigation_layout = QGridLayout()
        navigation_layout.setHorizontalSpacing(10)

        self.add_button(navigation_layout, '▲', 0, 1, partial(self._send_key, RemoteControl.DPAD_UP))
        self.add_button(navigation_layout, '◀', 1, 0, partial(self._send_key, RemoteControl.DPAD_LEFT))
        self.add_button(navigation_layout, 'OK', 1, 1, partial(self._send_key, RemoteControl.DPAD_CENTER))
        self.add_button(navigation_layout, '▶', 1, 2, partial(self._send_key, RemoteControl.DPAD_RIGHT))
        self.add_button(navigation_layout, '▼', 2, 1, partial(self._send_key, RemoteControl.DPAD_DOWN))

        main_layout.addLayout(top_layout)
        main_layout.addLayout(grid_layout)
        main_layout.addLayout(navigation_layout)
        self.setLayout(main_layout)

        self._set_remote_buttons_enabled(False)

    def add_button(
        self,
        layout: QGridLayout,
        text: str,
        row: int,
        col: int,
        handler: Callable | None = None,
    ) -> None:
        button = QPushButton(text)
        button.setFixedSize(60, 60)

        layout.addWidget(button, row, col)

        if handler:
            button.clicked.connect(handler)

        self._remote_buttons.append(button)

    def closeEvent(self, event):  # noqa: N802
        event.ignore()
        self.hide()

    def _main_window_configure(self) -> None:
        self.setWindowTitle('TV Remote Control')
        self.setFixedSize(300, 560)
        self.setStyleSheet("""
            QLabel { color: white; font-size: 16px; }
            QPushButton {
                background-color: #333;
                color: white;
                font-size: 14px;
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: #444;
            }
            QPushButton:pressed {
                background-color: #555;
            }
            QInputDialog {
                background-color: #1E1E1E;
            }
            QDialog QPushButton {
                font-size: 14px;
                padding: 8px 16px;
                border-radius: 10px;
                color: white;
            }
            QDialog QLineEdit {
                font-size: 18px;
                padding: 6px;
                border: 2px solid #4CAF50;
                border-radius: 10px;
                color: white;
                background-color: #444;
            }
            MainWindow {
                background-color: #1E1E1E;
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
        datefmt='%H:%M:%S',
        level=logging.INFO,
        handlers=[
            logging.FileHandler('app.log'),
            logging.StreamHandler(sys.stdout),
        ],
    )

    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    app.setWindowIcon(QIcon('resources/icon32.ico'))

    window = MainWindow()
    window.show()

    with loop:
        sys.exit(loop.run_forever())
