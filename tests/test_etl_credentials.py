"""Tests for EIA credential handling (docs/archive/plans/PLAN_EIA_EXTRACTOR.md Phase A1).

The key must never be interpolated into an error message or returned by
``require_eia_api_key``; ``redact_secrets`` is defence in depth only.
"""

from __future__ import annotations

import pytest

from owr.etl.credentials import MissingCredentialError, redact_secrets, require_eia_api_key

SENTINEL = "SENTINELKEY0123456789abcdefghijklmnopqrst"  # 40 chars


def test_missing_key_raises_with_actionable_message():
    with pytest.raises(MissingCredentialError) as exc_info:
        require_eia_api_key(getenv=lambda _name: None)
    message = str(exc_info.value)
    assert "EIA_API_KEY" in message
    assert "https://www.eia.gov/opendata/register.php" in message


def test_blank_key_raises_same_error():
    for blank in ("", "   "):
        with pytest.raises(MissingCredentialError):
            require_eia_api_key(getenv=lambda _name, v=blank: v)


def test_present_key_returns_none_and_raises_nothing():
    assert require_eia_api_key(getenv=lambda _name: "a-real-looking-key") is None


def test_missing_key_message_does_not_leak_other_env_vars():
    # A wildcard env dump would put every set variable's value into the message.
    # Guard against it: a sentinel set under a DIFFERENT name must not appear.
    getenv = lambda name: "OTHER_SENTINEL_VALUE" if name == "SOME_OTHER_VAR" else None  # noqa: E731
    with pytest.raises(MissingCredentialError) as exc_info:
        require_eia_api_key(getenv=getenv)
    assert "OTHER_SENTINEL_VALUE" not in str(exc_info.value)


def test_redact_secrets_replaces_sentinel_including_multiple_occurrences():
    text = f"boom {SENTINEL} happened near {SENTINEL} again"
    redacted = redact_secrets(text, getenv=lambda _name: SENTINEL)
    assert SENTINEL not in redacted
    assert redacted.count("***REDACTED***") == 2


def test_redact_secrets_is_noop_when_var_unset():
    text = "nothing to redact here"
    assert redact_secrets(text, getenv=lambda _name: None) == text


def test_redact_secrets_is_noop_for_short_key_over_redaction_guard():
    text = "a cat sat on a mat"
    assert redact_secrets(text, getenv=lambda _name: "a") == text


def test_redact_secrets_leaves_text_without_key_byte_identical():
    text = "an unrelated message with no secrets in it"
    assert redact_secrets(text, getenv=lambda _name: SENTINEL) == text
