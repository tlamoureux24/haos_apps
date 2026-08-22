#!/usr/bin/env python3
"""External black-box acceptance runner for MCB Lot 3B."""

from __future__ import annotations

import asyncio
import getpass
import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

FIXTURE_PORT = 18080
KEEPALIVE_SECONDS = 8


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/", "/favicon.ico"}:
            self.send_error(404)
            return
        if self.path == "/favicon.ico":
            self.send_response(204); self.end_headers(); return
        cookie_fresh = "mcb_fixture=" not in self.headers.get("Cookie", "")
        marker = secrets.token_hex(12)
        body = f"""<!doctype html><html><head><title>MCB Lot 3B fixture</title></head>
<body><main><h1>MCP Bridge acceptance fixture</h1>
<p id=\"cookie\">Cookie state: {'fresh' if cookie_fresh else 'reused'}</p>
<p id=\"storage\">Storage state: checking</p><p>Read-only fixture marker: {marker}</p></main>
<script>const old=localStorage.getItem('mcb_fixture');document.getElementById('storage').textContent='Storage state: '+(old?'reused':'fresh');if(!old)localStorage.setItem('mcb_fixture','{marker}');</script>
</body></html>""".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if cookie_fresh:
            self.send_header("Set-Cookie", f"mcb_fixture={marker}; HttpOnly; SameSite=Strict")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def log_message(self, *_):
        return


def local_address(remote: str) -> str:
    host = remote.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((host, 9))
        return probe.getsockname()[0]


def text_content(result: Any) -> str:
    return "\n".join(str(getattr(item, "text", "")) for item in result.content)


def decoded_result(result: Any) -> dict[str, Any]:
    if result.isError:
        raise RuntimeError(f"tool_error:{error_code(result)}")
    value = json.loads(text_content(result))
    if not isinstance(value, dict) or not isinstance(value.get("result"), dict):
        raise RuntimeError("invalid_tool_result")
    return value["result"]


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


async def credential_rejected(url: str, token: str) -> bool:
    async with httpx.AsyncClient(timeout=10) as client:
        response=await client.get(url,headers={"Authorization":f"Bearer {token}"})
    return response.status_code==401


def check(condition: bool, label: str):
    if not condition:
        raise RuntimeError(label)
    print(f"OK  {label}")


async def open_session(url: str, token: str, prefix: str) -> dict[str, Any]:
    return decoded_result(await call(url, token, f"{prefix}_open", {}))


async def snapshot(url: str, token: str, prefix: str, handle: str):
    return await call(url, token, f"{prefix}_snapshot", {"session": handle})


async def close(url: str, token: str, prefix: str, handle: str):
    return await call(url, token, f"{prefix}_close", {"session": handle})


async def interactive_pause(message:str, keepalive:list[tuple[str,str,str,str]], secret_prompt:str|None=None)->str|None:
    stop=asyncio.Event()
    async def pulse(url:str,token:str,prefix:str,handle:str):
        while not stop.is_set():
            try:await asyncio.wait_for(stop.wait(),timeout=KEEPALIVE_SECONDS)
            except asyncio.TimeoutError:
                try:await snapshot(url,token,prefix,handle)
                except Exception:pass
    tasks=[asyncio.create_task(pulse(*item)) for item in keepalive]
    try:
        await asyncio.to_thread(input,message)
        return await asyncio.to_thread(getpass.getpass,secret_prompt) if secret_prompt else None
    finally:
        stop.set()
        await asyncio.gather(*tasks,return_exceptions=True)


async def run(url: str, prefix: str, token_a: str, token_b: str):
    required = {f"{prefix}_{name}" for name in ("open", "snapshot", "wait", "close")}
    check(required <= await inventory(url, token_a), "outils publiés pour le client A")
    check(required <= await inventory(url, token_b), "outils publiés pour le client B")

    first = await open_session(url, token_a, prefix); handle_a = str(first["session"])
    denied = await snapshot(url, token_b, prefix, handle_a)
    check(denied.isError and error_code(denied) == "invalid_web_session", "isolation A → B")
    resumed = decoded_result(await snapshot(url, token_a, prefix, handle_a))
    check(int(resumed["generation"]) > int(first["generation"]), "session A toujours utilisable")
    decoded_result(await close(url, token_a, prefix, handle_a))
    decoded_result(await close(url, token_a, prefix, handle_a))
    print("OK  fermeture idempotente")

    states = []
    handles = []
    for _ in range(2):
        opened = await open_session(url, token_a, prefix); handles.append(opened["session"])
        rendered = json.dumps(opened, ensure_ascii=False)
        states.append(("Cookie state: fresh" in rendered, "Storage state: fresh" in rendered))
        decoded_result(await close(url, token_a, prefix, str(opened["session"])))
    check(handles[0] != handles[1], "handles successifs distincts")
    check(all(cookie and storage for cookie, storage in states), "aucun cookie/storage partagé entre profils")

    expiring = await open_session(url, token_a, prefix); expiring_handle = str(expiring["session"])
    print("INFO attente de 37 secondes pour vérifier l’expiration…")
    await asyncio.sleep(37)
    expired = await snapshot(url, token_a, prefix, expiring_handle)
    check(expired.isError and error_code(expired) == "invalid_web_session", "expiration par inactivité")

    session_a = await open_session(url, token_a, prefix)
    session_b = await open_session(url, token_b, prefix)
    rotated_a = str(await interactive_pause("\nRenouvelle maintenant le credential du client A dans le Bridge, puis appuie sur Entrée… ",[(url,token_a,prefix,str(session_a["session"])),(url,token_b,prefix,str(session_b["session"]))],"Nouveau credential A (saisie masquée) : ")).strip()
    check(await credential_rejected(url,token_a),"ancien credential A refusé après rotation")
    old_handle = await snapshot(url, rotated_a, prefix, str(session_a["session"]))
    check(old_handle.isError and error_code(old_handle) == "invalid_web_session", "rotation ferme la session A")
    decoded_result(await snapshot(url, token_b, prefix, str(session_b["session"])))
    print("OK  rotation A ne ferme pas la session B")
    decoded_result(await close(url, token_b, prefix, str(session_b["session"])))

    revoked_a_session = await open_session(url, rotated_a, prefix)
    surviving_b = await open_session(url, token_b, prefix)
    await interactive_pause("\nRévoque maintenant le client A dans le Bridge, puis appuie sur Entrée… ",[(url,rotated_a,prefix,str(revoked_a_session["session"])),(url,token_b,prefix,str(surviving_b["session"]))])
    check(await credential_rejected(url,rotated_a),"credential A refusé après révocation")
    decoded_result(await snapshot(url, token_b, prefix, str(surviving_b["session"])))
    print("OK  révocation A ne ferme pas la session B")
    decoded_result(await close(url, token_b, prefix, str(surviving_b["session"])))
    print("INFO vérifie dans la page Sessions que la session A révoquée a disparu.")
    del revoked_a_session


def main() -> int:
    url = input("URL MCP [http://192.168.1.15:18098/mcp] : ").strip() or "http://192.168.1.15:18098/mcp"
    address = local_address(url)
    server = ThreadingHTTPServer(("0.0.0.0", FIXTURE_PORT), FixtureHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"\nFixture prête : http://{address}:{FIXTURE_PORT}/")
    print("Crée dans le Bridge une cible Web temporaire vers cette URL avec inactivité=30 s et durée absolue >= 300 s.")
    print("Crée deux clients temporaires A/B et publie les quatre outils de cette cible vers chacun.")
    input("Appuie sur Entrée lorsque la cible, son test navigateur et les publications sont prêts… ")
    target_key = input("Clé technique affichée sous la cible Web : ").strip()
    prefix = f"web_{target_key}"
    token_a = getpass.getpass("Credential A (saisie masquée) : ").strip()
    token_b = getpass.getpass("Credential B (saisie masquée) : ").strip()
    try:
        asyncio.run(run(url, prefix, token_a, token_b))
    except Exception as exc:
        print(f"\nKO  {type(exc).__name__}: {exc}")
        return 1
    finally:
        server.shutdown();server.server_close();token_a = token_b = ""
    print("\nSUCCÈS — recette externe Lot 3B terminée.")
    print("Tu peux supprimer la cible temporaire, révoquer/archiver les clients de test et retirer le port hôte 18098.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
