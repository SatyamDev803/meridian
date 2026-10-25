import json
from decimal import Decimal

import httpx
import pytest

from meridian.core.ratelimit import RateBudget
from meridian.delta.auth import sign
from meridian.delta.rest import DeltaError, DeltaRest, DeltaUnavailable, RateLimited


def client(handler):
    return DeltaRest(
        "https://x.test", "key", "secret", RateBudget(), transport=httpx.MockTransport(handler)
    )


async def test_signed_order_request_matches_what_is_sent():
    seen = {}

    def handler(req: httpx.Request):
        seen["req"] = req
        return httpx.Response(200, json={"success": True, "result": {"id": 1, "state": "open"}})

    rest = client(handler)
    await rest.place_limit(27, "buy", 10, Decimal("70000.5"), "mrd-1")
    req = seen["req"]
    body = req.content.decode()
    assert json.loads(body)["limit_price"] == "70000.5"
    ts = req.headers["timestamp"]
    assert req.headers["signature"] == sign("secret", "POST" + ts + "/v2/orders" + body)
    await rest.aclose()


async def test_query_string_is_signed():
    seen = {}

    def handler(req):
        seen["req"] = req
        return httpx.Response(200, json={"success": True, "result": []})

    rest = client(handler)
    await rest.get_open_orders(27)
    req = seen["req"]
    q = "?" + req.url.query.decode()
    assert req.headers["signature"] == sign(
        "secret", "GET" + req.headers["timestamp"] + "/v2/orders" + q
    )
    await rest.aclose()


async def test_error_envelope_becomes_delta_error():
    rest = client(
        lambda r: httpx.Response(
            400, json={"success": False, "error": {"code": "insufficient_margin"}}
        )
    )
    with pytest.raises(DeltaError) as e:
        await rest.place_limit(27, "buy", 10, Decimal("1"), "c")
    assert e.value.code == "insufficient_margin"
    await rest.aclose()


async def test_429_blocks_budget():
    rest = client(lambda r: httpx.Response(429, headers={"X-RATE-LIMIT-RESET": "5000"}))
    with pytest.raises(RateLimited):
        await rest.get_position(27)
    assert not rest.budget.ok
    await rest.aclose()


async def test_5xx_is_unavailable():
    rest = client(lambda r: httpx.Response(503, text="down"))
    with pytest.raises(DeltaUnavailable):
        await rest.get_position(27)
    await rest.aclose()


async def test_contract_parsing():
    product = {
        "id": 27,
        "symbol": "BTCUSD",
        "tick_size": "0.5",
        "contract_value": "0.001",
        "maker_commission_rate": "0.0002",
        "taker_commission_rate": "0.0005",
    }
    rest = client(lambda r: httpx.Response(200, json={"success": True, "result": product}))
    c = await rest.get_contract("BTCUSD")
    assert c.product_id == 27 and c.tick_size == Decimal("0.5")
    await rest.aclose()


async def test_cancel_all_opts_in_to_every_order_type():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"success": True, "result": {}})

    rest = client(handler)
    await rest.cancel_all(84)
    assert seen["body"]["cancel_limit_orders"] is True
    assert seen["body"]["product_id"] == 84
    await rest.aclose()
