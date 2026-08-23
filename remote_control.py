import asyncio
import logging
from typing import Callable

from androidtvremote2 import (
    AndroidTVRemote,
    CannotConnect,
    ConnectionClosed,
    InvalidAuth,
)
from zeroconf import IPVersion, ServiceStateChange, Zeroconf
from zeroconf._services.info import AsyncServiceInfo
from zeroconf.asyncio import AsyncServiceBrowser, AsyncZeroconf

_LOGGER = logging.getLogger(__name__)


class RemoteControl:
    POWER: str = 'POWER'
    BACK: str = 'BACK'
    HOME: str = 'HOME'
    MENU: str = 'MENU'
    VOLUME_MUTE: str = 'MUTE'
    VOLUME_UP: str = 'VOLUME_UP'
    VOLUME_DOWN: str = 'VOLUME_DOWN'
    DPAD_UP: str = 'DPAD_UP'
    DPAD_DOWN: str = 'DPAD_DOWN'
    DPAD_LEFT: str = 'DPAD_LEFT'
    DPAD_RIGHT: str = 'DPAD_RIGHT'
    DPAD_CENTER: str = 'DPAD_CENTER'
    CHANNEL_UP: str = 'CHANNEL_UP'
    CHANNEL_DOWN: str = 'CHANNEL_DOWN'

    def __init__(self):
        self.found_addresses: list = []
        self.remote: AndroidTVRemote | None = None

    async def find_android_tv(self) -> list:
        self.found_addresses = []

        zc = AsyncZeroconf()
        services = ['_androidtvremote2._tcp.local.']
        browser = AsyncServiceBrowser(zc.zeroconf, services, handlers=[self._async_on_service_state_change])

        await asyncio.sleep(5)

        await browser.async_cancel()
        await zc.async_close()

        return self.found_addresses

    async def pair(self, host: str, callback: Callable):
        self.remote = AndroidTVRemote(
            'Android TV Remote Control',
            'keys/cert.pem',
            'keys/key.pem',
            host,
        )

        if await self.remote.async_generate_cert_if_missing():
            _LOGGER.info('Generated new certificate')
            await self._pair(callback)

        while True:
            try:
                await self.remote.async_connect()
                break
            except InvalidAuth as exc:
                _LOGGER.error('Need to pair again. Error: %s', exc)
                await self._pair(callback)
            except (CannotConnect, ConnectionClosed) as exc:
                _LOGGER.error('Cannot connect, exiting. Error: %s', exc)
                return

        self.remote.keep_reconnecting()

        _LOGGER.info('device_info: %s', self.remote.device_info)
        _LOGGER.info('is_on: %s', self.remote.is_on)
        _LOGGER.info('current_app: %s', self.remote.current_app)
        _LOGGER.info('volume_info: %s', self.remote.volume_info)

        self.remote.add_is_on_updated_callback(self._is_on_updated)
        self.remote.add_current_app_updated_callback(self._current_app_updated)
        self.remote.add_volume_info_updated_callback(self._volume_info_updated)
        self.remote.add_is_available_updated_callback(self._is_available_updated)

    def power(self) -> None:
        self.remote.send_key_command(self.POWER)

    def back(self) -> None:
        self.remote.send_key_command(self.BACK)

    def home(self) -> None:
        self.remote.send_key_command(self.HOME)

    def menu(self) -> None:
        self.remote.send_key_command(self.MENU)

    def channel_up(self) -> None:
        self.remote.send_key_command(self.CHANNEL_UP)

    def channel_down(self) -> None:
        self.remote.send_key_command(self.CHANNEL_DOWN)

    def volume_mute(self) -> None:
        self.remote.send_key_command(self.VOLUME_MUTE)

    def volume_up(self) -> None:
        self.remote.send_key_command(self.VOLUME_UP)

    def volume_down(self) -> None:
        self.remote.send_key_command(self.VOLUME_DOWN)

    def dpad_up(self) -> None:
        self.remote.send_key_command(self.DPAD_UP)

    def dpad_down(self) -> None:
        self.remote.send_key_command(self.DPAD_DOWN)

    def dpad_left(self) -> None:
        self.remote.send_key_command(self.DPAD_LEFT)

    def dpad_right(self) -> None:
        self.remote.send_key_command(self.DPAD_RIGHT)

    def dpad_center(self) -> None:
        self.remote.send_key_command(self.DPAD_CENTER)

    def device_info(self) -> dict[str, str] | None:
        return self.remote.device_info

    def disconnect(self):
        self.remote.disconnect()

    async def _pair(self, callback: Callable) -> None:
        await self.remote.async_start_pairing()
        while True:
            pairing_code, done = callback()
            if not done:
                self.remote.disconnect()
                raise RuntimeError('Interrupted by user')

            try:
                return await self.remote.async_finish_pairing(pairing_code)
            except InvalidAuth as exc:
                _LOGGER.error('Invalid pairing code. Error: %s', exc)
                continue
            except ConnectionClosed as exc:
                _LOGGER.error('Initialize pair again. Error: %s', exc)
                return await self._pair(callback)

    def _async_on_service_state_change(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        state_change: ServiceStateChange,
    ) -> None:
        if state_change is not ServiceStateChange.Added:
            return
        asyncio.ensure_future(self._async_display_service_info(zeroconf, service_type, name))

    async def _async_display_service_info(self, zeroconf: Zeroconf, service_type: str, name: str) -> None:
        info = AsyncServiceInfo(service_type, name)
        await info.async_request(zeroconf, 2000)

        if info:
            self.found_addresses.extend(info.parsed_scoped_addresses(IPVersion.V4Only))

    def _is_on_updated(self, is_on: bool) -> None:
        _LOGGER.info('Notified that is_on: %s', is_on)

    def _current_app_updated(self, current_app: str) -> None:
        _LOGGER.info('Notified that current_app: %s', current_app)

    def _volume_info_updated(self, volume_info: dict[str, str | bool]) -> None:
        _LOGGER.info('Notified that volume_info: %s', volume_info)

    def _is_available_updated(self, is_available: bool) -> None:
        _LOGGER.info('Notified that is_available: %s', is_available)
