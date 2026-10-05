import re

import pytest
from pydantic import ValidationError

from stylesense.api.preconditions import (
    IfMatch,
    InvalidPreconditionError,
    PreconditionRequiredError,
)
from stylesense.modules.polls.schemas import PollCreate
from stylesense.modules.sharing.schemas import ShareCreate
from stylesense.platform.slugs import SLUG_LENGTH, Pseudonymizer, new_slug

IDS = [
    "01a10000-0000-7000-8000-000000000001",
    "01a10000-0000-7000-8000-000000000002",
    "01a10000-0000-7000-8000-000000000003",
]


def test_slugs_are_short_url_safe_and_unique() -> None:
    slugs = {new_slug() for _ in range(2_000)}

    assert len(slugs) == 2_000
    assert all(re.fullmatch(rf"[A-Za-z0-9]{{{SLUG_LENGTH}}}", s) for s in slugs)


def test_pseudonyms_are_stable_keyed_and_purpose_bound() -> None:
    voters = Pseudonymizer.derive("x" * 32, "poll-voters")

    assert voters("1.2.3.4") == voters("1.2.3.4")
    assert voters("1.2.3.4") != Pseudonymizer.derive("y" * 32, "poll-voters")("1.2.3.4")
    assert voters("1.2.3.4") != Pseudonymizer.derive("x" * 32, "other")("1.2.3.4")
    assert "1.2.3.4" not in voters("1.2.3.4")


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "product", "product_ids": IDS[:2]},
        {"kind": "product", "product_ids": []},
        {"kind": "look", "product_ids": IDS[:1]},
        {"kind": "look", "product_ids": [IDS[0], IDS[0]]},
        {"kind": "board"},
        {"kind": "board", "board_id": IDS[0], "product_ids": IDS[:1]},
        {"kind": "look", "product_ids": IDS[:2], "board_id": IDS[2]},
        {"kind": "outfit", "product_ids": IDS[:2]},
    ],
)
def test_share_shapes_are_validated(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ShareCreate.model_validate(body)


@pytest.mark.parametrize(
    "body",
    [
        {"product_ids": IDS[:1]},
        {
            "product_ids": [
                *IDS,
                "01a10000-0000-7000-8000-000000000004",
                "01a10000-0000-7000-8000-000000000005",
            ]
        },
        {"product_ids": [IDS[0], IDS[0]]},
        {"product_ids": IDS[:2], "closes_in_hours": 0},
        {"product_ids": IDS[:2], "closes_in_hours": 24 * 8},
        {"product_ids": IDS[:2], "question": ""},
    ],
)
def test_poll_shapes_are_validated(body: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PollCreate.model_validate(body)


@pytest.mark.parametrize(("raw", "version"), [('"3"', 3), ('W/"12"', 12), ("7", 7), (' "1" ', 1)])
def test_if_match_reads_the_version(raw: str, version: int) -> None:
    assert IfMatch(raw) == version


def test_if_match_is_required_and_must_be_a_version() -> None:
    with pytest.raises(PreconditionRequiredError):
        IfMatch(None)
    for bad in ('"abc"', "*", '"-1"', ""):
        with pytest.raises(InvalidPreconditionError):
            IfMatch(bad)
