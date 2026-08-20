from __future__ import annotations

import json
import os
import sys
from pathlib import Path

connected = os.environ.get("AEP_FAKE_CONNECTED") == "1"
observation = Path(os.environ["AEP_FAKE_OBSERVATION"])


def send(value):
    sys.stdout.write(json.dumps(value) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    message = json.loads(line)
    method = message.get("method")
    if method == "initialized":
        continue
    with observation.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"method": method, "codex_home": os.environ.get("CODEX_HOME"), "forbidden_env": sorted(name for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN") if name in os.environ)}) + "\n")
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
        result = {"data": [{"model": "gpt-test", "displayName": "GPT Test"}], "nextCursor": None}
    else:
        send({"id": request_id, "error": {"code": -32601, "message": "unsupported"}})
        continue
    send({"id": request_id, "result": result})
