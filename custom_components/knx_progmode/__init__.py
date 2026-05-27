"""KNX programming-mode watcher integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_IDENTIFY,
    CONF_INTERVAL,
    CONF_TIMEOUT,
    DEFAULT_IDENTIFY,
    DEFAULT_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
    LOGGER,
)
from .coordinator import KnxProgmodeScanner

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
]


def _resolve_xknx(hass: HomeAssistant):
    """Find the XKNX instance owned by the KNX integration."""
    knx_data = hass.data.get("knx")
    if knx_data is None:
        return None
    xknx = getattr(knx_data, "xknx", None)
    if xknx is not None:
        return xknx
    if isinstance(knx_data, dict):
        for value in knx_data.values():
            xknx = getattr(value, "xknx", None)
            if xknx is not None:
                return xknx
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    xknx = _resolve_xknx(hass)
    if xknx is None:
        raise ConfigEntryNotReady(
            "KNX integration is not loaded; configure HA's KNX integration first."
        )

    options = entry.options or entry.data
    scanner = KnxProgmodeScanner(
        hass,
        xknx,
        timeout=float(options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)),
        interval=float(options.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
        identify=bool(options.get(CONF_IDENTIFY, DEFAULT_IDENTIFY)),
    )
    await scanner.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = scanner
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    LOGGER.info(
        "knx_progmode loaded (timeout=%.1fs interval=%.1fs identify=%s)",
        scanner.timeout,
        scanner.interval,
        scanner.identify,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        scanner: KnxProgmodeScanner = hass.data[DOMAIN].pop(entry.entry_id)
        await scanner.async_stop()
    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
