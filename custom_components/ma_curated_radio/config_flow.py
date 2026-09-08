"""Config and options flows.

Replaces the five ``input_text`` helpers, the ``secrets.yaml`` Last.fm URL
and the hand-written ``rest_command`` the YAML version needed.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_ARTIST_MUTE_DAYS,
    CONF_ARTIST_STRIKE_LIMIT,
    CONF_COOLDOWN_ENTITY,
    CONF_COOLDOWN_SECONDS,
    CONF_DEGREES,
    CONF_FILTER_HOLIDAY,
    CONF_FILTER_LIVE,
    CONF_HISTORY_MINUTES,
    CONF_LASTFM_API_KEY,
    CONF_MA_CONFIG_ENTRY_ID,
    CONF_MAX_ARTISTS,
    CONF_MAX_CONSECUTIVE,
    CONF_MIN_DURATION,
    CONF_PLAYER,
    CONF_PROVIDER_FILTER,
    CONF_REFILL_THRESHOLD,
    CONF_SEED_LEAN,
    CONF_SETTLE_SECONDS,
    CONF_TRACK_SUPPRESS_DAYS,
    CONF_TRACKS_PER_ARTIST,
    CONF_USE_NATIVE_TOP_TRACKS,
    DEFAULT_ARTIST_MUTE_DAYS,
    DEFAULT_ARTIST_STRIKE_LIMIT,
    DEFAULT_COOLDOWN_SECONDS,
    DEFAULT_DEGREES,
    DEFAULT_FILTER_HOLIDAY,
    DEFAULT_FILTER_LIVE,
    DEFAULT_HISTORY_MINUTES,
    DEFAULT_MAX_ARTISTS,
    DEFAULT_MAX_CONSECUTIVE,
    DEFAULT_MIN_DURATION,
    DEFAULT_PROVIDER_FILTER,
    DEFAULT_REFILL_THRESHOLD,
    DEFAULT_SEED_LEAN,
    DEFAULT_SETTLE_SECONDS,
    DEFAULT_TRACK_SUPPRESS_DAYS,
    DEFAULT_TRACKS_PER_ARTIST,
    DEFAULT_USE_NATIVE_TOP_TRACKS,
    DOMAIN,
    LASTFM_SIGNUP_URL,
    MA_DOMAIN,
    SEED_LEANS,
)
from .lastfm import async_validate_api_key

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PLAYER): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="media_player", integration=MA_DOMAIN)
        ),
        vol.Required(CONF_LASTFM_API_KEY): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
    }
)


def _number(minimum: int, maximum: int) -> selector.NumberSelector:
    """A plain integer box."""
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum, max=maximum, step=1, mode=selector.NumberSelectorMode.BOX
        )
    )


def _options_schema(current: dict[str, Any]) -> vol.Schema:
    """Build the tuning schema, pre-filled with what is configured now."""

    def value(key: str, default: Any) -> Any:
        return current.get(key, default)

    return vol.Schema(
        {
            vol.Required(
                CONF_MAX_ARTISTS,
                default=value(CONF_MAX_ARTISTS, DEFAULT_MAX_ARTISTS),
            ): _number(0, 15),
            vol.Required(
                CONF_TRACKS_PER_ARTIST,
                default=value(CONF_TRACKS_PER_ARTIST, DEFAULT_TRACKS_PER_ARTIST),
            ): _number(1, 10),
            vol.Required(
                CONF_SEED_LEAN,
                default=value(CONF_SEED_LEAN, DEFAULT_SEED_LEAN),
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=SEED_LEANS,
                    translation_key="seed_lean",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_DEGREES,
                default=value(CONF_DEGREES, DEFAULT_DEGREES),
            ): _number(0, 6),
            vol.Required(
                CONF_MIN_DURATION,
                default=value(CONF_MIN_DURATION, DEFAULT_MIN_DURATION),
            ): _number(0, 600),
            vol.Required(
                CONF_MAX_CONSECUTIVE,
                default=value(CONF_MAX_CONSECUTIVE, DEFAULT_MAX_CONSECUTIVE),
            ): _number(1, 5),
            vol.Required(
                CONF_TRACK_SUPPRESS_DAYS,
                default=value(CONF_TRACK_SUPPRESS_DAYS, DEFAULT_TRACK_SUPPRESS_DAYS),
            ): _number(0, 365),
            vol.Required(
                CONF_ARTIST_STRIKE_LIMIT,
                default=value(CONF_ARTIST_STRIKE_LIMIT, DEFAULT_ARTIST_STRIKE_LIMIT),
            ): _number(0, 10),
            vol.Required(
                CONF_ARTIST_MUTE_DAYS,
                default=value(CONF_ARTIST_MUTE_DAYS, DEFAULT_ARTIST_MUTE_DAYS),
            ): _number(0, 365),
            vol.Required(
                CONF_REFILL_THRESHOLD,
                default=value(CONF_REFILL_THRESHOLD, DEFAULT_REFILL_THRESHOLD),
            ): _number(0, 10),
            vol.Required(
                CONF_HISTORY_MINUTES,
                default=value(CONF_HISTORY_MINUTES, DEFAULT_HISTORY_MINUTES),
            ): _number(0, 1440),
            vol.Required(
                CONF_SETTLE_SECONDS,
                default=value(CONF_SETTLE_SECONDS, DEFAULT_SETTLE_SECONDS),
            ): _number(0, 30),
            vol.Optional(
                CONF_COOLDOWN_ENTITY,
                description={"suggested_value": value(CONF_COOLDOWN_ENTITY, None)},
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["script", "automation"])
            ),
            vol.Required(
                CONF_COOLDOWN_SECONDS,
                default=value(CONF_COOLDOWN_SECONDS, DEFAULT_COOLDOWN_SECONDS),
            ): _number(0, 3600),
            vol.Optional(
                CONF_PROVIDER_FILTER,
                description={
                    "suggested_value": value(
                        CONF_PROVIDER_FILTER, DEFAULT_PROVIDER_FILTER
                    )
                },
            ): selector.TextSelector(),
            vol.Required(
                CONF_FILTER_LIVE,
                default=value(CONF_FILTER_LIVE, DEFAULT_FILTER_LIVE),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_FILTER_HOLIDAY,
                default=value(CONF_FILTER_HOLIDAY, DEFAULT_FILTER_HOLIDAY),
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_USE_NATIVE_TOP_TRACKS,
                default=value(
                    CONF_USE_NATIVE_TOP_TRACKS, DEFAULT_USE_NATIVE_TOP_TRACKS
                ),
            ): selector.BooleanSelector(),
        }
    )


def _coerce_ints(data: dict[str, Any]) -> dict[str, Any]:
    """Number selectors hand back floats; the settings want whole numbers."""
    integer_keys = (
        CONF_MAX_ARTISTS,
        CONF_TRACKS_PER_ARTIST,
        CONF_REFILL_THRESHOLD,
        CONF_HISTORY_MINUTES,
        CONF_SETTLE_SECONDS,
        CONF_COOLDOWN_SECONDS,
        CONF_DEGREES,
        CONF_MAX_CONSECUTIVE,
        CONF_MIN_DURATION,
        CONF_TRACK_SUPPRESS_DAYS,
        CONF_ARTIST_STRIKE_LIMIT,
        CONF_ARTIST_MUTE_DAYS,
    )
    return {
        key: int(val) if key in integer_keys else val for key, val in data.items()
    }


class MaCuratedRadioConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up one player."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the player, the Music Assistant instance and the API key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_PLAYER])
            self._abort_if_unique_id_configured()

            ma_entry_id = self._music_assistant_entry_id(user_input[CONF_PLAYER])
            session = async_get_clientsession(self.hass)

            if ma_entry_id is None:
                errors[CONF_PLAYER] = "not_music_assistant"
            elif not await async_validate_api_key(
                session, user_input[CONF_LASTFM_API_KEY]
            ):
                errors[CONF_LASTFM_API_KEY] = "invalid_api_key"
            else:
                player = self.hass.states.get(user_input[CONF_PLAYER])
                title = (
                    player.attributes.get("friendly_name")
                    if player is not None
                    else None
                ) or user_input[CONF_PLAYER]
                return self.async_create_entry(
                    title=title,
                    data={**user_input, CONF_MA_CONFIG_ENTRY_ID: ma_entry_id},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input or {}
            ),
            errors=errors,
            description_placeholders={"lastfm_url": LASTFM_SIGNUP_URL},
        )

    def _music_assistant_entry_id(self, player: str) -> str | None:
        """Find the Music Assistant config entry that owns this player.

        Asking the user to pick the instance separately needed a
        ``config_entry`` selector, which the frontend cannot render inside a
        config flow: it takes the whole form down with it, leaving a dialog
        with nothing but a Submit button. The entity registry already knows
        the answer, and deriving it also makes a player/instance mismatch
        impossible.
        """
        registry = er.async_get(self.hass)
        entry = registry.async_get(player)
        if entry is None or entry.config_entry_id is None:
            return None
        owner = self.hass.config_entries.async_get_entry(entry.config_entry_id)
        if owner is None or owner.domain != MA_DOMAIN:
            return None
        return owner.entry_id

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> MaCuratedRadioOptionsFlow:
        """Return the options flow."""
        return MaCuratedRadioOptionsFlow()


class MaCuratedRadioOptionsFlow(OptionsFlow):
    """Tune batch sizes, filters and the cooldown without re-adding.

    Saving applies the change in place through the entry update listener
    rather than reloading, so the settings entities stay alive.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the tuning options."""
        if user_input is not None:
            return self.async_create_entry(data=_coerce_ints(user_input))

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_options_schema(current)
        )
