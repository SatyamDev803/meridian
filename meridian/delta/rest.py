"""Async Delta Exchange REST client (India testnet by default).

Every private call is signed (see auth.py), goes through the local rate budget, and turns
Delta's {"success": false, "error": {...}} envelope into a typed exception.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

import httpx

from meridian.core.quoter import Contract
from meridian.core.ratelimit import (
    WEIGHT_CANCEL,
    WEIGHT_FILLS,
    WEIGHT_ORDER,
    WEIGHT_READ,
    RateBudget,
)
from meridian.delta.auth import USER_AGENT, encode_body, encode_query, rest_headers

log = logging.getLogger("meridian.rest")


class DeltaError(Exception):
    """Delta rejected the request (business error, 4xx)."""

    def __init__(self, status: int, code: str, context: Any = None) -> None:
        super().__init__(f"{status} {code} {context or ''}".strip())
        self.status = status
        self.code = code
        self.context = context


class DeltaUnavailable(Exception):
    """Transport failure or 5xx. Counts against API health."""


class RateLimited(Exception):
    def __init__(self, reset_ms: int | None) -> None:
        super().__init__(f"rate limited, reset in {reset_ms} ms")
        self.reset_ms = reset_ms


class BudgetExhausted(Exception):
    """Our own budget refused the call before it reached Delta."""


class DeltaRest:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        budget: RateBudget,
        timeout_s: float = 5.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.budget = budget
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_s,
            headers={"User-Agent": USER_AGENT},
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        auth: bool = True,
        weight: int = WEIGHT_READ,
    ) -> Any:
        if not self.budget.try_spend(weight):
            raise BudgetExhausted(f"{method} {path}")
        query = encode_query(params)
        payload = encode_body(body)
        headers = (
            rest_headers(self.api_key, self.api_secret, method, path, query, payload)
            if auth
            else {"Accept": "application/json"}
        )
        try:
            resp = await self._client.request(
                method, path + query, content=payload or None, headers=headers
            )
        except httpx.HTTPError as exc:
            raise DeltaUnavailable(f"{method} {path}: {exc!r}") from exc

        if resp.status_code == 429:
            reset = resp.headers.get("X-RATE-LIMIT-RESET")
            reset_ms = int(reset) if reset and reset.isdigit() else None
            self.budget.on_429(reset_ms)
            raise RateLimited(reset_ms)
        if resp.status_code >= 500:
            raise DeltaUnavailable(f"{method} {path}: HTTP {resp.status_code}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise DeltaUnavailable(f"{method} {path}: non-JSON HTTP {resp.status_code}") from exc

        if resp.status_code >= 400 or not data.get("success", False):
            err = data.get("error") or {}
            code = err.get("code", "unknown") if isinstance(err, dict) else str(err)
            ctx = err.get("context") if isinstance(err, dict) else None
            raise DeltaError(resp.status_code, code, ctx)
        return data.get("result")

    # Market data -----------------------------------------------------------------------

    async def get_contract(self, symbol: str) -> Contract:
        p = await self.request("GET", f"/v2/products/{symbol}", auth=False)
        return Contract(
            product_id=int(p["id"]),
            symbol=p["symbol"],
            tick_size=Decimal(str(p["tick_size"])),
            contract_value=Decimal(str(p["contract_value"])),
            maker_fee=Decimal(str(p.get("maker_commission_rate") or "0.0002")),
            taker_fee=Decimal(str(p.get("taker_commission_rate") or "0.0005")),
        )

    async def get_ticker(self, symbol: str) -> dict:
        return await self.request("GET", f"/v2/tickers/{symbol}", auth=False)

    # Account ---------------------------------------------------------------------------

    async def set_leverage(self, product_id: int, leverage: int) -> dict:
        return await self.request(
            "POST",
            f"/v2/products/{product_id}/orders/leverage",
            body={"leverage": str(leverage)},
            weight=WEIGHT_ORDER,
        )

    async def get_position(self, product_id: int) -> dict:
        return await self.request("GET", "/v2/positions", params={"product_id": product_id})

    async def get_open_orders(self, product_id: int) -> list[dict]:
        return await self.request(
            "GET", "/v2/orders", params={"product_ids": product_id, "states": "open,pending"}
        )

    async def get_balances(self) -> list[dict]:
        return await self.request("GET", "/v2/wallet/balances")

    async def get_fills(self, product_id: int, page_size: int = 50) -> list[dict]:
        return await self.request(
            "GET",
            "/v2/fills",
            params={"product_ids": product_id, "page_size": page_size},
            weight=WEIGHT_FILLS,
        )

    async def get_wallet_balance(self, asset: str = "USD") -> Decimal | None:
        for b in await self.get_balances() or []:
            if b.get("asset_symbol") == asset:
                return Decimal(str(b.get("balance") or 0))
        return None

    # Orders ----------------------------------------------------------------------------

    async def place_limit(
        self,
        product_id: int,
        side: str,
        size: int,
        price: Decimal,
        client_order_id: str,
        *,
        post_only: bool = True,
    ) -> dict:
        return await self.request(
            "POST",
            "/v2/orders",
            body={
                "product_id": product_id,
                "side": side,
                "size": size,
                "order_type": "limit_order",
                "limit_price": format(price, "f"),
                "time_in_force": "gtc",
                "post_only": post_only,
                "client_order_id": client_order_id,
            },
            weight=WEIGHT_ORDER,
        )

    async def place_reduce_market(self, product_id: int, side: str, size: int, coid: str) -> dict:
        return await self.request(
            "POST",
            "/v2/orders",
            body={
                "product_id": product_id,
                "side": side,
                "size": size,
                "order_type": "market_order",
                "reduce_only": True,
                "client_order_id": coid,
            },
            weight=WEIGHT_ORDER,
        )

    async def edit_order(self, product_id: int, order_id: int, price: Decimal, size: int) -> dict:
        return await self.request(
            "PUT",
            "/v2/orders",
            body={
                "id": order_id,
                "product_id": product_id,
                "limit_price": format(price, "f"),
                "size": size,
            },
            weight=WEIGHT_ORDER,
        )

    async def cancel_order(self, product_id: int, order_id: int) -> dict:
        return await self.request(
            "DELETE",
            "/v2/orders",
            body={"id": order_id, "product_id": product_id},
            weight=WEIGHT_CANCEL,
        )

    async def cancel_all(self, product_id: int) -> Any:
        return await self.request(
            "DELETE",
            "/v2/orders/all",
            # Without these flags Delta answers success and cancels nothing (found in testing).
            body={
                "product_id": product_id,
                "cancel_limit_orders": True,
                "cancel_stop_orders": True,
                "cancel_reduce_only_orders": True,
            },
            weight=WEIGHT_CANCEL,
        )

    # Dead man's switch -----------------------------------------------------------------

    async def heartbeat_create(self, heartbeat_id: str, symbol: str, ttl_ms: int = 30_000) -> dict:
        return await self.request(
            "POST",
            "/v2/heartbeat/create",
            body={
                "heartbeat_id": heartbeat_id,
                "impact": "products",
                "contract_types": [],
                "product_symbols": [symbol],
                "default_ttl": ttl_ms,  # required by the API, though the docs example omits it
                "config": [{"action": "cancel_orders", "unhealthy_count": 1}],
            },
            weight=WEIGHT_READ,
        )

    async def heartbeat_ack(self, heartbeat_id: str, ttl_ms: int) -> dict:
        return await self.request(
            "POST",
            "/v2/heartbeat",
            body={"heartbeat_id": heartbeat_id, "ttl": ttl_ms},
            weight=WEIGHT_READ,
        )
