"""Ephemeral, namespace-bound read-only browser sessions."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from mcp_capability_bridge.contracts import AdapterCallError, InvocationContext
from mcp_capability_bridge.web_adapter import NetworkPolicy

MAX_NODES = 200
MAX_FIELD = 512
MAX_RESULT = 64 * 1024


@dataclass
class WebSession:
    namespace_id: str
    credential_generation: int
    target_id: str
    digest: bytes
    created: float
    touched: float
    inactivity: int
    absolute: int
    profile: Path
    driver: Any
    secret_values: tuple[str, ...]
    policy: NetworkPolicy
    generation: int = 0
    lock: asyncio.Lock | None = None


class WebSessionManager:
    def __init__(self, root: Path, driver_factory: Callable[..., Any] | None = None):
        self.root = root
        self.driver_factory = driver_factory or webdriver.Chrome
        self._sessions: list[WebSession] = []
        self._closed: list[tuple[bytes,str,int,str]] = []
        self._guard = asyncio.Lock()
        self._closing = False
        self._reaper: asyncio.Task | None = None

    def _ensure_reaper(self):
        if self._reaper is None or self._reaper.done():
            self._reaper=asyncio.create_task(self._reap_loop())

    async def _reap_loop(self):
        try:
            while not self._closing:
                await asyncio.sleep(5)
                async with self._guard:
                    now=time.monotonic();expired=[s for s in self._sessions if now-s.touched>s.inactivity or now-s.created>s.absolute]
                    self._sessions=[s for s in self._sessions if s not in expired]
                await asyncio.gather(*(self._cleanup(s) for s in expired),return_exceptions=True)
        except asyncio.CancelledError:
            pass

    @staticmethod
    def _digest(handle: str) -> bytes:
        return hashlib.sha256(handle.encode()).digest()

    async def _lookup(self, context: InvocationContext, handle: str) -> WebSession:
        wanted = self._digest(handle)
        async with self._guard:
            now = time.monotonic()
            expired = [s for s in self._sessions if now-s.touched > s.inactivity or now-s.created > s.absolute]
            for session in expired:
                self._sessions.remove(session)
            found = next((s for s in self._sessions if hmac.compare_digest(s.digest, wanted)), None)
        for session in expired:
            await self._cleanup(session)
        if found is None or found.namespace_id != context.namespace_id or found.credential_generation != context.credential_generation or found.target_id != context.target_id:
            raise AdapterCallError("invalid_web_session")
        found.touched = time.monotonic()
        return found

    async def open(self, context: InvocationContext, configuration: dict[str, Any], secret: bytes | None) -> dict[str, Any]:
        if self._closing:
            raise AdapterCallError("browser_runtime_stopping")
        self._ensure_reaper()
        policy = NetworkPolicy(configuration)
        await policy.verify_resolution()
        handle = secrets.token_urlsafe(32)
        auth = self._auth(configuration, secret)
        async with self._guard:
            if len(self._sessions) >= 8 or sum(s.namespace_id == context.namespace_id for s in self._sessions) >= 2:
                raise AdapterCallError("web_session_limit")
        try:
            profile, driver = await asyncio.wait_for(asyncio.to_thread(self._start, configuration, policy, auth), 30)
        except Exception as exc:
            raise AdapterCallError("browser_session_failed") from exc
        session = WebSession(context.namespace_id, context.credential_generation, context.target_id, self._digest(handle), time.monotonic(), time.monotonic(), configuration["inactivity_seconds"], configuration["absolute_seconds"], profile, driver, tuple(v for v in auth.values() if isinstance(v, str) and v), policy, lock=asyncio.Lock())
        async with self._guard:
            self._sessions.append(session)
        try:
            snapshot = await self._snapshot(session)
        except Exception:
            await self._remove(session)
            raise
        return {"session": handle, **snapshot}

    @staticmethod
    def _auth(configuration: dict[str, Any], secret: bytes | None) -> dict[str, str]:
        mode = configuration.get("authentication",{"mode":"none"})["mode"]
        if mode == "none":
            return {"mode": "none"}
        try:
            value = json.loads((secret or b"").decode())
        except Exception as exc:
            raise AdapterCallError("invalid_web_authentication") from exc
        if not isinstance(value, dict) or value.get("mode") != mode:
            raise AdapterCallError("invalid_web_authentication")
        return {str(k): str(v) for k, v in value.items()}

    def _start(self, configuration: dict[str, Any], policy: NetworkPolicy, auth: dict[str, str]):
        profile = Path(tempfile.mkdtemp(prefix="profile-", dir=self.root))
        parsed = urlparse(configuration["base_url"])
        rules = ", ".join([*(f"MAP {parsed.hostname} {address}" for address in policy.addresses), "MAP * ~NOTFOUND"])
        options = Options()
        for arg in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-background-networking", "--disable-sync", "--disable-extensions", "--disable-popup-blocking", "--no-first-run", "--remote-debugging-pipe", f"--host-resolver-rules={rules}", f"--user-data-dir={profile}"):
            options.add_argument(arg)
        options.add_experimental_option("prefs", {"download_restrictions": 3, "profile.default_content_setting_values": {"notifications": 2, "geolocation": 2, "media_stream": 2, "automatic_downloads": 2}})
        if not configuration["verify_tls"]:
            options.add_argument("--ignore-certificate-errors")
        driver = self.driver_factory(service=Service("/usr/bin/chromedriver", service_args=["--log-level=WARNING"]), options=options)
        try:
            driver.set_page_load_timeout(20)
            if auth["mode"] == "basic":
                import base64
                encoded = base64.b64encode(f'{auth["username"]}:{auth["password"]}'.encode()).decode()
                driver.execute_cdp_cmd("Network.enable", {})
                driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Authorization": f"Basic {encoded}"}})
            target = configuration["base_url"]
            if auth["mode"] == "form":
                target = policy.base_origin + configuration["authentication"]["login_path"]
            driver.get(target)
            policy.authorize(driver.current_url, "authentication_origins" if auth["mode"] == "form" else "navigation_origins")
            if auth["mode"] == "form":
                selectors = configuration["authentication"]
                driver.find_element("css selector", selectors["username_selector"]).send_keys(auth["username"])
                driver.find_element("css selector", selectors["password_selector"]).send_keys(auth["password"])
                driver.find_element("css selector", selectors["submit_selector"]).click()
                time.sleep(1)
                policy.authorize(driver.current_url, "navigation_origins")
            if len(driver.window_handles) != 1:
                raise RuntimeError("browser_popup_denied")
            return profile, driver
        except Exception:
            try: driver.quit()
            except Exception: pass
            shutil.rmtree(profile, ignore_errors=True)
            raise

    async def snapshot(self, context: InvocationContext, handle: str) -> dict[str, Any]:
        session = await self._lookup(context, handle)
        if session.lock is None or session.lock.locked():
            raise AdapterCallError("web_session_busy")
        async with session.lock:
            return await self._snapshot(session)

    async def _snapshot(self, session: WebSession) -> dict[str, Any]:
        try:
            session.policy.authorize(session.driver.current_url,"navigation_origins")
            raw = await asyncio.wait_for(asyncio.to_thread(session.driver.execute_cdp_cmd, "Accessibility.getFullAXTree", {}), 15)
        except Exception as exc:
            await self._remove(session)
            raise AdapterCallError("browser_session_failed") from exc
        nodes = []
        raw_nodes=raw.get("nodes",[]);by_id={node.get("nodeId"):node for node in raw_nodes}
        def depth(node):
            value=0;parent=node.get("parentId")
            while parent in by_id and value<=12:value+=1;parent=by_id[parent].get("parentId")
            return value
        for node in raw_nodes:
            role = str(node.get("role", {}).get("value", ""))[:MAX_FIELD]
            protected=any(item.get("name")=="protected" and item.get("value",{}).get("value") for item in node.get("properties",[]))
            if node.get("ignored") or protected or depth(node)>12 or role.lower() in {"password", "none"}:
                continue
            name = self._redact(str(node.get("name", {}).get("value", ""))[:MAX_FIELD], session.secret_values)
            value = self._redact(str(node.get("value", {}).get("value", ""))[:MAX_FIELD], session.secret_values)
            if not role and not name and not value:
                continue
            nodes.append({"role": role, "name": name, "value": value})
            if len(nodes) >= MAX_NODES:
                break
        session.generation += 1
        result = {"generation": session.generation, "origin": self._safe_origin(session.driver.current_url), "nodes": nodes, "truncated": len(raw.get("nodes", [])) > len(nodes)}
        while len(json.dumps(result, ensure_ascii=False).encode()) > MAX_RESULT and result["nodes"]:
            result["nodes"].pop(); result["truncated"] = True
        return result

    @staticmethod
    def _redact(value: str, secrets_: tuple[str, ...]) -> str:
        for secret in secrets_:
            value = value.replace(secret, "[REDACTED]")
        return value

    @staticmethod
    def _safe_origin(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    async def wait(self, context: InvocationContext, handle: str, seconds: int) -> dict[str, Any]:
        session = await self._lookup(context, handle)
        if session.lock is None or session.lock.locked():
            raise AdapterCallError("web_session_busy")
        async with session.lock:
            await asyncio.sleep(seconds)
            return await self._snapshot(session)

    async def close(self, context: InvocationContext, handle: str) -> dict[str, Any]:
        try:
            session = await self._lookup(context, handle)
        except AdapterCallError:
            wanted=self._digest(handle)
            if any(hmac.compare_digest(digest,wanted) and owner==context.namespace_id and generation==context.credential_generation and target==context.target_id for digest,owner,generation,target in self._closed):return {"closed":True}
            raise
        self._closed.append((session.digest,session.namespace_id,session.credential_generation,session.target_id));self._closed=self._closed[-256:]
        await self._remove(session)
        return {"closed": True}

    async def _remove(self, session: WebSession):
        async with self._guard:
            if session in self._sessions:
                self._sessions.remove(session)
        await self._cleanup(session)

    async def _cleanup(self, session: WebSession):
        def clean():
            try: session.driver.quit()
            except Exception: pass
            shutil.rmtree(session.profile, ignore_errors=True)
        await asyncio.to_thread(clean)

    async def close_namespace(self, namespace_id: str):
        async with self._guard:
            selected = [s for s in self._sessions if s.namespace_id == namespace_id]
            self._sessions = [s for s in self._sessions if s.namespace_id != namespace_id]
        await asyncio.gather(*(self._cleanup(s) for s in selected), return_exceptions=True)

    async def close_all(self):
        self._closing = True
        if self._reaper is not None:
            self._reaper.cancel();await asyncio.gather(self._reaper,return_exceptions=True);self._reaper=None
        async with self._guard:
            selected, self._sessions = self._sessions, []
        await asyncio.gather(*(self._cleanup(s) for s in selected), return_exceptions=True)

    def target_in_use(self, target_id: str) -> bool:
        return any(s.target_id == target_id for s in self._sessions)

    def count(self) -> int:
        return len(self._sessions)

    def describe(self) -> list[dict[str, Any]]:
        now = time.monotonic()
        return [{"namespace_id": s.namespace_id, "target_id": s.target_id, "age_seconds": int(now-s.created), "idle_seconds": int(now-s.touched), "generation": s.generation} for s in self._sessions]
