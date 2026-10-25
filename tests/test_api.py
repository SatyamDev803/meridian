from fastapi.testclient import TestClient

from meridian.config import Settings
from meridian.main import create_app


def make(**kw):
    s = Settings(_env_file=None, database_url="sqlite:///:memory:", web_dir="nope", **kw)
    return TestClient(create_app(s, start_engine=False))


def test_health_and_state_without_keys():
    with make() as c:
        assert c.get("/health").json() == {"status": "ok"}
        st = c.get("/api/state").json()
        assert st["hasKeys"] is False
        assert st["canTrade"] is False
        assert "API keys" in st["cannotTradeReason"]


def test_start_without_keys_is_409():
    with make() as c:
        r = c.post("/api/control/start")
        assert r.status_code == 409


def test_control_key_enforced():
    with make(control_api_key="sekret") as c:
        assert c.post("/api/control/stop").status_code == 401
        assert c.post("/api/control/stop", headers={"x-control-key": "sekret"}).status_code == 200


def test_params_patch_validates():
    with make() as c:
        r = c.patch("/api/control/params", json={"spread_bps": "20", "order_size": 5})
        assert r.status_code == 200
        assert r.json()["order_size"] == 5
        assert c.patch("/api/control/params", json={"spread_bps": -1}).status_code == 422


def test_chaos_respects_flag():
    with make(chaos_enabled=False) as c:
        assert c.post("/api/chaos/stale_ref").status_code == 403
    with make() as c:
        assert c.post("/api/chaos/stale_ref").json()["ok"] is True
        assert c.post("/api/chaos/nope").status_code == 422
