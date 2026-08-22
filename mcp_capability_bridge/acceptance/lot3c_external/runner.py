#!/usr/bin/env python3
"""External black-box acceptance runner for MCB Lot 3C."""

from __future__ import annotations

import asyncio
import base64
import getpass
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

READER_PORT = 18080
ADMIN_PORT = 18082
EXTERNAL_PORT = 18081


class State:
    lock = threading.Lock()
    admin_effects = 0
    reader_denials = 0
    external_requests = 0


class ExternalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        with State.lock:
            State.external_requests += 1
        self.send_response(204); self.end_headers()

    def log_message(self, *_):
        return


def expected_authorization(role: str) -> str:
    return "Basic " + base64.b64encode(f"{role}:{role}-secret".encode()).decode()


class FixtureHandler(BaseHTTPRequestHandler):
    role = "reader"
    external_origin = ""

    def authorized_role(self) -> str:
        return self.role if self.headers.get("Authorization") == expected_authorization(self.role) else "unauthenticated"

    def do_GET(self):
        if self.path == "/__state":
            with State.lock:
                body = json.dumps({"admin_effects": State.admin_effects, "reader_denials": State.reader_denials, "external_requests": State.external_requests}).encode()
            return self.respond(200, body, "application/json")
        if self.path == "/redirect":
            self.send_response(302); self.send_header("Location", self.external_origin + "/redirected"); self.end_headers(); return
        if self.path == "/iframe":
            return self.page("<h1>Iframe test</h1><iframe src='/'></iframe>")
        if self.path == "/popup":
            return self.page("<h1>Popup test</h1><button aria-label='Open popup' onclick=\"window.open('/')\">Open popup</button>")
        if self.path == "/escape":
            return self.page(f"<h1>Network escape test</h1><script>fetch('{self.external_origin}/fetch');new WebSocket('{self.external_origin.replace('http:', 'ws:')}/socket')</script>")
        if self.path == "/page-two":
            return self.page("<h1>Page Two</h1><p>Relative navigation succeeded</p>")
        if self.path == "/download.bin":
            self.send_response(200); self.send_header("Content-Disposition", "attachment; filename=test.bin"); self.end_headers(); self.wfile.write(b"blocked-download"); return
        if self.path != "/":
            self.send_error(404); return
        role = self.authorized_role()
        return self.page(f"""<h1>Lot 3C {self.role.title()}</h1><p>Authority: {role}</p>
<label>Name <input aria-label='Name' value='before'></label>
<label>Mode <select aria-label='Mode'><option value='read'>Read</option><option value='admin'>Admin</option></select></label>
<button aria-label='Apply effect' onclick="applyEffect()">Apply effect</button>
<input type='password' aria-label='Forbidden password'><input type='file' aria-label='Forbidden upload'>
<a aria-label='Forbidden download' download href='/download.bin'>Download</a>
<p id='status'>Effect status: untouched</p><p id='key'>Key status: untouched</p>
<script>
async function applyEffect(){{const r=await fetch('/effect',{{method:'POST'}});document.getElementById('status').textContent='Effect status: '+(r.ok?'applied':'denied')}}
document.querySelector('[aria-label=Name]').addEventListener('keydown',e=>document.getElementById('key').textContent='Key status: '+e.key)
</script>""")

    def do_POST(self):
        if self.path != "/effect":
            self.send_error(404); return
        if self.role == "admin" and self.authorized_role() == "admin":
            with State.lock:
                State.admin_effects += 1
            self.send_response(204); self.end_headers(); return
        with State.lock:
            State.reader_denials += 1
        self.send_response(403); self.end_headers()

    def page(self, content: str):
        body = f"<!doctype html><html><head><title>MCB Lot 3C</title></head><body>{content}</body></html>".encode()
        return self.respond(200, body, "text/html; charset=utf-8")

    def respond(self, status: int, body: bytes, content_type: str):
        self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *_):
        return


def handler(role: str, external_origin: str):
    return type(f"{role.title()}Handler", (FixtureHandler,), {"role": role, "external_origin": external_origin})


def local_address(remote: str) -> str:
    host = remote.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((host, 9))
        return probe.getsockname()[0]


def text_content(result: Any) -> str:
    return "\n".join(str(getattr(item, "text", "")) for item in result.content)


def error_code(result: Any) -> str:
    text = text_content(result)
    for _ in range(2):
        try:
            value = json.loads(text)
        except Exception:
            break
        if isinstance(value, dict) and isinstance(value.get("error"), dict):
            return str(value["error"].get("code", "unknown_error"))
        if isinstance(value, str):
            text = value
        else:
            break
    return "unknown_error"


def decoded(result: Any) -> dict[str, Any]:
    if result.isError:
        raise RuntimeError(f"tool_error:{error_code(result)}")
    value = json.loads(text_content(result))
    if not isinstance(value, dict) or not isinstance(value.get("result"), dict):
        raise RuntimeError("invalid_tool_result")
    return value["result"]


async def call(url: str, token: str, tool: str, arguments: dict[str, Any]):
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=45) as client:
        async with streamable_http_client(url, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool, arguments)


async def inventory(url: str, token: str) -> set[str]:
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=20) as client:
        async with streamable_http_client(url, http_client=client) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return {tool.name for tool in (await session.list_tools()).tools}


def check(condition: bool, label: str):
    if not condition:
        raise RuntimeError(label)
    print(f"OK  {label}")


def find_reference(snapshot: dict[str, Any], role: str, name: str) -> str:
    for node in snapshot.get("nodes", []):
        if str(node.get("role", "")).lower() == role and name.lower() in str(node.get("name", "")).lower() and node.get("reference"):
            return str(node["reference"])
    raise RuntimeError(f"reference_absente:{role}:{name}")


async def invoke(url: str, token: str, prefix: str, capability: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return decoded(await call(url, token, f"{prefix}_{capability}", arguments))


async def state(address: str) -> dict[str, int]:
    async with httpx.AsyncClient(timeout=5) as client:
        return (await client.get(f"http://{address}:{READER_PORT}/__state")).json()


async def run(url: str, address: str, reader_prefix: str, admin_prefix: str, token: str):
    tools = await inventory(url, token)
    reader_required = {f"{reader_prefix}_{name}" for name in ("open", "click", "close")}
    admin_required = {f"{admin_prefix}_{name}" for name in ("open", "snapshot", "wait", "navigate", "click", "fill", "select", "press", "close")}
    check(reader_required <= tools, "outils Reader publiés")
    check(admin_required <= tools, "neuf outils Admin publiés")

    reader = await invoke(url, token, reader_prefix, "open", {})
    reader_handle = str(reader["session"])
    reader_button = find_reference(reader, "button", "Apply effect")
    clicked = await invoke(url, token, reader_prefix, "click", {"session": reader_handle, "reference": reader_button})
    await invoke(url, token, reader_prefix, "close", {"session": reader_handle})
    check((await state(address))["reader_denials"] == 1, "compte Reader réellement privé d'effet")
    check("password" not in json.dumps(clicked).lower(), "aucun champ password exposé")

    opened = await invoke(url, token, admin_prefix, "open", {})
    handle = str(opened["session"])
    textbox = find_reference(opened, "textbox", "Name")
    filled = await invoke(url, token, admin_prefix, "fill", {"session": handle, "reference": textbox, "value": "Lot 3C value"})
    check("Lot 3C value" in json.dumps(filled), "fill borné")
    combo = find_reference(filled, "combobox", "Mode")
    selected = await invoke(url, token, admin_prefix, "select", {"session": handle, "reference": combo, "value": "admin"})
    check(isinstance(selected.get("generation"), int), "select borné")
    textbox = find_reference(selected, "textbox", "Name")
    pressed = await invoke(url, token, admin_prefix, "press", {"session": handle, "reference": textbox, "key": "Enter"})
    waited = await invoke(url, token, admin_prefix, "wait", {"session": handle, "seconds": 1})
    check("Key status: Enter" in json.dumps(pressed) or "Key status: Enter" in json.dumps(waited), "press borné")
    second = await invoke(url, token, admin_prefix, "navigate", {"session": handle, "path": "/page-two"})
    check("Relative navigation succeeded" in json.dumps(second), "navigation strictement relative")
    home = await invoke(url, token, admin_prefix, "navigate", {"session": handle, "path": "/"})
    button = find_reference(home, "button", "Apply effect")
    stale = find_reference(home, "textbox", "Name")
    await invoke(url, token, admin_prefix, "click", {"session": handle, "reference": button})
    stale_result = await call(url, token, f"{admin_prefix}_fill", {"session": handle, "reference": stale, "value": "replay"})
    check(stale_result.isError and error_code(stale_result) == "stale_reference", "référence précédente invalidée")
    await invoke(url, token, admin_prefix, "wait", {"session": handle, "seconds": 1})
    await invoke(url, token, admin_prefix, "close", {"session": handle})
    check((await state(address))["admin_effects"] == 1, "compte Admin autorisé et effet non rejoué")

    concurrent = await invoke(url, token, admin_prefix, "open", {})
    concurrent_handle = str(concurrent["session"]); concurrent_button = find_reference(concurrent, "button", "Apply effect")
    results = await asyncio.gather(*[call(url, token, f"{admin_prefix}_click", {"session": concurrent_handle, "reference": concurrent_button}) for _ in range(2)])
    check(sum(not item.isError for item in results) == 1 and sum(error_code(item) == "stale_reference" for item in results if item.isError) == 1, "actions simultanées sérialisées")
    await invoke(url, token, admin_prefix, "close", {"session": concurrent_handle})
    check((await state(address))["admin_effects"] == 2, "une seule exécution de l'action concurrente")

    iframe = await invoke(url, token, admin_prefix, "open", {}); iframe_handle = str(iframe["session"])
    denied = await call(url, token, f"{admin_prefix}_navigate", {"session": iframe_handle, "path": "/iframe"})
    check(denied.isError and error_code(denied) == "browser_frame_denied", "iframe refusée")
    invalid = await call(url, token, f"{admin_prefix}_snapshot", {"session": iframe_handle})
    check(invalid.isError and error_code(invalid) == "invalid_web_session", "session iframe invalidée")

    popup = await invoke(url, token, admin_prefix, "open", {}); popup_handle = str(popup["session"])
    popup_page = await invoke(url, token, admin_prefix, "navigate", {"session": popup_handle, "path": "/popup"})
    popup_ref = find_reference(popup_page, "button", "Open popup")
    denied = await call(url, token, f"{admin_prefix}_click", {"session": popup_handle, "reference": popup_ref})
    check(denied.isError and error_code(denied) == "browser_popup_denied", "popup refusée")

    escape = await invoke(url, token, admin_prefix, "open", {}); escape_handle = str(escape["session"])
    await invoke(url, token, admin_prefix, "navigate", {"session": escape_handle, "path": "/escape"})
    await asyncio.sleep(1)
    check((await state(address))["external_requests"] == 0, "ressource et WebSocket hors origine bloqués")
    redirected = await call(url, token, f"{admin_prefix}_navigate", {"session": escape_handle, "path": "/redirect"})
    check(redirected.isError and (await state(address))["external_requests"] == 0, "redirection hors origine refusée")


def main() -> int:
    url = input("URL MCP [http://192.168.1.15:18098/mcp] : ").strip() or "http://192.168.1.15:18098/mcp"
    address = local_address(url)
    external_origin = f"http://{address}:{EXTERNAL_PORT}"
    servers = [
        ThreadingHTTPServer(("0.0.0.0", READER_PORT), handler("reader", external_origin)),
        ThreadingHTTPServer(("0.0.0.0", ADMIN_PORT), handler("admin", external_origin)),
        ThreadingHTTPServer(("0.0.0.0", EXTERNAL_PORT), ExternalHandler),
    ]
    for server in servers:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"\nFixture Reader : http://{address}:{READER_PORT}/  — Basic reader / reader-secret")
    print(f"Fixture Admin  : http://{address}:{ADMIN_PORT}/  — Basic admin / admin-secret")
    print("Crée les deux cibles temporaires avec inactivité >= 30 s et durée absolue >= 300 s, puis teste leur navigateur.")
    print("Crée un client MCP temporaire. Publie open/click/close pour Reader et les neuf outils pour Admin.")
    input("Appuie sur Entrée lorsque les cibles, tests navigateur et publications sont prêts… ")
    reader_key = input("Clé technique de la cible Reader : ").strip()
    admin_key = input("Clé technique de la cible Admin : ").strip()
    token = getpass.getpass("Credential du client temporaire (saisie masquée) : ").strip()
    try:
        asyncio.run(run(url, address, f"web_{reader_key}", f"web_{admin_key}", token))
    except Exception as exc:
        print(f"\nKO  {type(exc).__name__}: {exc}")
        return 1
    finally:
        for server in servers:
            server.shutdown(); server.server_close()
        token = ""
    print("\nSUCCÈS — recette externe Lot 3C terminée.")
    print("Tu peux supprimer les deux cibles, révoquer/archiver le client temporaire et retirer le port hôte 18098.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
