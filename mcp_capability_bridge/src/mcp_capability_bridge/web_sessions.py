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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from mcp_capability_bridge.contracts import AdapterCallError, InvocationContext
from mcp_capability_bridge.web_adapter import NetworkPolicy
from mcp_capability_bridge.web_tls import verify_driver_certificate

MAX_NODES = 200
MAX_FIELD = 512
MAX_RESULT = 64 * 1024
ACTIONABLE_ROLES = frozenset({"button", "checkbox", "combobox", "link", "menuitem", "radio", "searchbox", "slider", "spinbutton", "switch", "textbox"})
PRESS_KEYS = frozenset({"Enter", "Escape", "ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown", "Tab", "Space"})


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
    references: dict[str, tuple[int, int, str, str, str]] = field(default_factory=dict)


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
        await self._verify_policy_resolution(policy)
        handle = secrets.token_urlsafe(32)
        auth = self._auth(configuration, secret)
        async with self._guard:
            if len(self._sessions) >= 8 or sum(s.namespace_id == context.namespace_id for s in self._sessions) >= 2:
                raise AdapterCallError("web_session_limit")
        try:
            profile, driver = await asyncio.wait_for(asyncio.to_thread(self._start, configuration, policy, auth), 30)
        except RuntimeError as exc:
            if str(exc) in {"web_certificate_sha256_mismatch","web_certificate_unavailable"}:
                raise AdapterCallError(str(exc)) from None
            raise AdapterCallError("browser_session_failed") from exc
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
        extension = policy.install_extension(profile)
        parsed = urlparse(configuration["base_url"])
        rules = ", ".join([*(f"MAP {parsed.hostname} {address}" for address in policy.addresses), "MAP * ~NOTFOUND"])
        options = Options()
        for arg in ("--headless=new", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-background-networking", "--disable-sync", "--disable-popup-blocking", "--no-first-run", "--remote-debugging-pipe", f"--host-resolver-rules={rules}", f"--user-data-dir={profile}", f"--load-extension={extension}"):
            options.add_argument(arg)
        options.add_experimental_option("prefs", {"download_restrictions": 3, "profile.default_content_setting_values": {"notifications": 2, "geolocation": 2, "media_stream": 2, "automatic_downloads": 2}})
        if not configuration["verify_tls"] or configuration.get("certificate_sha256"):
            options.add_argument("--ignore-certificate-errors")
        driver = self.driver_factory(service=Service("/usr/bin/chromedriver", service_args=["--log-level=WARNING"]), options=options)
        try:
            driver.set_page_load_timeout(20)
            if configuration.get("certificate_sha256"):
                driver.execute_cdp_cmd("Network.enable", {})
            target = configuration["base_url"]
            if auth["mode"] == "form":
                target = policy.base_origin + configuration["authentication"]["login_path"]
            driver.get(target)
            verify_driver_certificate(driver,policy.base_origin,configuration.get("certificate_sha256",""))
            if auth["mode"] == "basic":
                import base64
                encoded = base64.b64encode(f'{auth["username"]}:{auth["password"]}'.encode()).decode()
                driver.execute_cdp_cmd("Network.enable", {})
                driver.execute_cdp_cmd("Network.setExtraHTTPHeaders", {"headers": {"Authorization": f"Basic {encoded}"}})
                driver.get(target)
                verify_driver_certificate(driver,policy.base_origin,configuration.get("certificate_sha256",""))
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
            await self._verify_policy_resolution(session.policy)
        except Exception as exc:
            await self._remove(session)
            raise AdapterCallError("web_resolution_changed") from exc
        try:
            session.policy.authorize(session.driver.current_url,"navigation_origins")
        except Exception as exc:
            await self._remove(session)
            raise AdapterCallError("web_origin_denied") from exc
        try:
            raw = await asyncio.wait_for(asyncio.to_thread(session.driver.execute_cdp_cmd, "Accessibility.getFullAXTree", {}), 15)
        except Exception as exc:
            await self._remove(session)
            raise AdapterCallError("browser_session_failed") from exc
        nodes = []
        raw_nodes=raw.get("nodes",[]);by_id={node["nodeId"]:node for node in raw_nodes if node.get("nodeId") is not None}
        def depth(node):
            value=0;parent=node.get("parentId")
            while parent is not None and parent in by_id and value<=12:value+=1;parent=by_id[parent].get("parentId")
            return value
        for node in raw_nodes:
            role = str(node.get("role", {}).get("value", ""))[:MAX_FIELD]
            protected=any(item.get("name")=="protected" and item.get("value",{}).get("value") for item in node.get("properties",[]))
            if node.get("ignored") or protected or depth(node)>12 or role.lower() in {"password", "none"}:
                continue
            name = self._redact(str(node.get("name", {}).get("value", ""))[:MAX_FIELD], session.secret_values)
            value = self._redact(str(node.get("value", {}).get("value", ""))[:MAX_FIELD], session.secret_values)
            state = self._node_state(node)
            if not role and not name and not value:
                continue
            item = {"role": role, "name": name, "value": value, "state": state}
            backend_id = node.get("backendDOMNodeId")
            reference_allowed = False
            if role.lower() in ACTIONABLE_ROLES and isinstance(backend_id, int):
                try:
                    reference_allowed = await asyncio.wait_for(asyncio.to_thread(self._reference_allowed, session.driver, backend_id), 5)
                except Exception:
                    reference_allowed = False
            if reference_allowed:
                reference = secrets.token_urlsafe(24)
                session.references[reference] = (session.generation + 1, backend_id, role, name, json.dumps(state,sort_keys=True,separators=(",",":")))
                item["reference"] = reference
            nodes.append(item)
            if len(nodes) >= MAX_NODES:
                break
        session.generation += 1
        session.references = {key: value for key, value in session.references.items() if value[0] == session.generation}
        result = {"generation": session.generation, "origin": self._safe_origin(session.driver.current_url), "nodes": nodes, "truncated": len(raw.get("nodes", [])) > len(nodes)}
        while len(json.dumps(result, ensure_ascii=False).encode()) > MAX_RESULT and result["nodes"]:
            result["nodes"].pop(); result["truncated"] = True
        return result

    async def navigate(self, context: InvocationContext, handle: str, relative: str) -> dict[str, Any]:
        session = await self._lookup(context, handle)
        if session.lock is None:
            raise AdapterCallError("invalid_web_session")
        async with session.lock:
            if not relative.startswith("/") or relative.startswith("//") or any(ord(char) < 32 for char in relative):
                raise AdapterCallError("invalid_web_navigation")
            target = urljoin(session.policy.base_origin + "/", relative)
            session.policy.authorize(target, "navigation_origins")
            await self._verify_policy_resolution(session.policy)
            self._invalidate(session)
            try:
                await asyncio.wait_for(asyncio.to_thread(session.driver.get, target), 20)
                await self._validate_context(session)
                return await self._snapshot(session)
            except AdapterCallError as exc:
                if exc.code in {"browser_popup_denied", "web_origin_denied", "browser_frame_denied"}:
                    await self._remove(session)
                raise AdapterCallError(exc.code, True) from None
            except Exception as exc:
                raise AdapterCallError("browser_action_ambiguous", True) from exc

    async def action(self, context: InvocationContext, handle: str, reference: str, action: str, value: str | None = None) -> dict[str, Any]:
        session = await self._lookup(context, handle)
        if session.lock is None:
            raise AdapterCallError("invalid_web_session")
        async with session.lock:
            descriptor = session.references.get(reference)
            if descriptor is None or descriptor[0] != session.generation:
                raise AdapterCallError("stale_reference")
            await self._verify_policy_resolution(session.policy)
            try:
                object_id = await asyncio.wait_for(asyncio.to_thread(self._revalidate_reference, session, descriptor), 10)
            except AdapterCallError:
                self._invalidate(session)
                raise
            except Exception as exc:
                self._invalidate(session)
                raise AdapterCallError("stale_reference") from exc
            self._invalidate(session)
            try:
                await asyncio.wait_for(asyncio.to_thread(self._perform_action, session, object_id, action, value), 15)
                await self._validate_context(session)
                return await self._snapshot(session)
            except AdapterCallError as exc:
                if exc.code in {"browser_popup_denied", "web_origin_denied", "browser_frame_denied", "web_resolution_changed"}:
                    await self._remove(session)
                raise AdapterCallError(exc.code, True) from None
            except Exception as exc:
                raise AdapterCallError("browser_action_ambiguous", True) from exc

    @staticmethod
    def _invalidate(session: WebSession) -> None:
        session.references.clear()
        session.generation += 1

    @staticmethod
    async def _verify_policy_resolution(policy: NetworkPolicy) -> None:
        try:
            await policy.verify_resolution()
        except Exception as exc:
            raise AdapterCallError("web_resolution_changed") from exc

    async def _validate_context(self, session: WebSession) -> None:
        try:
            session.policy.authorize(session.driver.current_url, "navigation_origins")
            if len(session.driver.window_handles) != 1:
                raise AdapterCallError("browser_popup_denied", True)
            frames = await asyncio.wait_for(asyncio.to_thread(session.driver.execute_script, "return window.frames.length"), 5)
            if frames != 0:
                raise AdapterCallError("browser_frame_denied", True)
        except AdapterCallError:
            raise
        except Exception as exc:
            raise AdapterCallError("web_origin_denied", True) from exc

    @staticmethod
    def _revalidate_reference(session: WebSession, descriptor: tuple[int, int, str, str, str]) -> str:
        _, backend_id, expected_role, expected_name, expected_state = descriptor
        raw = session.driver.execute_cdp_cmd("Accessibility.getFullAXTree", {})
        current = next((node for node in raw.get("nodes", []) if node.get("backendDOMNodeId") == backend_id), None)
        if current is None or current.get("ignored"):
            raise AdapterCallError("stale_reference")
        role = str(current.get("role", {}).get("value", ""))[:MAX_FIELD]
        name = WebSessionManager._redact(str(current.get("name", {}).get("value", ""))[:MAX_FIELD], session.secret_values)
        state = json.dumps(WebSessionManager._node_state(current),sort_keys=True,separators=(",",":"))
        if role != expected_role or name != expected_name or state != expected_state:
            raise AdapterCallError("stale_reference")
        resolved = session.driver.execute_cdp_cmd("DOM.resolveNode", {"backendNodeId": backend_id})
        object_id = resolved.get("object", {}).get("objectId")
        if not isinstance(object_id, str) or not object_id:
            raise AdapterCallError("stale_reference")
        return object_id

    @staticmethod
    def _reference_allowed(driver: Any, backend_id: int) -> bool:
        resolved = driver.execute_cdp_cmd("DOM.resolveNode", {"backendNodeId": backend_id})
        object_id = resolved.get("object", {}).get("objectId")
        if not isinstance(object_id, str) or not object_id:
            return False
        inspected = driver.execute_cdp_cmd("Runtime.callFunctionOn", {"objectId": object_id, "functionDeclaration": "function(){return {type:(this.type||'').toLowerCase(),download:Boolean(this.hasAttribute&&this.hasAttribute('download'))}}", "arguments": [], "returnByValue": True})
        contract = inspected.get("result", {}).get("result", {}).get("value", inspected.get("result", {}).get("value", {}))
        return not inspected.get("exceptionDetails") and isinstance(contract, dict) and str(contract.get("type", "")).lower() not in {"file", "hidden", "password"} and not contract.get("download")

    @staticmethod
    def _perform_action(session: WebSession, object_id: str, action: str, value: str | None) -> None:
        inspected = session.driver.execute_cdp_cmd("Runtime.callFunctionOn", {"objectId": object_id, "functionDeclaration": "function(){return {tag:this.tagName||'',type:(this.type||'').toLowerCase(),disabled:Boolean(this.disabled),readOnly:Boolean(this.readOnly),download:Boolean(this.hasAttribute&&this.hasAttribute('download'))}}", "arguments": [], "returnByValue": True})
        contract = inspected.get("result", {}).get("result", {}).get("value", inspected.get("result", {}).get("value", {}))
        if inspected.get("exceptionDetails") or not isinstance(contract, dict) or contract.get("disabled"):
            raise AdapterCallError("invalid_web_element")
        if str(contract.get("type", "")).lower() in {"file", "hidden", "password"} or contract.get("download"):
            raise AdapterCallError("sensitive_web_field")
        if action == "click":
            model = session.driver.execute_cdp_cmd("DOM.getBoxModel", {"objectId": object_id}).get("model", {})
            quad = model.get("content") or model.get("border")
            if not isinstance(quad, list) or len(quad) != 8:
                raise AdapterCallError("invalid_web_element")
            x = sum(float(quad[index]) for index in (0,2,4,6))/4;y = sum(float(quad[index]) for index in (1,3,5,7))/4
            session.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type":"mousePressed","x":x,"y":y,"button":"left","clickCount":1})
            session.driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type":"mouseReleased","x":x,"y":y,"button":"left","clickCount":1})
            return
        declarations = {
            "fill": "function(v){const t=(this.type||'').toLowerCase();if(this.tagName!=='INPUT'&&this.tagName!=='TEXTAREA')throw new Error('invalid_element');if(this.readOnly||['password','hidden','file'].includes(t))throw new Error('sensitive_field');this.focus();this.value=v;this.dispatchEvent(new Event('input',{bubbles:true}));this.dispatchEvent(new Event('change',{bubbles:true}));return true}",
            "select": "function(v){if(this.tagName!=='SELECT'||this.disabled||![...this.options].some(o=>o.value===v))throw new Error('invalid_selection');this.value=v;this.dispatchEvent(new Event('input',{bubbles:true}));this.dispatchEvent(new Event('change',{bubbles:true}));return true}",
        }
        if action == "press" and value in PRESS_KEYS:
            focused = session.driver.execute_cdp_cmd("Runtime.callFunctionOn", {"objectId": object_id, "functionDeclaration": "function(){this.focus();return true}", "arguments": [], "returnByValue": True})
            if focused.get("exceptionDetails"):
                raise AdapterCallError("invalid_web_element")
            key = " " if value == "Space" else value
            session.driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": key})
            session.driver.execute_cdp_cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": key})
            return
        if action not in declarations:
            raise AdapterCallError("invalid_web_action")
        arguments = [] if action == "click" else [{"value": value or ""}]
        result = session.driver.execute_cdp_cmd("Runtime.callFunctionOn", {"objectId": object_id, "functionDeclaration": declarations[action], "arguments": arguments, "awaitPromise": True, "returnByValue": True})
        if result.get("exceptionDetails"):
            description = str(result.get("exceptionDetails", {}).get("exception", {}).get("description", ""))
            if "sensitive_field" in description:
                raise AdapterCallError("sensitive_web_field")
            raise AdapterCallError("invalid_web_element")

    @staticmethod
    def _redact(value: str, secrets_: tuple[str, ...]) -> str:
        for secret in secrets_:
            value = value.replace(secret, "[REDACTED]")
        return value

    @staticmethod
    def _node_state(node: dict[str, Any]) -> dict[str, bool | str]:
        admitted = {"checked", "disabled", "expanded", "focused", "multiselectable", "pressed", "readonly", "required", "selected"}
        result: dict[str, bool | str] = {}
        for item in node.get("properties", []):
            name = item.get("name")
            value = item.get("value", {}).get("value")
            if name in admitted and isinstance(value, (bool, str)):
                result[str(name)] = value
        return result

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
