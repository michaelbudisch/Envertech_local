"""Config flow for Envertech Local."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_IP_ADDRESS, CONF_PORT, CONF_UNIQUE_ID
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DISCOVERY_TIMEOUT,
    INTEGRATION_NAME,
    POLL_INTERVAL_CHOICES,
    DOMAIN,
)
from .discovery import discover_devices
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)

# Config-flow schemas must be serializable for the Home Assistant frontend.
# Bare validator functions cause HTTP 500 errors in the schema serializer.
_IPV4_OCTET = r"(?:25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
IPV4_VALIDATOR = vol.All(
    str, vol.Match(rf"^(?:{_IPV4_OCTET}\\.){{3}}{_IPV4_OCTET}$")
)
PORT_VALIDATOR = vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))


class InverterMonitorOptionsFlow(config_entries.OptionsFlow):
    """Options flow for Envertech Local (poll interval)."""

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Handle the options flow."""
        if user_input is not None:
            interval = int(user_input[CONF_POLL_INTERVAL])
            if interval not in POLL_INTERVAL_CHOICES:
                interval = DEFAULT_POLL_INTERVAL
            user_input[CONF_POLL_INTERVAL] = interval
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get(
            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_POLL_INTERVAL, default=current): vol.In(
                        POLL_INTERVAL_CHOICES
                    ),
                }
            ),
        )



class InverterMonitorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Envertech Local."""

    VERSION = 1

    def __init__(self) -> None:
        self.discovered_devices: list[dict] = []

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> InverterMonitorOptionsFlow:
        """Return the options flow handler."""
        return InverterMonitorOptionsFlow()

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle the initial step with discovery."""
        errors: dict[str, str] = {}

        try:
            self.discovered_devices = await discover_devices(timeout=DISCOVERY_TIMEOUT)
        except Exception:
            _LOGGER.exception("Device discovery failed")
            self.discovered_devices = []

        existing_entries = self.hass.config_entries.async_entries(DOMAIN)
        existing_ids = {
            entry.data[CONF_UNIQUE_ID]
            for entry in existing_entries
            if CONF_UNIQUE_ID in entry.data
        }

        filtered_devices = [
            device
            for device in self.discovered_devices
            if device.get("serial_number") not in existing_ids
        ]
        ip_to_sn = {d["ip"]: d["serial_number"] for d in filtered_devices}

        if user_input is not None:
            selected_ip = user_input[CONF_IP_ADDRESS]

            if selected_ip == "manual":
                return await self.async_step_manual()

            sn = ip_to_sn.get(selected_ip)
            if not sn:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(sn)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"{INTEGRATION_NAME} {sn}",
                    data={
                        CONF_IP_ADDRESS: selected_ip,
                        CONF_UNIQUE_ID: sn,
                        CONF_PORT: user_input[CONF_PORT],
                    },
                )

        device_choices = {
            d["ip"]: f"{d['ip']} — {d['serial_number']}" for d in filtered_devices
        }
        device_choices["manual"] = "Manual entry"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IP_ADDRESS): vol.In(device_choices),
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): PORT_VALIDATOR,
                }
            ),
            errors=errors,
            description_placeholders={
                "discovered_devices": ", ".join(
                    f"{d['ip']} — {d['serial_number']}"
                    for d in self.discovered_devices
                )
                or "none"
            },
        )

    async def async_step_manual(self, user_input: dict | None = None) -> FlowResult:
        """Handle manual entry of device details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            sn = user_input[CONF_UNIQUE_ID].strip()
            await self.async_set_unique_id(sn)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"{INTEGRATION_NAME} {sn}",
                data={
                    CONF_IP_ADDRESS: user_input[CONF_IP_ADDRESS].strip(),
                    CONF_UNIQUE_ID: sn,
                    CONF_PORT: user_input[CONF_PORT],
                },
            )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_IP_ADDRESS): IPV4_VALIDATOR,
                    vol.Required(CONF_UNIQUE_ID): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): PORT_VALIDATOR,
                }
            ),
            errors=errors,
        )
