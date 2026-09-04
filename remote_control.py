import asyncio
import logging
from typing import Callable

from androidtvremote2 import (
    AndroidTVRemote,
    CannotConnect,
    ConnectionClosed,
    InvalidAuth,
)
from androidtvremote2.model import DeviceInfo, VolumeInfo
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
        self.remote: AndroidTVRemote | None = None
        self._generation = 0
        self._on_availability: Callable[[bool], None] | None = None
        self._on_invalid_auth: Callable[[], None] | None = None

    def set_callbacks(
        self,
        on_availability: Callable[[bool], None],
        on_invalid_auth: Callable[[], None],
    ) -> None:
        """Register UI callbacks for connection state changes."""
        self._on_availability = on_availability
        self._on_invalid_auth = on_invalid_auth

    async def find_android_tv(self) -> list[str]:
        found: list[str] = []
        tasks: list[asyncio.Task] = []

        def on_service_state_change(
            zeroconf: Zeroconf,
            service_type: str,
            name: str,
            state_change: ServiceStateChange,
        ) -> None:
            if state_change is not ServiceStateChange.Added:
                return
            tasks.append(asyncio.ensure_future(self._async_display_service_info(zeroconf, service_type, name, found)))

        zc = AsyncZeroconf()
        services = ['_androidtvremote2._tcp.local.']
        browser = AsyncServiceBrowser(zc.zeroconf, services, handlers=[on_service_state_change])

        await asyncio.sleep(5)

        await browser.async_cancel()
        await zc.async_close()
        await asyncio.gather(*tasks, return_exceptions=True)

        return found

    async def pair(self, host: str, callback: Callable) -> None:
        if self.remote:
            self.remote.disconnect()

        self._generation += 1
        generation = self._generation

        self.remote = AndroidTVRemote(
            'Android TV Remote Control',
            'keys/cert.pem',
            'keys/key.pem',
            host,
        )

        if await self.remote.async_generate_cert_if_missing():
            _LOGGER.info('Generated new certificate')
            await self._pair(callback)

        self.remote.add_is_on_updated_callback(self._is_on_updated)
        self.remote.add_current_app_updated_callback(self._current_app_updated)
        self.remote.add_volume_info_updated_callback(self._volume_info_updated)
        self.remote.add_is_available_updated_callback(
            lambda is_available: self._is_available_updated(generation, is_available)
        )

        while True:
            try:
                await self.remote.async_connect()
                break
            except InvalidAuth as exc:
                _LOGGER.error('Need to pair again. Error: %s', exc)
                await self._pair(callback)
            except (CannotConnect, ConnectionClosed) as exc:
                _LOGGER.error('Cannot connect. Error: %s', exc)
                raise

        self.remote.keep_reconnecting(invalid_auth_callback=lambda: self._invalid_auth(generation))

        _LOGGER.info('device_info: %s', self.remote.device_info)
        _LOGGER.info('is_on: %s', self.remote.is_on)
        _LOGGER.info('current_app: %s', self.remote.current_app)
        _LOGGER.info('volume_info: %s', self.remote.volume_info)

    def send_key(self, key_code: str) -> None:
        if self.remote is None:
            return
        self.remote.send_key_command(key_code)

    def device_info(self) -> DeviceInfo | None:
        if self.remote is None:
            return None
        return self.remote.device_info

    def disconnect(self) -> None:
        if self.remote is None:
            return
        self.remote.disconnect()

    async def _pair(self, callback: Callable) -> None:
        while True:
            await self.remote.async_start_pairing()
            while True:
                pairing_code, done = callback()
                if not done:
                    self.remote.disconnect()
                    raise RuntimeError('Interrupted by user')

                try:
                    await self.remote.async_finish_pairing(pairing_code)
                    return
                except InvalidAuth as exc:
                    _LOGGER.error('Invalid pairing code. Error: %s', exc)
                    continue
                except ConnectionClosed as exc:
                    _LOGGER.error('Initialize pair again. Error: %s', exc)
                    break

    async def _async_display_service_info(
        self,
        zeroconf: Zeroconf,
        service_type: str,
        name: str,
        found: list[str],
    ) -> None:
        info = AsyncServiceInfo(service_type, name)
        if not await info.async_request(zeroconf, 2000):
            return
        for address in info.parsed_scoped_addresses(IPVersion.V4Only):
            if address not in found:
                found.append(address)

    def _is_on_updated(self, is_on: bool) -> None:
        _LOGGER.info('Notified that is_on: %s', is_on)

    def _current_app_updated(self, current_app: str) -> None:
        _LOGGER.info('Notified that current_app: %s', current_app)

    def _volume_info_updated(self, volume_info: VolumeInfo) -> None:
        _LOGGER.info('Notified that volume_info: %s', volume_info)

    def _is_available_updated(self, generation: int, is_available: bool) -> None:
        _LOGGER.info('Notified that is_available: %s', is_available)
        if generation != self._generation:
            return
        if self._on_availability:
            self._on_availability(is_available)

    def _invalid_auth(self, generation: int) -> None:
        if generation != self._generation:
            return
        _LOGGER.warning('Invalid auth: TV requires re-pairing')
        if self._on_invalid_auth:
            self._on_invalid_auth()
