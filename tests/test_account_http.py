import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from apixly_media.server import AccountController, register_routes


def test_custom_node_entrypoint_registers_only_its_three_routes(monkeypatch):
    web = pytest.importorskip("aiohttp.web")
    owner = SimpleNamespace(routes=web.RouteTableDef())
    monkeypatch.setitem(
        sys.modules,
        "server",
        SimpleNamespace(PromptServer=SimpleNamespace(instance=owner)),
    )
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "apixly_test_loader",
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "apixly_test_loader", module)
    spec.loader.exec_module(module)
    paths = {(route.method, route.path) for route in owner.routes}
    assert paths == {
        ("GET", "/apixly/state"),
        ("POST", "/apixly/account"),
        ("GET", "/apixly/catalog"),
    }


def test_real_aiohttp_boundary_rejects_csrf_origin_and_oversized_actions_without_touching_credentials():
    web = pytest.importorskip("aiohttp.web")
    helpers = pytest.importorskip("aiohttp.test_utils")

    class Manager:
        calls = []

        def public(self):
            return {"mode": "manual", "connected": False}

        def start(self):
            self.calls.append("begin")

        def poll(self):
            self.calls.append("poll")

        def cancel(self):
            pass

        def refresh(self):
            pass

        def disconnect(self):
            pass

        def use_manual(self):
            pass

        def use_account(self):
            pass

    async def run():
        owner = SimpleNamespace(routes=web.RouteTableDef())
        manager = Manager()
        assert register_routes(owner, AccountController(manager))
        assert register_routes(owner, AccountController(manager))
        app = web.Application()
        app.add_routes(owner.routes)
        async with helpers.TestClient(helpers.TestServer(app)) as client:
            response = await client.get("/apixly/state")
            assert response.status == 200
            assert response.headers["Cache-Control"] == "no-store"
            nonce = (await response.json())["csrf_token"]
            foreign = await client.get(
                "/apixly/state", headers={"Origin": "https://evil.test"}
            )
            assert foreign.status == 403
            missing = await client.post("/apixly/account", json={"action": "begin"})
            assert missing.status == 403 and not manager.calls
            approved = await client.post(
                "/apixly/account",
                json={"action": "begin"},
                headers={"X-Apixly-CSRF": nonce},
            )
            assert approved.status == 200 and manager.calls == ["begin"]
            large = await client.post(
                "/apixly/account", data="x" * 4097, headers={"X-Apixly-CSRF": nonce}
            )
            assert large.status == 413 and manager.calls == ["begin"]

    asyncio.run(run())
