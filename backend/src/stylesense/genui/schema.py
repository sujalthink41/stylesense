"""The GenUI contract as JSON Schema: the source the mobile app's types are generated from."""

import json
from typing import Any

from pydantic import TypeAdapter

from stylesense.genui.actions import ActionRequest
from stylesense.genui.components import CATALOG_VERSION
from stylesense.genui.envelope import UiEnvelope, UiEvent


def contract() -> dict[str, Any]:
    return {
        "catalog_version": CATALOG_VERSION,
        "envelope": UiEnvelope.model_json_schema(),
        "event": TypeAdapter(UiEvent).json_schema(),
        "action_request": ActionRequest.model_json_schema(),
    }


def contract_json() -> str:
    # Sorted and indented: stable output, so the committed file diffs cleanly in reviews.
    return json.dumps(contract(), indent=2, sort_keys=True) + "\n"
