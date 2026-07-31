"""Credential handling for provider API keys — the EIA key never bound to a name.

The EIA-930 wind extractor (Phase A2) needs ``$EIA_API_KEY``. Two rules keep the
key out of logs, stdout, provenance strings, and the database:

1. **The value is never returned, stored, or interpolated.** ``require_eia_api_key``
   checks presence and raises; it does not hand the caller the key. ``gridstatus.EIA()``
   reads the environment variable itself (see ``extract._default_eia_client``), so this
   process never binds the key to a Python name at all.
2. **``redact_secrets`` is defence in depth, not the primary mechanism.** The primary
   mechanism is that our own code never puts the key into a string in the first place.
   Redaction exists so a *provider* leak (e.g. an exception message from gridstatus)
   cannot reach stdout.
"""

from __future__ import annotations

import os
from collections.abc import Callable

EIA_API_KEY_ENV = "EIA_API_KEY"

# Never redact a trivially short value: a developer with EIA_API_KEY=a set would
# otherwise see every letter 'a' in every message replaced. Real EIA keys are 40
# characters, so this guard only ever suppresses a pathological local setting.
_MIN_REDACTABLE_LEN = 8


class MissingCredentialError(RuntimeError):
    """Raised when a required credential is absent, blank, or whitespace-only."""


def require_eia_api_key(getenv: Callable[[str], str | None] = os.environ.get) -> None:
    """Raise ``MissingCredentialError`` if ``$EIA_API_KEY`` is absent or blank.

    Returns nothing — the value itself is never returned, stored, or interpolated
    into the error message. Only the variable *name* and the registration URL are.
    """
    value = getenv(EIA_API_KEY_ENV)
    if value is None or not value.strip():
        raise MissingCredentialError(
            f"no EIA API key. Set ${EIA_API_KEY_ENV} (free registration: "
            f"https://www.eia.gov/opendata/register.php). The wind dataset needs "
            f"it even for --dry-run, because --dry-run still performs the provider pull."
        )


def redact_secrets(text: str, getenv: Callable[[str], str | None] = os.environ.get) -> str:
    """Replace every occurrence of the ``$EIA_API_KEY`` value with ``***REDACTED***``.

    No-op when the variable is unset, blank, or shorter than ``_MIN_REDACTABLE_LEN``
    (the over-redaction guard described in the module docstring).
    """
    value = getenv(EIA_API_KEY_ENV)
    if not value or len(value) < _MIN_REDACTABLE_LEN:
        return text
    return text.replace(value, "***REDACTED***")
