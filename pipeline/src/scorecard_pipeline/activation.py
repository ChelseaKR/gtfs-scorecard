"""Validate bounded agency selections for manual production activation.

The workflow input is deliberately parsed in Python instead of interpolated
into shell: operator-supplied text is data, every selected id must already be
in the curated registry, and one dispatch can never fan out beyond the
documented safety bound.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection

from .agencies import ID_PATTERN

MAX_ACTIVATION_TARGETS = 25
_SEPARATOR = re.compile(r"[,\s]+")


class ActivationTargetError(ValueError):
    """A manual activation selection is unsafe or does not match the registry."""


def parse_activation_targets(
    raw: str,
    known_ids: Collection[str],
    *,
    limit: int = MAX_ACTIVATION_TARGETS,
) -> list[str]:
    """Return validated registry ids from comma or whitespace separated input.

    Inputs are never silently canonicalized. NFKC/casefold normalization is
    used only to detect visually surprising duplicates such as ``agency`` and
    ``AGENCY``; each accepted token must still be the exact lowercase registry
    id supplied by the operator.
    """
    tokens = [token for token in _SEPARATOR.split(raw.strip()) if token]
    if not tokens:
        raise ActivationTargetError("provide at least one agency id")
    if len(tokens) > limit:
        raise ActivationTargetError(
            f"at most {limit} agency ids may be activated in one run (received {len(tokens)})"
        )

    normalized: dict[str, str] = {}
    for token in tokens:
        key = unicodedata.normalize("NFKC", token).casefold()
        if previous := normalized.get(key):
            raise ActivationTargetError(
                f"duplicate agency id after normalization: {previous!r} and {token!r}"
            )
        normalized[key] = token

    malformed = [token for token in tokens if ID_PATTERN.fullmatch(token) is None]
    if malformed:
        raise ActivationTargetError(
            "malformed agency id(s): "
            + ", ".join(repr(token) for token in malformed)
            + "; use exact lowercase registry slugs"
        )

    unknown = [token for token in tokens if token not in known_ids]
    if unknown:
        raise ActivationTargetError("unknown agency id(s): " + ", ".join(unknown))
    return tokens
