"""Configuration.

`Settings` is read once from the environment (and `.env`). `StrategyParams` is the
subset that can be changed while the bot runs, from the dashboard or the control API.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StrategyParams(BaseModel):
    """Knobs the strategy reads on every tick. All prices are in bps of fair value."""

    spread_bps: Decimal = Field(default=Decimal("8"), gt=0, le=500)
    skew_bps: Decimal = Field(default=Decimal("10"), ge=0, le=500)
    order_size: int = Field(default=10, ge=1, le=10_000, description="contracts per side")
    max_position: int = Field(default=50, ge=1, le=100_000, description="contracts, absolute")
    requote_bps: Decimal = Field(
        default=Decimal("1.5"), ge=0, le=100, description="move needed before we edit an order"
    )
    guard_bps: Decimal = Field(
        default=Decimal("25"), gt=0, le=1000, description="pull quotes beyond this disagreement"
    )
    warn_bps: Decimal = Field(
        default=Decimal("10"), ge=0, le=1000, description="widen spread beyond this disagreement"
    )
    max_session_loss: Decimal = Field(
        default=Decimal("50"), gt=0, description="USD; breach flattens and halts"
    )
    use_ref_drift: bool = Field(
        default=True, description="nudge Delta mark by Binance's move since the last mark tick"
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Delta Exchange India testnet. Demo-account keys only work against these hosts.
    delta_api_key: str = ""
    delta_api_secret: str = ""
    delta_rest_url: str = "https://cdn-ind.testnet.deltaex.org"
    delta_ws_private_url: str = "wss://socket-ind.testnet.deltaex.org"
    delta_ws_public_url: str = "wss://socket-ind-pub.testnet.deltaex.org"
    symbol: str = "BTCUSD"
    leverage: int = 5

    # Binance public market-data-only host: no keys, fewer geo blocks than stream.binance.com.
    binance_ws_url: str = "wss://data-stream.binance.vision/ws"
    binance_symbol: str = "btcusdt"

    database_url: str = "sqlite:///./meridian.db"
    control_api_key: str = ""
    chaos_enabled: bool = True
    auto_start: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]
    web_dir: str = "web/out"

    # Timings, seconds.
    tick_interval_s: float = 0.25
    mark_stale_s: float = 6.0
    ref_stale_s: float = 3.0
    ws_silence_s: float = 35.0
    reconcile_interval_s: float = 10.0
    deadman_interval_s: float = 10.0
    deadman_ttl_ms: int = 30_000
    snapshot_interval_s: float = 0.5
    max_consecutive_api_errors: int = 5
    api_cooldown_s: float = 30.0

    # Defaults for the runtime-editable strategy knobs.
    spread_bps: Decimal = Decimal("8")
    skew_bps: Decimal = Decimal("10")
    order_size: int = 10
    max_position: int = 50
    max_session_loss: Decimal = Decimal("50")

    @property
    def has_keys(self) -> bool:
        return bool(self.delta_api_key and self.delta_api_secret)

    def initial_params(self) -> StrategyParams:
        return StrategyParams(
            spread_bps=self.spread_bps,
            skew_bps=self.skew_bps,
            order_size=self.order_size,
            max_position=self.max_position,
            max_session_loss=self.max_session_loss,
        )
