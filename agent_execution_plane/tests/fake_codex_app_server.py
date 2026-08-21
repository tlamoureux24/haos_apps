from __future__ import annotations

import json
import os
import sys
from pathlib import Path

connected = os.environ.get("AEP_FAKE_CONNECTED") == "1"
observation = Path(os.environ["AEP_FAKE_OBSERVATION"])
execution = os.environ.get("AEP_FAKE_EXECUTION") == "1"
models = [item for item in os.environ.get("AEP_FAKE_MODELS", "gpt-test").split(",") if item]

if stderr_text := os.environ.get("AEP_FAKE_STDERR"):
    sys.stderr.write(stderr_text + "\n")
    sys.stderr.write("x" * 131072 + "\n")
    sys.stderr.flush()


def send(value):
    sys.stdout.write(json.dumps(value) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "initialized":
        continue
    with observation.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"method": method, "params": message.get("params"), "codex_home": os.environ.get("CODEX_HOME"), "forbidden_env": sorted(name for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN") if name in os.environ)}) + "\n")
    request_id = message.get("id")
    if method == "initialize":
        result = {"userAgent": "codex/0.144.4 fake", "codexHome": os.environ.get("CODEX_HOME"), "platformFamily": "unix", "platformOs": "linux"}
    elif method == "account/read":
        result = {"account": {"type": "chatgpt", "email": "must-not-leak@example.invalid", "planType": "plus"} if connected else None, "requiresOpenaiAuth": not connected}
    elif method == "account/login/start" and message.get("params", {}).get("type") == "chatgptDeviceCode":
        result = {"type": "chatgptDeviceCode", "loginId": "login-1", "verificationUrl": "https://example.invalid/device", "userCode": "ABCD-EFGH"}
    elif method == "account/login/cancel":
        result = {"status": "cancelled"}
    elif method == "account/logout":
        connected = False
        result = {}
    elif method == "model/list":
        result = {"data": [{"model": model, "displayName": "GPT Test" if model == "gpt-test" else model} for model in models], "nextCursor": None}
    elif execution and method == "thread/start":
        result = {"thread": {"id": "thread-1"}}
    elif execution and method == "turn/start":
        send({"id": request_id, "result": {"turn": {"id": "turn-1"}}})
        send({"id": "denied-1", "method": "item/commandExecution/requestApproval", "params": {"command": "forbidden"}})
        denied = json.loads(sys.stdin.readline())
        with observation.open("a", encoding="utf-8") as stream: stream.write(json.dumps({"method": "observed_denial", "response": denied}) + "\n")
        send({"id": "tool-1", "method": "item/tool/call", "params": {"threadId": "thread-1", "turnId": "turn-1", "callId": "call-1", "tool": "source_tool", "arguments": {"value": 4}}})
        routed = json.loads(sys.stdin.readline())
        with observation.open("a", encoding="utf-8") as stream: stream.write(json.dumps({"method": "observed_dynamic_result", "response": routed}) + "\n")
        send({"method": "item/completed", "params": {"item": {"type": "agentMessage", "text": "done"}}})
        send({"method": "turn/completed", "params": {"turn": {"id": "turn-1", "status": "completed"}}})
        continue
    else:
        send({"id": request_id, "error": {"code": -32601, "message": "unsupported"}})
        continue
    send({"id": request_id, "result": result})
