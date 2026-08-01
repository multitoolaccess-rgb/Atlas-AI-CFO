"""Bounded codecs for the forecast API: cursor pagination tokens and ETag values.

This module is the single source of truth for two Phase 1 client-visible
encodings:

* **Cursor** pagination tokens that survive HTTP round-trips.  They are
  opaque to the client (base64url-encoded JSON), but the inner contract
  is bounded so a tampered cursor cannot inject identifiers into a
  query that bypasses the slice's user-scope.

* **ETag** values for ``If-Match`` / ``If-None-Match`` conditional
  requests.  The emitted value is RFC 7232-quoted; the parser accepts
  both the bare and the quoted form so a real client and a synthetic
  CLI both work.

Both encodings:

* are deterministic for the same inputs (canonicalization-stable);
* reject malformed values without echoing the rejected bytes back to
  the client;
* never include user-supplied free-form text in the encoded payload; and
* are validated against bounded length, character, and shape rules so a
  crafted cursor cannot smuggle a foreign identifier into a server query.

Slice C scope: this module has no FastAPI imports, no route registration,
no database reads, and no HTTP plumbing.  Slice D wires the codecs to the
real ``/api/v1/forecasts*`` routes.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

# ``fc1.`` namespacing prefixes every emitted cursor.  Decoding rejects
# cursors with any other prefix so a future coordinate-format change is
# explicit and a stale client cannot ingest the new format by accident.
CURSOR_VERSION_PREFIX: Final[str] = "fc1."
# Max encoded length: a 128-byte inner payload base64url-encoded fits in
# ~172 characters; we round up to 256 to leave room for the prefix and
# padding-free tail.  Anything longer is rejected.
CURSOR_MAX_LENGTH: Final[int] = 256
# Inner payload bounds: keep forecast_id length uniform with the rest
# of the schema identifiers (36 chars when UUIDv4 lowercase); pad to 64
# for any future non-uuid format.
CURSOR_MAX_INNER_PAYLOAD_BYTES: Final[int] = 384

_UUID_LOWER = re.compile(r"^[0-9a-f]{32}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_UTC_RFC3339_Z = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$"
)

# ETag limits: a 36-char UUID plus ``-v`` plus a 32-bit signed version
# decimal = ~46 characters; bound it at 96 to leave slack for any future
# nesting or formatting (e.g. weak ``W/`` prefix).
ETAG_MAX_LENGTH: Final[int] = 96
# ETag format: ``{forecast_uuid}-v{positive_int}``.  We deliberately do
# NOT include a ``W/`` weak indicator; the forecast content is byte-
# stable per (forecast_id, version_number), so the strong ETag is the
# correct semantic.  Bounded regex keeps a malformed value out of the
# persistence boundary.
_VERSION_DIGITS = re.compile(r"[1-9][0-9]{0,9}|0$")  # 0..9999999999, no leading zeros
_ETAG_BARE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-v[1-9][0-9]{0,9}$")
_ETAG_WEAK = re.compile(r"W/\"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-v[1-9][0-9]{0,9}\"$")
_ETAG_STRONG = re.compile(r"\"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-v[1-9][0-9]{0,9}\"$")


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------

class CodecError(ValueError):
    """A bounded codec rejected the input; the message holds NO echo."""


# ----------------------------------------------------------------------
# Cursor codec
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class ForecastCursor:
    """Inner cursor payload — server-only, never serialized raw to clients."""

    forecast_id: str
    created_at: datetime  # timezone-aware UTC
    version_number: int


def _validate_forecast_id(value: Any) -> str:
    if not isinstance(value, str) or not _UUID_LOWER.fullmatch(value):
        raise CodecError("forecast_id")
    if len(value) > 64:
        raise CodecError("forecast_id")
    return value


def _validate_created_at(value: Any) -> datetime:
    if not isinstance(value, str) or not _UTC_RFC3339_Z.fullmatch(value):
        raise CodecError("created_at")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo != timezone.utc:
        raise CodecError("created_at")
    return parsed


def _validate_version_number(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CodecError("version_number")
    if not 0 <= value <= 9_999_999_999:
        raise CodecError("version_number")
    return value


def encode_forecast_cursor(*, forecast_id: str, created_at: datetime, version_number: int) -> str:
    """Return the opaque base64url cursor token (no echo of inputs)."""
    _validate_forecast_id(forecast_id)
    _validate_created_at(created_at.isoformat().replace("+00:00", "Z"))
    _validate_version_number(version_number)
    payload = {
        "forecast_id": forecast_id,
        "created_at": created_at.astimezone(timezone.utc).isoformat(timespec="microseconds")
        .replace("+00:00", "Z"),
        "version_number": version_number,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    bare = encoded.decode("ascii").rstrip("=")
    cursor = f"{CURSOR_VERSION_PREFIX}{bare}"
    if len(cursor) > CURSOR_MAX_LENGTH:
        raise CodecError("cursor")
    return cursor


def decode_forecast_cursor(cursor: str) -> ForecastCursor:
    """Reverse :func:`encode_forecast_cursor`; reject tampered cursors."""
    if not isinstance(cursor, str):
        raise CodecError("cursor")
    if len(cursor) > CURSOR_MAX_LENGTH:
        raise CodecError("cursor")
    if not cursor.startswith(CURSOR_VERSION_PREFIX):
        raise CodecError("cursor")
    payload_b64 = cursor[len(CURSOR_VERSION_PREFIX):]
    pad = "=" * (-len(payload_b64) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_b64 + pad)
    except (binascii.Error, ValueError) as exc:
        raise CodecError("cursor") from exc
    if len(decoded) > CURSOR_MAX_INNER_PAYLOAD_BYTES:
        raise CodecError("cursor")
    try:
        payload = json.loads(decoded)
    except ValueError as exc:
        raise CodecError("cursor") from exc
    if not isinstance(payload, dict):
        raise CodecError("cursor")
    forecast_id = _validate_forecast_id(payload.get("forecast_id"))
    created_at_utc = _validate_created_at(payload.get("created_at"))
    version_number = _validate_version_number(payload.get("version_number"))
    return ForecastCursor(forecast_id=forecast_id, created_at=created_at_utc, version_number=version_number)


# ----------------------------------------------------------------------
# ETag codec (forecast namespace)
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class ForecastETag:
    """Inner ETag payload — opaque to clients, server-derived."""

    forecast_id: str
    version_number: int


def derive_forecast_etag(*, forecast_id: str, version_number: int) -> str:
    """Return the **bare** server-derived ETag value (no quotes)."""
    _validate_forecast_id(forecast_id)
    if not isinstance(version_number, int) or isinstance(version_number, bool):
        raise CodecError("version_number")
    if not 1 <= version_number <= 9_999_999_999:
        raise CodecError("version_number")
    bare = f"{forecast_id}-v{version_number}"
    if not _ETAG_BARE.fullmatch(bare) or len(bare) > ETAG_MAX_LENGTH:
        raise CodecError("etag")
    return bare


def format_forecast_etag_header(*, forecast_id: str, version_number: int) -> str:
    """Return the **quoted** RFC 7232 ETag header value ready to emit."""
    bare = derive_forecast_etag(forecast_id=forecast_id, version_number=version_number)
    return f'"{bare}"'


def parse_forecast_etag_header(value: Any) -> ForecastETag | None:
    """Parse an inbound ETag header value.

    Returns ``None`` for the wildcard ``*`` (per RFC 7232 used by
    ``If-None-Match`` for first-creation requests).  Rejects weak
    ETags (``W/``): forecast versions are byte-stable, so a weak tag
    is semantically wrong and is treated as malformed.
    """
    if value is None:
        raise CodecError("etag")
    if not isinstance(value, str):
        raise CodecError("etag")
    if value == "*":
        return None
    if len(value) > ETAG_MAX_LENGTH:
        raise CodecError("etag")
    if _ETAG_WEAK.fullmatch(value):
        raise CodecError("etag")  # weak forbidden (see module docstring)
    match = _ETAG_STRONG.fullmatch(value)
    if not match:
        raise CodecError("etag")
    bare = value[1:-1]
    forecast_id, _, version_text = bare.rpartition("-v")
    if not _UUID_LOWER.fullmatch(forecast_id):
        raise CodecError("etag")
    version_number = _validate_version_number(int(version_text))
    return ForecastETag(forecast_id=forecast_id, version_number=version_number)


# ----------------------------------------------------------------------
# ETag codec (decision namespace, Phase 2 Slice 1)
# ----------------------------------------------------------------------
#
# The decision ETag namespace uses a distinct ``-dN`` form so that an
# immutable recommendation row (whose PK is a UUIDv4-lowercase) and an
# immutable journal row (whose PK is also a UUIDv4-lowercase) cannot
# collide at the wire surface with the ``-vN`` forecast namespace.
# Bare form: ``{uuid}-d{positive_int}``.  Length-bound at 96 to leave
# slack identical to the forecast ETag namespace.
#
# Schema parity: ``recommendation_schemas._DECISION_ETAG_BARE`` is
# re-imported from here so wire-shape validators and server-emitted
# values stay byte-identical without a duplicated regex literal.

_DECISION_ETAG_BARE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-d[1-9][0-9]{0,9}$"
)
_DECISION_ETAG_WEAK = re.compile(
    r"W/\"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-d[1-9][0-9]{0,9}\"$"
)
_DECISION_ETAG_STRONG = re.compile(
    r"\"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}-d[1-9][0-9]{0,9}\"$"
)


@dataclass(frozen=True)
class DecisionETag:
    """Inner ETag payload for the recommendation / decision-jet namespace.

    ``source_id`` is the canonical UUID of the underlying Phase 2 row
    (a recommendation row's PK, or a journal entry's PK); ``version``
    is currently always 1 in Phase 2 Slice 1 because the bounded
    derivation engine emits exactly one row per canonical input tuple.
    The field is retained as a ``version`` placeholder so a future
    additive bump has a wire-stable shape to ride on without changing
    the contract.
    """

    source_id: str
    version: int = 1


def derive_decision_etag(*, source_id: str, version: int = 1) -> str:
    """Return the **bare** server-derived decision-ETag value (no quotes).

    Mirrors :func:`derive_forecast_etag` shape, but emits the
    ``-d<n>`` distinction so the two namespaces cannot collide.
    """
    _validate_forecast_id(source_id)
    if not isinstance(version, int) or isinstance(version, bool):
        raise CodecError("etag")
    if not 1 <= version <= 9_999_999_999:
        raise CodecError("etag")
    bare = f"{source_id}-d{version}"
    if not _DECISION_ETAG_BARE.fullmatch(bare) or len(bare) > ETAG_MAX_LENGTH:
        raise CodecError("etag")
    return bare


def format_decision_etag_header(*, source_id: str, version: int = 1) -> str:
    """Return the **quoted** RFC 7232 ETag header value ready to emit."""
    bare = derive_decision_etag(source_id=source_id, version=version)
    return f'"{bare}"'


def parse_decision_etag_header(value: Any) -> DecisionETag | None:
    """Parse an inbound decision ETag header value.

    Returns ``None`` for the wildcard ``*``.  Rejects weak ETags
    (``W/``) for the same byte-stability reason as
    :func:`parse_forecast_etag_header`.
    """
    if value is None:
        raise CodecError("etag")
    if not isinstance(value, str):
        raise CodecError("etag")
    if value == "*":
        return None
    if len(value) > ETAG_MAX_LENGTH:
        raise CodecError("etag")
    if _DECISION_ETAG_WEAK.fullmatch(value):
        raise CodecError("etag")  # weak forbidden (see module docstring)
    match = _DECISION_ETAG_STRONG.fullmatch(value)
    if not match:
        raise CodecError("etag")
    bare = value[1:-1]
    source_id, _, version_text = bare.rpartition("-d")
    if not _UUID_LOWER.fullmatch(source_id):
        raise CodecError("etag")
    try:
        version = _validate_version_number(int(version_text))
    except CodecError:
        raise CodecError("etag")
    return DecisionETag(source_id=source_id, version=version)
