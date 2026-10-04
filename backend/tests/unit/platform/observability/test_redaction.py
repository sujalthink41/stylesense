import uuid

import pytest
from hypothesis import given
from hypothesis import strategies as st

from stylesense.platform.observability.redaction import REDACTED, redact_processor, scrub

emails = st.emails()
indian_mobiles = st.from_regex(r"(\+91[ -]?)?[6-9][0-9]{9}", fullmatch=True)


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "Authorization",
        "access_token",
        "refresh_token",
        "api_key",
        "client_secret",
        "cookie",
        "id_token",
    ],
)
def test_sensitive_keys_are_masked_regardless_of_value(key: str) -> None:
    assert scrub({key: "anything", "safe": "keep"}) == {key: REDACTED, "safe": "keep"}


@given(email=emails)
def test_emails_inside_strings_are_masked(email: str) -> None:
    out = scrub(f"user {email} signed in")

    assert email not in out
    assert "signed in" in out


@given(phone=indian_mobiles)
def test_indian_mobile_numbers_are_masked(phone: str) -> None:
    assert phone not in scrub(f"otp sent to {phone}")


def test_bearer_tokens_and_jwts_are_masked() -> None:
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"

    out = scrub(f"Authorization: Bearer abc.def-123 and raw {jwt}")

    assert "abc.def-123" not in out
    assert jwt not in out


def test_nested_structures_are_scrubbed_without_mutating_input() -> None:
    original = {"user": {"email": "a@b.co", "tokens": [{"refresh_token": "r1"}]}, "n": 3}

    out = scrub(original)

    assert out == {"user": {"email": REDACTED, "tokens": [{"refresh_token": REDACTED}]}, "n": 3}
    assert original["user"]["email"] == "a@b.co"  # type: ignore[index]


def test_non_string_scalars_pass_through() -> None:
    assert scrub({"count": 5, "ok": True, "ratio": 0.5, "none": None}) == {
        "count": 5,
        "ok": True,
        "ratio": 0.5,
        "none": None,
    }


def test_digit_runs_inside_ids_are_not_mistaken_for_phone_numbers() -> None:
    trace_id = "9e2ac6dac6886634856afcbdcbe6597d"  # caught in CI: corrupted by the phone pattern

    assert scrub(f"trace {trace_id}") == f"trace {trace_id}"


@given(value=st.uuids())
def test_ids_are_never_altered(value: uuid.UUID) -> None:
    for text in (value.hex, str(value)):
        assert scrub(text) == text


def test_correlation_fields_are_never_scrubbed() -> None:
    event = {"request_id": "x9876543210y", "trace_id": "6886634856", "span_id": "a@b.co"}

    assert scrub(event) == event


def test_versioned_names_are_not_mistaken_for_emails() -> None:
    assert scrub("deployed stylesense@1.2.3") == "deployed stylesense@1.2.3"


def test_ordinary_text_and_ids_are_untouched() -> None:
    text = "order 018f2a3b-7c4d-7e8f-9a0b-1c2d3e4f5a6b placed for 49900 paise"

    assert scrub(text) == text


def test_structlog_processor_scrubs_event_dict() -> None:
    event = {"event": "login for a@b.co", "password": "x", "level": "info"}

    out = redact_processor(None, "info", event)

    assert out == {"event": f"login for {REDACTED}", "password": REDACTED, "level": "info"}
