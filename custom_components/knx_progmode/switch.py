"""Switch entity that arms/disarms the programming-mode scanner."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DEFAULT_SCAN_ENABLED, DOMAIN, SIGNAL_UPDATE
from .coordinator import KnxProgmodeScanner, build_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    scanner: KnxProgmodeScanner = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KnxProgmodeScanSwitch(scanner, entry.entry_id)])


class KnxProgmodeScanSwitch(SwitchEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_name = "Scanning"
    _attr_icon = "mdi:radar"
    _attr_should_poll = False

    def __init__(self, scanner: KnxProgmodeScanner, entry_id: str) -> None:
        self._scanner = scanner
        self._attr_unique_id = f"{entry_id}_scan_enabled"
        self._attr_device_info = build_device_info(entry_id)

    async def async_added_to_hass(self) -> None:
        last = await self.async_get_last_state()
        enabled = (
            last.state == "on" if last is not None else DEFAULT_SCAN_ENABLED
        )
        self._scanner.async_set_enabled(enabled)
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        return self._scanner.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._scanner.async_set_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._scanner.async_set_enabled(False)
        self.async_write_ha_state()
