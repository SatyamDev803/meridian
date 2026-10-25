"""Delta Exchange request signing.

REST: signature = HMAC_SHA256(secret, method + timestamp + path + query + body), hex.
WebSocket: the same HMAC over "GET" + timestamp + "/live".
The timestamp is unix seconds and the exchange rejects anything older than 5 seconds.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import urlencode

USER_AGENT = "meridian-mm/0.1 (python-httpx)"


def sign(secret: str, message: str) -> str:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def encode_body(body: dict[str, Any] | None) -> str:
    """Compact JSON, so the bytes we sign are exactly the bytes we send."""
    if body is None:
        return ""
    return json.dumps(body, separators=(",", ":"))


def encode_query(params: dict[str, Any] | None) -> str:
    """Return '?a=1&b=2' or ''. Delta signs the query with its leading '?'."""
    if not params:
        return ""
    clean = {k: v for k, v in params.items() if v is not None}
    return "?" + urlencode(clean) if clean else ""


def rest_headers(
    api_key: str,
    secret: str,
    method: str,
    path: str,
    query: str = "",
    body: str = "",
    now: float | None = None,
) -> dict[str, str]:
    timestamp = str(int(now if now is not None else time.time()))
    signature = sign(secret, method.upper() + timestamp + path + query + body)
    return {
        "api-key": api_key,
        "timestamp": timestamp,
        "signature": signature,
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def ws_auth_message(api_key: str, secret: str, now: float | None = None) -> dict[str, Any]:
    timestamp = str(int(now if now is not None else time.time()))
    return {
        "type": "key-auth",
        "payload": {
            "api-key": api_key,
            "signature": sign(secret, "GET" + timestamp + "/live"),
            "timestamp": timestamp,
        },
    }
