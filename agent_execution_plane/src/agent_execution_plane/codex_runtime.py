"""Strict Lot 1 account/catalogue client for the pinned Codex app-server."""

from __future__ import annotations

import importlib.metadata
import json
import logging
import os
import re
import selectors
import subprocess
import threading
import asyncio
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from agent_execution_plane.execution import ProviderReply, ToolCall

CODEX_VERSION = "0.144.4"
FORBIDDEN_AUTH_ENV = {"OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"}
REQUEST_TIMEOUT_SECONDS = 15.0
CODEX_DIAG_PREFIX = "AEP_CODEX_DIAG"
CODEX_STDERR_LINE_LIMIT = 512
CODEX_STDERR_TOTAL_LIMIT = 8192
LOGGER = logging.getLogger("uvicorn.error")
ALLOWED_METHODS = {
    "account/login/start",
    "account/login/cancel",
    "account/read",
    "account/logout",
    "model/list",
}

CONFIG = '''forced_login_method = "chatgpt"
cli_auth_credentials_store = "file"
web_search = "live"

[features]
plugins = false
apps = false
connectors = false
image_generation = false
collab = false
multi_agent = false
shell_tool = false
unified_exec = false
apply_patch_freeform = false
'''


class CodexRuntimeError(RuntimeError):
    """Bounded runtime/protocol failure with no upstream payload attached."""


def _safe_label(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_./:-]", "_", str(value))[:120]


def _sanitize_codex_stderr(value: str) -> str:
    """Bound one stderr line and remove likely secrets, URLs, and payloads."""
    text = value.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"https?://\S+", "[REDACTED_URL]", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)\b(authorization|token|credential|secret|api[_-]?key)\b\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"([\[{]).*?([\]}])", r"\1REDACTED_PAYLOAD\2", text)
    text = re.sub(r"([\"']).{8,}?\1", r"\1REDACTED\1", text)
    text = re.sub(r"\b[A-Za-z0-9_+/=-]{32,}\b", "[REDACTED_OPAQUE]", text)
    return text[:CODEX_STDERR_LINE_LIMIT]


def ensure_codex_home(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    config_path = path / "config.toml"
    if config_path.exists() and config_path.read_text(encoding="utf-8") == CONFIG:
        os.chmod(config_path, 0o600)
        return
    temporary = path / f".config.{uuid4().hex}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(CONFIG)
        os.replace(temporary, config_path)
        os.chmod(config_path, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()


def child_environment(codex_home: Path, source: dict[str, str] | None = None) -> dict[str, str]:
    environment = dict(source if source is not None else os.environ)
    for name in FORBIDDEN_AUTH_ENV:
        environment.pop(name, None)
    environment["CODEX_HOME"] = str(codex_home)
    return environment


def bundled_codex() -> str:
    if importlib.metadata.version("openai-codex") != CODEX_VERSION or importlib.metadata.version("openai-codex-cli-bin") != CODEX_VERSION:
        raise CodexRuntimeError("runtime_or_model_incompatible")
    from codex_cli_bin import bundled_codex_path
    return str(bundled_codex_path())


class CodexRuntime:
    """Own one local stdio process and expose no thread/turn operation."""

    def __init__(self, codex_home: Path, *, command: tuple[str, ...] | None = None, environment: dict[str, str] | None = None):
        self.codex_home = codex_home
        self.command = command
        self.environment = environment
        self._process: subprocess.Popen[str] | None = None
        self._stderr_thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._pending_login: dict[str, str] | None = None

    def _start(self) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        ensure_codex_home(self.codex_home)
        command = list(self.command or (bundled_codex(), "app-server", "--listen", "stdio://"))
        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                cwd=self.codex_home,
                env=child_environment(self.codex_home, self.environment),
                bufsize=1,
            )
            LOGGER.debug("%s subprocess_start mode=account", CODEX_DIAG_PREFIX)
            self._stderr_thread = threading.Thread(target=self._drain_stderr, args=(self._process,), daemon=True, name="aep-codex-stderr")
            self._stderr_thread.start()
            result = self._exchange("initialize", {"clientInfo": {"name": "agent_execution_plane", "title": "Agent Execution Plane", "version": "0.3.0"}, "capabilities": {"experimentalApi": False}}, allow_initialize=True)
            if CODEX_VERSION not in str(result.get("userAgent", "")):
                raise CodexRuntimeError("runtime_or_model_incompatible")
            self._write({"method": "initialized"})
        except (OSError, ValueError, CodexRuntimeError):
            self._close_unlocked()
            raise CodexRuntimeError("runtime_or_model_incompatible") from None

    def _write(self, message: dict[str, object]) -> None:
        if self._process is None or self._process.stdin is None:
            raise CodexRuntimeError("runtime_or_model_incompatible")
        self._process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self._process.stdin.flush()

    @staticmethod
    def _drain_stderr(process: subprocess.Popen[str]) -> None:
        if process.stderr is None:
            return
        consumed = 0
        while chunk := process.stderr.read(4096):
            if consumed < CODEX_STDERR_TOTAL_LIMIT:
                safe = _sanitize_codex_stderr(chunk)
                consumed += len(safe)
                if safe:
                    LOGGER.debug("%s stderr text=%s", CODEX_DIAG_PREFIX, safe)

    def _read(self) -> dict[str, object]:
        if self._process is None or self._process.stdout is None:
            raise CodexRuntimeError("runtime_or_model_incompatible")
        with selectors.DefaultSelector() as selector:
            selector.register(self._process.stdout, selectors.EVENT_READ)
            if not selector.select(REQUEST_TIMEOUT_SECONDS):
                raise CodexRuntimeError("runtime_or_model_incompatible")
        line = self._process.stdout.readline()
        if not line:
            raise CodexRuntimeError("runtime_or_model_incompatible")
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            raise CodexRuntimeError("runtime_or_model_incompatible") from None
        if not isinstance(message, dict):
            raise CodexRuntimeError("runtime_or_model_incompatible")
        return message

    def _observe(self, message: dict[str, object]) -> None:
        if message.get("method") == "account/login/completed":
            params = message.get("params")
            if isinstance(params, dict) and self._pending_login and params.get("loginId") == self._pending_login.get("login_id") and not params.get("success"):
                self._pending_login = {"status": "error", "code": "login_failed"}

    def _exchange(self, method: str, params: dict[str, object] | None = None, *, allow_initialize: bool = False) -> dict[str, object]:
        if not allow_initialize and method not in ALLOWED_METHODS:
            raise CodexRuntimeError("runtime_or_model_incompatible")
        request_id = uuid4().hex
        message: dict[str, object] = {"id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self._write(message)
        while True:
            response = self._read()
            self._observe(response)
            if response.get("id") != request_id:
                continue
            if "error" in response or not isinstance(response.get("result"), dict):
                raise CodexRuntimeError("runtime_or_model_incompatible")
            return response["result"]

    def request(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        with self._lock:
            self._start()
            try:
                return self._exchange(method, params)
            except (OSError, CodexRuntimeError):
                self._close_unlocked()
                raise CodexRuntimeError("runtime_or_model_incompatible") from None

    def smoke(self) -> None:
        with self._lock:
            self._start()

    def account(self) -> dict[str, object]:
        result = self.request("account/read", {"refreshToken": False})
        account = result.get("account")
        if not isinstance(account, dict) or account.get("type") != "chatgpt":
            return {"status": "disconnected"}
        self._pending_login = None
        return {"status": "connected", "plan_type": account.get("planType") if isinstance(account.get("planType"), str) else None}

    def login_start(self) -> dict[str, object]:
        result = self.request("account/login/start", {"type": "chatgptDeviceCode"})
        if result.get("type") != "chatgptDeviceCode" or not all(isinstance(result.get(key), str) for key in ("loginId", "verificationUrl", "userCode")):
            raise CodexRuntimeError("runtime_or_model_incompatible")
        verification = urlparse(result["verificationUrl"])
        if verification.scheme != "https" or not verification.netloc:
            raise CodexRuntimeError("runtime_or_model_incompatible")
        self._pending_login = {"status": "pending", "login_id": result["loginId"], "verification_url": result["verificationUrl"], "user_code": result["userCode"]}
        return dict(self._pending_login)

    def login_status(self) -> dict[str, object]:
        account = self.account()
        return account if account["status"] == "connected" or self._pending_login is None else dict(self._pending_login)

    def login_cancel(self) -> None:
        if self._pending_login and self._pending_login.get("login_id"):
            self.request("account/login/cancel", {"loginId": self._pending_login["login_id"]})
        self._pending_login = None

    def logout(self) -> None:
        self.request("account/logout")
        self._pending_login = None

    def models(self) -> list[dict[str, str]]:
        if self.account()["status"] != "connected":
            raise CodexRuntimeError("auth_required")
        result = self.request("model/list", {"includeHidden": False})
        data = result.get("data")
        if not isinstance(data, list):
            raise CodexRuntimeError("runtime_or_model_incompatible")
        return [{"id": item["model"], "display_name": item.get("displayName", item["model"])} for item in data if isinstance(item, dict) and isinstance(item.get("model"), str)]

    def validate_model(self, model: str) -> None:
        if not any(item["id"] == model for item in self.models()):
            raise CodexRuntimeError("runtime_or_model_incompatible")

    def close(self) -> None:
        with self._lock:
            self._close_unlocked()

    def _close_unlocked(self) -> None:
        process, self._process = self._process, None
        stderr_thread, self._stderr_thread = self._stderr_thread, None
        if process is None:
            return
        if process.stdin:
            process.stdin.close()
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
        if process.stdout:
            process.stdout.close()
        if stderr_thread:
            stderr_thread.join(timeout=2)
        if process.stderr:
            process.stderr.close()

    async def execute_turn(self, model: str, messages: list[dict[str, object]], tools, result_schema, timeout: float, dispatch, *, model_provider: str | None = None):
        """Run one ephemeral, unattended execution with only AEP dynamic calls handled."""
        ensure_codex_home(self.codex_home)
        process = await asyncio.create_subprocess_exec(
            *(self.command or (bundled_codex(), "app-server", "--listen", "stdio://")),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            cwd=self.codex_home, env=child_environment(self.codex_home,self.environment),
        )
        LOGGER.debug("%s subprocess_start mode=turn", CODEX_DIAG_PREFIX)
        pending: dict[str, asyncio.Future] = {}
        final_content = None
        turn_outcome = "failure"
        async def drain_stderr():
            consumed=0
            while True:
                chunk=await process.stderr.read(4096)
                if not chunk:return
                if consumed>=CODEX_STDERR_TOTAL_LIMIT:continue
                safe=_sanitize_codex_stderr(chunk.decode('utf-8',errors='replace'));consumed+=len(safe)
                if safe:LOGGER.debug("%s stderr text=%s",CODEX_DIAG_PREFIX,safe)
        stderr_task=asyncio.create_task(drain_stderr(),name='aep-codex-stderr')
        async def write(value):
            process.stdin.write((json.dumps(value,separators=(",",":"))+"\n").encode()); await process.stdin.drain()
        async def request(method,params):
            request_id=uuid4().hex; future=asyncio.get_running_loop().create_future(); pending[request_id]=future
            await write({'id':request_id,'method':method,'params':params}); return await future
        async def run():
            nonlocal final_content,turn_outcome
            initialize=asyncio.create_task(request('initialize',{'clientInfo':{'name':'agent_execution_plane_execution','title':'Agent Execution Plane','version':'0.6.6'},'capabilities':{'experimentalApi':True}}))
            while not initialize.done(): await consume_one(); await asyncio.sleep(0)
            result=await initialize
            if CODEX_VERSION not in str(result.get('userAgent','')): raise CodexRuntimeError('runtime_or_model_incompatible')
            await write({'method':'initialized'})
            dynamic=[{'type':'function','name':t.name,'description':t.description,'inputSchema':t.input_schema,'deferLoading':False} for t in tools]
            LOGGER.debug("%s dynamic_tools count=%d names=%s",CODEX_DIAG_PREFIX,len(dynamic),','.join(_safe_label(t.name) for t in tools) or '-')
            thread_params={'model':model,'ephemeral':True,'cwd':str(self.codex_home),'approvalPolicy':'never','approvalsReviewer':'user','baseInstructions':'','developerInstructions':'','environments':[],'instructionSources':[],'dynamicTools':dynamic}
            if model_provider is not None: thread_params['modelProvider']=model_provider
            thread_task=asyncio.create_task(request('thread/start',thread_params))
            while not thread_task.done(): await consume_one(); await asyncio.sleep(0)
            thread=(await thread_task)['thread']; thread_id=thread['id']
            text=json.dumps(messages,ensure_ascii=False,sort_keys=True,separators=(',',':'))
            params={'threadId':thread_id,'input':[{'type':'text','text':text,'text_elements':[]}]}
            if result_schema is not None: params['outputSchema']=result_schema
            turn_task=asyncio.create_task(request('turn/start',params))
            while not turn_task.done(): await consume_one(); await asyncio.sleep(0)
            turn_id=(await turn_task)['turn']['id']
            while True:
                message=await consume_one()
                if message.get('method')=='turn/completed' and message.get('params',{}).get('turn',{}).get('id')==turn_id:
                    turn=message['params']['turn']
                    if turn.get('status')!='completed': raise CodexRuntimeError('provider_failure')
                    turn_outcome='success'
                    return ProviderReply(final_content)
        async def consume_one():
            nonlocal final_content
            line=await process.stdout.readline()
            if not line: raise CodexRuntimeError('provider_failure')
            try: message=json.loads(line)
            except json.JSONDecodeError: raise CodexRuntimeError('provider_failure') from None
            if 'id' in message and ('result' in message or 'error' in message):
                future=pending.pop(str(message['id']),None)
                if future:
                    if 'error' in message: future.set_exception(CodexRuntimeError('provider_failure'))
                    else: future.set_result(message['result'])
                return message
            method=message.get('method'); params=message.get('params',{})
            if isinstance(method,str):LOGGER.debug("%s rpc_received method=%s",CODEX_DIAG_PREFIX,_safe_label(method))
            if 'id' in message:
                if method=='item/tool/call' and isinstance(params,dict) and any(t.name==params.get('tool') for t in tools):
                    LOGGER.debug("%s tool_call_received name=%s",CODEX_DIAG_PREFIX,_safe_label(params.get('tool')))
                    call=ToolCall(str(params.get('callId','')),str(params['tool']),params.get('arguments'))
                    try:
                        LOGGER.debug("%s dispatch_start name=%s",CODEX_DIAG_PREFIX,_safe_label(call.name))
                        output=await dispatch(call); response={'contentItems':[{'type':'inputText','text':json.dumps(output,ensure_ascii=False,separators=(',',':'))}],'success':True}
                        LOGGER.debug("%s dispatch_success name=%s",CODEX_DIAG_PREFIX,_safe_label(call.name))
                    except Exception as exc:
                        LOGGER.debug("%s dispatch_failure name=%s error_type=%s",CODEX_DIAG_PREFIX,_safe_label(call.name),_safe_label(type(exc).__name__))
                        response={'contentItems':[{'type':'inputText','text':'technical_failure'}],'success':False}
                        await write({'id':message['id'],'result':response})
                        raise
                    await write({'id':message['id'],'result':response})
                else:
                    LOGGER.debug("%s server_request_denied method=%s",CODEX_DIAG_PREFIX,_safe_label(method))
                    await write({'id':message['id'],'error':{'code':-32000,'message':'unattended_request_denied'}})
                return message
            if method=='item/completed':
                item=params.get('item',{}) if isinstance(params,dict) else {}
                if item.get('type')=='agentMessage': final_content=item.get('text') or item.get('content')
            return message
        try:
            return await asyncio.wait_for(run(),timeout=timeout)
        except asyncio.TimeoutError: raise CodexRuntimeError('attempt_timeout') from None
        finally:
            if process.stdin: process.stdin.close()
            if process.returncode is None:
                process.terminate()
                try: await asyncio.wait_for(process.wait(),2)
                except asyncio.TimeoutError: process.kill(); await process.wait()
            try:await asyncio.wait_for(stderr_task,2)
            except asyncio.TimeoutError:
                stderr_task.cancel();await asyncio.gather(stderr_task,return_exceptions=True)
            LOGGER.debug("%s turn_end outcome=%s exit_code=%s",CODEX_DIAG_PREFIX,turn_outcome,process.returncode)
