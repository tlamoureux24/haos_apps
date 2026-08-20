"""Configured-model persistence and validate-before-save lifecycle."""

from __future__ import annotations

import sqlite3
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from agent_execution_plane.codex_runtime import CodexRuntime
from agent_execution_plane.database import connect, now_iso, record_activity
from agent_execution_plane.providers import ProviderCheck, check
from agent_execution_plane.security import decrypt, encrypt, load_or_create_key

FAMILIES = {"ollama_compatible", "openai_compatible", "openai_chatgpt_oauth"}


@dataclass(frozen=True)
class Candidate:
    display_name: str
    provider_family: str
    base_url: str | None
    provider_model: str
    credential: str | None
    replace_credential: bool
    enabled: bool
    timeout_minutes: float


class ModelStore:
    def __init__(self, database: Path, private_dir: Path, codex_runtime: CodexRuntime | None = None):
        self.database = database
        self.key = load_or_create_key(private_dir / "provider-key")
        self.codex_runtime = codex_runtime

    def _validate_fields(self, candidate: Candidate) -> Candidate:
        if not candidate.display_name.strip() or len(candidate.display_name) > 120: raise ValueError("invalid_name")
        if candidate.provider_family not in FAMILIES: raise ValueError("invalid_provider_family")
        if candidate.provider_family == "openai_chatgpt_oauth":
            if candidate.base_url or candidate.credential: raise ValueError("oauth_fields_forbidden")
        else:
            parsed = urlparse(candidate.base_url or "")
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password: raise ValueError("invalid_base_url")
        if not candidate.provider_model.strip() or len(candidate.provider_model) > 200: raise ValueError("invalid_provider_model")
        if not math.isfinite(candidate.timeout_minutes) or candidate.timeout_minutes <= 0: raise ValueError("invalid_timeout")
        return candidate

    def _public(self, row: sqlite3.Row) -> dict[str, object]:
        return {"id": row["id"], "display_name": row["display_name"], "provider_family": row["provider_family"], "base_url": row["base_url"], "provider_model": row["provider_model"], "credential_configured": row["encrypted_credential"] is not None, "enabled": bool(row["enabled"]), "priority": row["priority"], "timeout_minutes": row["timeout_minutes"], "technical_state": "disabled" if not row["enabled"] else row["technical_state"], "provider_state": row["technical_state"], "diagnostic_code": row["diagnostic_code"], "checked_at": row["checked_at"], "in_use": False}

    def list(self) -> list[dict[str, object]]:
        with connect(self.database) as db:
            rows = db.execute("SELECT * FROM models ORDER BY priority").fetchall()
        return [self._public(row) for row in rows]

    def _row(self, model_id: str) -> sqlite3.Row | None:
        with connect(self.database) as db: return db.execute("SELECT * FROM models WHERE id=?", (model_id,)).fetchone()

    def save(self, candidate: Candidate, model_id: str | None = None) -> tuple[dict[str, object] | None, ProviderCheck]:
        candidate = self._validate_fields(candidate)
        previous = self._row(model_id) if model_id else None
        if model_id and previous is None: raise KeyError("model_not_found")
        credential = None if candidate.provider_family == "openai_chatgpt_oauth" else candidate.credential if candidate.replace_credential else (decrypt(self.key, previous["encrypted_credential"]) if previous else candidate.credential)
        result = check(candidate.provider_family, candidate.base_url, candidate.provider_model, credential, explicit=True, codex_runtime=self.codex_runtime)
        if result.state != "available": return None, result
        encrypted = encrypt(self.key, credential) if credential else None
        timestamp = now_iso()
        with connect(self.database) as db:
            if previous:
                db.execute("UPDATE models SET display_name=?,provider_family=?,base_url=?,provider_model=?,encrypted_credential=?,enabled=?,timeout_minutes=?,technical_state=?,diagnostic_code=?,checked_at=?,updated_at=? WHERE id=?", (candidate.display_name.strip(), candidate.provider_family, candidate.base_url.rstrip('/') if candidate.base_url else None, candidate.provider_model.strip(), encrypted, int(candidate.enabled), candidate.timeout_minutes, result.state, result.code, timestamp, timestamp, model_id))
            else:
                model_id = str(uuid4())
                priority = db.execute("SELECT coalesce(max(priority),0)+1 FROM models").fetchone()[0]
                db.execute("INSERT INTO models VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (model_id, candidate.display_name.strip(), candidate.provider_family, candidate.base_url.rstrip('/') if candidate.base_url else None, candidate.provider_model.strip(), encrypted, int(candidate.enabled), priority, candidate.timeout_minutes, result.state, result.code, timestamp, timestamp, timestamp))
        record_activity(self.database, "model_updated" if previous else "model_created", "configuration", "success")
        if previous and candidate.replace_credential and candidate.provider_family != "openai_chatgpt_oauth":
            record_activity(self.database, "model_credential_replaced", "configuration", "success")
        return self._public(self._row(model_id)), result

    def delete(self, model_id: str) -> bool:
        with connect(self.database) as db:
            found = db.execute("DELETE FROM models WHERE id=?", (model_id,)).rowcount
            if found:
                rows = db.execute("SELECT id FROM models ORDER BY priority").fetchall()
                for priority, row in enumerate(rows, 1): db.execute("UPDATE models SET priority=? WHERE id=?", (priority, row["id"]))
        if found: record_activity(self.database, "model_deleted", "configuration", "success")
        return bool(found)

    def set_enabled(self, model_id: str, enabled: bool) -> bool:
        with connect(self.database) as db: found = db.execute("UPDATE models SET enabled=?,updated_at=? WHERE id=?", (int(enabled), now_iso(), model_id)).rowcount
        if found: record_activity(self.database, "model_enabled" if enabled else "model_disabled", "configuration", "success")
        return bool(found)

    def reorder(self, ordered_ids: list[str]) -> None:
        with connect(self.database) as db:
            current = [row[0] for row in db.execute("SELECT id FROM models ORDER BY priority")]
            if len(ordered_ids) != len(set(ordered_ids)) or set(ordered_ids) != set(current): raise ValueError("invalid_order")
            offset = len(current) + 1
            db.execute("UPDATE models SET priority=priority+?", (offset,))
            for priority, model_id in enumerate(ordered_ids, 1): db.execute("UPDATE models SET priority=?,updated_at=? WHERE id=?", (priority, now_iso(), model_id))
        record_activity(self.database, "models_reordered", "configuration", "success")

    def refresh_health(self) -> None:
        with connect(self.database) as db: rows = db.execute("SELECT * FROM models ORDER BY priority").fetchall()
        for row in rows:
            credential = decrypt(self.key, row["encrypted_credential"])
            result = check(row["provider_family"], row["base_url"], row["provider_model"], credential, explicit=False, codex_runtime=self.codex_runtime)
            with connect(self.database) as db: db.execute("UPDATE models SET technical_state=?,diagnostic_code=?,checked_at=? WHERE id=?", (result.state, result.code, now_iso(), row["id"]))
