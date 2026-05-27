"""Config flow for the KNX programming-mode watcher."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from .const import (
    CONF_IDENTIFY,
    CONF_INTERVAL,
    CONF_TIMEOUT,
    DEFAULT_IDENTIFY,
    DEFAULT_INTERVAL,
    DEFAULT_TIMEOUT,
    DOMAIN,
)


class KnxProgmodeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(
            title="KNX Programming Mode",
            data={},
            options={
                CONF_TIMEOUT: DEFAULT_TIMEOUT,
                CONF_INTERVAL: DEFAULT_INTERVAL,
                CONF_IDENTIFY: DEFAULT_IDENTIFY,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return KnxProgmodeOptionsFlow(entry)


class KnxProgmodeOptionsFlow(OptionsFlow):
    def __init__(self, entry: ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.entry.options or {}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_TIMEOUT,
                    default=current.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=30.0)),
                vol.Required(
                    CONF_INTERVAL,
                    default=current.get(CONF_INTERVAL, DEFAULT_INTERVAL),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=300.0)),
                vol.Required(
                    CONF_IDENTIFY,
                    default=current.get(CONF_IDENTIFY, DEFAULT_IDENTIFY),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
