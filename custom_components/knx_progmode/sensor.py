"""Sensor exposing the list and count of KNX devices in programming mode."""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_UPDATE
from .coordinator import KnxProgmodeScanner


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    scanner: KnxProgmodeScanner = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KnxProgmodeCountSensor(scanner, entry.entry_id)])


class KnxProgmodeCountSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Devices in programming mode"
    _attr_icon = "mdi:cog-sync"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "devices"
    _attr_should_poll = False

    def __init__(self, scanner: KnxProgmodeScanner, entry_id: str) -> None:
        self._scanner = scanner
        self._attr_unique_id = f"{entry_id}_count"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        return len(self._scanner.devices)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        devices = list(self._scanner.devices.values())
        return {
            "scanning": self._scanner.enabled,
            "addresses": [d["address"] for d in devices],
            "devices": devices,
        }
