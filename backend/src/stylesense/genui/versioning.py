"""Catalog version negotiation: never send an app a component it can't render."""

from collections.abc import Mapping

from stylesense.genui.components import (
    CATALOG_VERSION,
    INTRODUCED_IN,
    InfoBanner,
    InfoBannerProps,
)
from stylesense.genui.envelope import UiEnvelope
from stylesense.platform.errors import AppError

HEADER = "X-GenUI-Version"
MIN_SUPPORTED_VERSION = 1
_UPDATE_PROMPT = "Update StyleSense to see this."


class InvalidGenUIVersionError(AppError):
    status_code = 400
    code = "invalid_genui_version"
    title = f"{HEADER} must be a positive integer"


class UnsupportedGenUIVersionError(AppError):
    status_code = 426
    code = "app_update_required"
    title = "This version of the app is no longer supported; please update"


def negotiate(raw: str | None) -> int:
    """The catalog version to render for this client."""
    if raw is None:
        return MIN_SUPPORTED_VERSION  # unknown client: assume the oldest supported catalog
    try:
        version = int(raw.strip())
    except ValueError:
        raise InvalidGenUIVersionError from None
    if version < 1:
        raise InvalidGenUIVersionError
    if version < MIN_SUPPORTED_VERSION:
        raise UnsupportedGenUIVersionError
    return min(version, CATALOG_VERSION)  # a newer app talking to an older server is fine


def adapt(
    envelope: UiEnvelope, client_version: int, introduced: Mapping[str, int] = INTRODUCED_IN
) -> UiEnvelope:
    """Replace components the client doesn't know with an update prompt (same id and slot)."""
    if all(introduced[c.type] <= client_version for c in envelope.components):
        return envelope
    components = [
        c
        if introduced[c.type] <= client_version
        else InfoBanner(id=c.id, props=InfoBannerProps(tone="info", text=_UPDATE_PROMPT))
        for c in envelope.components
    ]
    return envelope.model_copy(update={"components": components})
