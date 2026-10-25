import hashlib
import hmac

from meridian.delta.auth import encode_body, encode_query, rest_headers, sign, ws_auth_message


def test_sign_matches_hmac_sha256_hex():
    expected = hmac.new(b"secret", b"GET1700000000/v2/orders", hashlib.sha256).hexdigest()
    assert sign("secret", "GET1700000000/v2/orders") == expected


def test_rest_headers_sign_method_ts_path_query_body():
    body = encode_body({"product_id": 27, "size": 1})
    query = encode_query({"product_ids": 27, "states": "open"})
    h = rest_headers("key", "secret", "post", "/v2/orders", query, body, now=1700000000.9)
    assert h["timestamp"] == "1700000000"
    assert h["api-key"] == "key"
    assert h["signature"] == sign("secret", "POST1700000000/v2/orders" + query + body)
    assert "User-Agent" in h


def test_body_is_compact_and_query_has_leading_question_mark():
    assert encode_body({"a": 1, "b": "x"}) == '{"a":1,"b":"x"}'
    assert encode_body(None) == ""
    assert encode_query({"a": 1, "b": None}) == "?a=1"
    assert encode_query(None) == ""


def test_ws_auth_uses_key_auth_and_live_path():
    msg = ws_auth_message("key", "secret", now=1700000000)
    assert msg["type"] == "key-auth"
    assert msg["payload"]["signature"] == sign("secret", "GET1700000000/live")
    assert msg["payload"]["timestamp"] == "1700000000"
