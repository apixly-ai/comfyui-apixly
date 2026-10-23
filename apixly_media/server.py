"""Comfy-native account controls for one trusted server operator.

No browser client ID is treated as an account identity. Credentials stay in the
private AccountManager; these routes expose its public metadata projection only.
"""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import os
import secrets
import urllib.parse

from .account import AccountError, AccountManager
from .catalog_service import CatalogService


class ControllerError(ValueError):
    def __init__(self, message, status=403):
        super().__init__(message)
        self.status = status


def _same_origin(*, host, remote, origin):
    if origin is not None:
        try:
            parsed = urllib.parse.urlsplit(origin)
            return (
                parsed.scheme in {"http", "https"}
                and parsed.netloc.lower() == host.lower()
                and not (
                    parsed.username
                    or parsed.password
                    or parsed.path
                    or parsed.query
                    or parsed.fragment
                )
            )
        except (ValueError, AttributeError):
            return False
    try:
        address = ipaddress.ip_address(remote)
        return address.is_loopback or bool(
            getattr(address, "ipv4_mapped", None) and address.ipv4_mapped.is_loopback
        )
    except (ValueError, TypeError):
        return False


class AccountController:
    def __init__(self, manager=None, *, catalog=None):
        self.manager = manager or AccountManager()
        self.catalog_service = catalog
        self.csrf = secrets.token_urlsafe(32)

    def _authorize(self, *, host, remote, origin, csrf=None, mutation=False):
        if not _same_origin(host=host, remote=remote, origin=origin):
            raise ControllerError("Open the Apixly panel from this ComfyUI server.")
        if mutation and (
            not isinstance(csrf, str) or not hmac.compare_digest(csrf, self.csrf)
        ):
            raise ControllerError(
                "Refresh the Apixly panel before changing its account."
            )

    @staticmethod
    def _identity(public):
        return (
            public.get("mode"),
            public.get("connected"),
            public.get("connection_id"),
            public.get("account", {}).get("id"),
            public.get("selected_key", {}).get("id"),
            public.get("selection_revision"),
        )

    def _state(self, include_keys=False):
        public = self.manager.public()
        key = os.environ.get("APIXLY_API_KEY", "").strip()
        result = {
            "account": public,
            "manual_key_available": bool(key and "\r" not in key and "\n" not in key),
            "csrf_token": self.csrf,
        }
        if include_keys and public.get("mode") == "account" and public.get("connected"):
            result["keys"] = self.manager.keys()
        return result

    def state(self, *, include_keys=False, **context):
        self._authorize(**context)
        return self._state(include_keys)

    def action(self, payload, *, csrf, **context):
        self._authorize(csrf=csrf, mutation=True, **context)
        if not isinstance(payload, dict) or not isinstance(payload.get("action"), str):
            raise ControllerError("Select an account action.", 400)
        action = payload["action"]
        allowed = {"action", "key_id"} if action == "select_key" else {"action"}
        if set(payload) - allowed:
            raise ControllerError(
                "Account actions do not accept credentials or extra fields.", 400
            )
        operations = {
            "begin": self.manager.start,
            "poll": self.manager.poll,
            "cancel": self.manager.cancel,
            "refresh": self.manager.refresh,
            "disconnect": self.manager.disconnect,
            "use_manual": self.manager.use_manual,
            "use_account": self.manager.use_account,
        }
        before = self._identity(self.manager.public())
        if action == "select_key":
            self.manager.select_key(payload.get("key_id"))
        elif action in operations:
            operations[action]()
        else:
            raise ControllerError("Unknown account action.", 400)
        if self.catalog_service and before != self._identity(self.manager.public()):
            self.catalog_service.clear()
        return self._state(
            include_keys=action
            in {"begin", "poll", "refresh", "select_key", "use_account"}
        )

    def catalog(self, *, force=False, **context):
        self._authorize(**context)
        if self.catalog_service is None:
            self.catalog_service = CatalogService(self.manager)
        return self.catalog_service.read(force=force)


def register_routes(server=None, controller=None):
    """Register once when imported by a real ComfyUI host; no standalone server."""
    if server is None:
        try:
            from server import PromptServer

            server = PromptServer.instance
        except ImportError:
            return False
    if server is None:
        return False
    if getattr(server, "_apixly_media_routes_registered", False):
        return True
    from aiohttp import web

    control = controller or AccountController()

    def context(request):
        return {
            "host": request.host,
            "remote": request.remote,
            "origin": request.headers.get("Origin"),
        }

    async def respond(operation):
        try:
            result = await asyncio.to_thread(operation)
            return web.json_response(result, headers={"Cache-Control": "no-store"})
        except ControllerError as error:
            return web.json_response(
                {"error": str(error)},
                status=error.status,
                headers={"Cache-Control": "no-store"},
            )
        except AccountError as error:
            return web.json_response(
                {"error": str(error), "account": control.manager.public()},
                status=400,
                headers={"Cache-Control": "no-store"},
            )
        except Exception:
            return web.json_response(
                {
                    "error": "The Apixly account panel could not complete this request. Refresh the panel."
                },
                status=503,
                headers={"Cache-Control": "no-store"},
            )

    @server.routes.get("/apixly/state")
    async def state(request):
        return await respond(
            lambda: control.state(
                include_keys=request.rel_url.query.get("keys") == "1",
                **context(request),
            )
        )

    @server.routes.post("/apixly/account")
    async def action(request):
        try:
            # Authorize before reading untrusted data or dispatching any operation.
            control._authorize(
                csrf=request.headers.get("X-Apixly-CSRF"),
                mutation=True,
                **context(request),
            )
            data = bytearray()
            while chunk := await request.content.read(1024):
                data.extend(chunk)
                if len(data) > 4096:
                    raise ControllerError("Account actions are limited to 4 KiB.", 413)
            payload = json.loads(data)
        except ControllerError as error:
            return web.json_response(
                {"error": str(error)},
                status=error.status,
                headers={"Cache-Control": "no-store"},
            )
        except (ValueError, UnicodeError):
            return web.json_response(
                {"error": "Account actions require valid JSON."},
                status=400,
                headers={"Cache-Control": "no-store"},
            )
        return await respond(
            lambda: control.action(
                payload, csrf=request.headers.get("X-Apixly-CSRF"), **context(request)
            )
        )

    @server.routes.get("/apixly/catalog")
    async def catalog(request):
        return await respond(
            lambda: control.catalog(
                force=request.rel_url.query.get("refresh") == "1", **context(request)
            )
        )

    server._apixly_media_routes_registered = True
    return True
