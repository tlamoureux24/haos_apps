"""Durable namespace, target and publication state."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp_capability_bridge.contracts import AdapterRegistry, Capability
from mcp_capability_bridge.database import connect
from mcp_capability_bridge.security import IssuedCredential, SecretBox, issue_credential, token_lookup, verify_token

KEY = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


def generated_key(display_name: str, existing: set[str], fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", display_name).encode("ascii", "ignore").decode("ascii").lower()
    base = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if not base or not base[0].isalpha():
        base = fallback
    if len(base) == 1:
        base += "_"
    base = base[:32] or fallback
    candidate = base
    suffix = 2
    while candidate in existing:
        marker = f"_{suffix}"
        candidate = f"{base[:32 - len(marker)].rstrip('_')}{marker}"
        suffix += 1
    return candidate


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class NamespaceContext:
    namespace_id: str
    key: str
    credential_generation: int
    inventory_revision: int


@dataclass(frozen=True)
class PublishedCapability:
    namespace_id: str
    target_id: str
    target_key: str
    adapter_type: str
    configuration: dict[str, Any]
    encrypted_secret: bytes | None
    capability: Capability


class NamespaceStore:
    def __init__(self, database_path: Path, pepper: bytes, secret_box: SecretBox, registry: AdapterRegistry):
        self.database_path = database_path
        self.pepper = pepper
        self.secret_box = secret_box
        self.registry = registry

    def create_namespace(self, key: str, display_name: str) -> tuple[dict[str, object], IssuedCredential]:
        key = key.strip()
        display_name = display_name.strip()
        if not 1 <= len(display_name) <= 100:
            raise ValueError("invalid_namespace")
        namespace_id = uuid.uuid4().hex
        credential = issue_credential(namespace_id, self.pepper)
        timestamp = now_iso()
        try:
            with connect(self.database_path) as database:
                if not key:
                    existing = {row[0] for row in database.execute("SELECT key FROM namespaces")}
                    key = generated_key(display_name, existing, "client")
                if not KEY.fullmatch(key):
                    raise ValueError("invalid_namespace")
                database.execute(
                    "INSERT INTO namespaces(id,key,display_name,status,credential_id,credential_verifier,credential_generation,inventory_revision,created_at,updated_at) VALUES(?,?,?,'active',?,?,1,1,?,?)",
                    (namespace_id, key, display_name, credential.credential_id, credential.verifier, timestamp, timestamp),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError("namespace_key_exists") from exc
        return self.get_namespace(namespace_id), credential

    def get_namespace(self, namespace_id: str) -> dict[str, object]:
        with connect(self.database_path) as database:
            row = database.execute(
                "SELECT id,key,display_name,status,credential_generation,inventory_revision,created_at,updated_at,revoked_at,archived_at FROM namespaces WHERE id=?",
                (namespace_id,),
            ).fetchone()
        if row is None:
            raise KeyError("namespace_not_found")
        return dict(row)

    def list_namespaces(self, include_archived: bool = False) -> list[dict[str, object]]:
        where = "" if include_archived else "WHERE status != 'archived'"
        with connect(self.database_path) as database:
            rows = database.execute(
                f"SELECT id,key,display_name,status,credential_generation,inventory_revision,created_at,updated_at,revoked_at,archived_at FROM namespaces {where} ORDER BY created_at,id"
            ).fetchall()
        return [dict(row) for row in rows]

    def authenticate(self, token: str) -> NamespaceContext:
        lookup = token_lookup(token)
        if lookup is None:
            raise PermissionError("invalid_credential")
        namespace_id, credential_id = lookup
        with connect(self.database_path) as database:
            row = database.execute(
                "SELECT id,key,status,credential_id,credential_verifier,credential_generation,inventory_revision FROM namespaces WHERE credential_id=?",
                (credential_id,),
            ).fetchone()
        if row is None or row["id"] != namespace_id or row["status"] != "active" or not verify_token(token, self.pepper, row["credential_verifier"]):
            raise PermissionError("invalid_credential")
        return NamespaceContext(row["id"], row["key"], row["credential_generation"], row["inventory_revision"])

    def rotate(self, namespace_id: str) -> IssuedCredential:
        timestamp = now_iso()
        with connect(self.database_path) as database:
            row = database.execute("SELECT status FROM namespaces WHERE id=?", (namespace_id,)).fetchone()
            if row is None:
                raise KeyError("namespace_not_found")
            if row["status"] != "active":
                raise ValueError("namespace_not_active")
            credential = issue_credential(namespace_id, self.pepper)
            database.execute(
                "UPDATE namespaces SET credential_id=?,credential_verifier=?,credential_generation=credential_generation+1,updated_at=? WHERE id=?",
                (credential.credential_id, credential.verifier, timestamp, namespace_id),
            )
        return credential

    def revoke(self, namespace_id: str) -> bool:
        timestamp = now_iso()
        with connect(self.database_path) as database:
            row = database.execute("SELECT status FROM namespaces WHERE id=?", (namespace_id,)).fetchone()
            if row is None:
                raise KeyError("namespace_not_found")
            if row["status"] == "archived":
                raise ValueError("namespace_archived")
            if row["status"] == "revoked":
                return False
            database.execute(
                "UPDATE namespaces SET status='revoked',credential_generation=credential_generation+1,revoked_at=?,updated_at=? WHERE id=?",
                (timestamp, timestamp, namespace_id),
            )
        return True

    def archive(self, namespace_id: str) -> None:
        timestamp = now_iso()
        with connect(self.database_path) as database:
            row = database.execute("SELECT status FROM namespaces WHERE id=?", (namespace_id,)).fetchone()
            if row is None:
                raise KeyError("namespace_not_found")
            if row["status"] != "revoked":
                raise ValueError("namespace_must_be_revoked")
            database.execute(
                "UPDATE namespaces SET status='archived',archived_at=?,updated_at=? WHERE id=?",
                (timestamp, timestamp, namespace_id),
            )

    def create_target(self, key: str, display_name: str, adapter_type: str, configuration: dict[str, Any], secret: bytes | None = None) -> dict[str, object]:
        key = key.strip()
        if not 1 <= len(display_name.strip()) <= 100:
            raise ValueError("invalid_target")
        adapter = self.registry.get(adapter_type)
        adapter.validate_target(configuration, secret)
        capabilities = adapter.capabilities(configuration)
        if len({item.capability_id for item in capabilities}) != len(capabilities):
            raise ValueError("duplicate_capability")
        for capability in capabilities:
            capability.validated()
        target_id = uuid.uuid4().hex
        timestamp = now_iso()
        envelope = self.secret_box.encrypt(secret) if secret is not None else None
        encoded = json.dumps(configuration, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        with connect(self.database_path) as database:
            if not key:
                existing = {row[0] for row in database.execute("SELECT key FROM targets")}
                key = generated_key(display_name, existing, "target")
            if not KEY.fullmatch(key):
                raise ValueError("invalid_target")
            database.execute(
                "INSERT INTO targets(id,key,display_name,adapter_type,configuration_json,encrypted_secret,enabled,technical_state,created_at,updated_at) VALUES(?,?,?,?,?,?,1,'valid',?,?)",
                (target_id, key, display_name.strip(), adapter_type, encoded, envelope, timestamp, timestamp),
            )
        return {"id": target_id, "key": key, "display_name": display_name.strip(), "adapter_type": adapter_type, "enabled": True, "technical_state": "valid"}

    def list_targets(self) -> list[dict[str, object]]:
        with connect(self.database_path) as database:
            rows = database.execute("SELECT id,key,display_name,adapter_type,enabled,technical_state,created_at,updated_at FROM targets ORDER BY created_at,id").fetchall()
        result = []
        for row in rows:
            item = {**dict(row), "enabled": bool(row["enabled"])}
            item["capabilities"] = self.list_target_capabilities(row["id"])
            result.append(item)
        return result

    def get_target(self, target_id: str) -> dict[str, object]:
        with connect(self.database_path) as database:
            row = database.execute("SELECT id,key,display_name,adapter_type,enabled,technical_state,configuration_json,created_at,updated_at FROM targets WHERE id=?", (target_id,)).fetchone()
        if row is None:
            raise KeyError("target_not_found")
        result = dict(row)
        configuration = json.loads(result.pop("configuration_json"))
        configuration.pop("host_public_key", None)
        result["configuration"] = configuration
        result["enabled"] = bool(result["enabled"])
        return result

    def get_target_configuration(self, target_id: str) -> dict[str, Any]:
        with connect(self.database_path) as database:
            row = database.execute("SELECT configuration_json FROM targets WHERE id=?", (target_id,)).fetchone()
        if row is None:
            raise KeyError("target_not_found")
        return json.loads(row["configuration_json"])

    def get_target_secret(self, target_id: str) -> bytes | None:
        with connect(self.database_path) as database:
            row=database.execute("SELECT encrypted_secret FROM targets WHERE id=?",(target_id,)).fetchone()
        if row is None:raise KeyError("target_not_found")
        return self.secret_box.decrypt(row["encrypted_secret"]) if row["encrypted_secret"] is not None else None

    def list_target_capabilities(self, target_id: str) -> list[dict[str, object]]:
        with connect(self.database_path) as database:
            row=database.execute("SELECT adapter_type,configuration_json FROM targets WHERE id=?",(target_id,)).fetchone()
        if row is None:raise KeyError("target_not_found")
        configuration=json.loads(row["configuration_json"])
        if row["adapter_type"]=="web":
            target=self.get_target(target_id);adapter=self.registry.get("web")
            capabilities=adapter.capabilities_for_target(configuration,str(target["key"]))
            return [{"id":item.capability_id,"capability_id":item.capability_id,"name":item.name,"display_name":item.name,"description":item.description,"enabled":True,"effect_capable":False} for item in capabilities]
        return [{key: value for key, value in item.items() if key not in {"template"}} | {"template_entries": len(item["template"])} for item in configuration.get("capabilities", [])]

    def update_target(self, target_id: str, display_name: str, configuration: dict[str, Any], secret: bytes | None = None) -> list[str]:
        display_name = display_name.strip()
        if not 1 <= len(display_name) <= 100:
            raise ValueError("invalid_target")
        with connect(self.database_path) as database:
            row = database.execute("SELECT adapter_type,encrypted_secret FROM targets WHERE id=?", (target_id,)).fetchone()
            if row is None:
                raise KeyError("target_not_found")
            envelope = self.secret_box.encrypt(secret) if secret is not None else row["encrypted_secret"]
            clear = secret if secret is not None else (self.secret_box.decrypt(envelope) if envelope is not None else None)
            self.registry.get(row["adapter_type"]).validate_target(configuration, clear)
            encoded = json.dumps(configuration, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            database.execute("UPDATE targets SET display_name=?,configuration_json=?,encrypted_secret=?,technical_state='valid',updated_at=? WHERE id=?", (display_name, encoded, envelope, now_iso(), target_id))
        return self.touch_target_inventory(target_id)

    def set_target_enabled(self, target_id: str, enabled: bool) -> list[str]:
        with connect(self.database_path) as database:
            cursor = database.execute("UPDATE targets SET enabled=?,updated_at=? WHERE id=?", (int(enabled), now_iso(), target_id))
            if cursor.rowcount != 1:
                raise KeyError("target_not_found")
        return self.touch_target_inventory(target_id)

    def delete_target(self, target_id: str) -> list[str]:
        with connect(self.database_path) as database:
            namespaces = [row[0] for row in database.execute("SELECT namespace_id FROM publications WHERE target_id=?", (target_id,)).fetchall()]
            cursor = database.execute("DELETE FROM targets WHERE id=?", (target_id,))
            if cursor.rowcount != 1:
                raise KeyError("target_not_found")
            self._bump_inventory(database, namespaces)
        return namespaces

    def save_capability(self, target_id: str, capability: dict[str, Any]) -> list[str]:
        configuration = self.get_target_configuration(target_id)
        capabilities = configuration.setdefault("capabilities", [])
        existing = next((index for index, item in enumerate(capabilities) if item["id"] == capability["id"]), None)
        if existing is None:
            key = str(capability.get("key", "")).strip()
            if not key:
                key = generated_key(str(capability.get("display_name", "")), {str(item["key"]) for item in capabilities}, "capability")
            capability["key"] = key
            capabilities.append(capability)
        else:
            supplied_key = str(capability.get("key", "")).strip()
            if supplied_key and capabilities[existing]["key"] != supplied_key:
                raise ValueError("capability_key_immutable")
            capability["key"] = capabilities[existing]["key"]
            capabilities[existing] = capability
        with connect(self.database_path) as database:
            row = database.execute("SELECT adapter_type,encrypted_secret FROM targets WHERE id=?", (target_id,)).fetchone()
            if row is None:
                raise KeyError("target_not_found")
            secret = self.secret_box.decrypt(row["encrypted_secret"]) if row["encrypted_secret"] is not None else None
            self.registry.get(row["adapter_type"]).validate_target(configuration, secret)
            database.execute("UPDATE targets SET configuration_json=?,updated_at=? WHERE id=?", (json.dumps(configuration, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False), now_iso(), target_id))
        return self.touch_target_inventory(target_id)

    def delete_capability(self, target_id: str, capability_id: str) -> list[str]:
        configuration = self.get_target_configuration(target_id)
        before = len(configuration.get("capabilities", []))
        configuration["capabilities"] = [item for item in configuration.get("capabilities", []) if item["id"] != capability_id]
        if len(configuration["capabilities"]) == before:
            raise KeyError("capability_not_found")
        with connect(self.database_path) as database:
            namespaces = [row[0] for row in database.execute("SELECT DISTINCT namespace_id FROM publications WHERE target_id=? AND capability_id=?", (target_id, capability_id)).fetchall()]
            database.execute("DELETE FROM publications WHERE target_id=? AND capability_id=?", (target_id, capability_id))
            database.execute("UPDATE targets SET configuration_json=?,updated_at=? WHERE id=?", (json.dumps(configuration, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False), now_iso(), target_id))
            self._bump_inventory(database, namespaces)
        return namespaces

    def touch_target_inventory(self, target_id: str) -> list[str]:
        with connect(self.database_path) as database:
            namespaces = [row[0] for row in database.execute("SELECT DISTINCT namespace_id FROM publications WHERE target_id=?", (target_id,)).fetchall()]
            self._bump_inventory(database, namespaces)
        return namespaces

    def _bump_inventory(self, database, namespace_ids: list[str]) -> None:
        timestamp = now_iso()
        for namespace_id in namespace_ids:
            database.execute("UPDATE namespaces SET inventory_revision=inventory_revision+1,updated_at=? WHERE id=?", (timestamp, namespace_id))

    def publish(self, namespace_id: str, target_id: str, capability_id: str) -> int:
        published = self._target_capability(target_id, capability_id)
        timestamp = now_iso()
        with connect(self.database_path) as database:
            namespace = database.execute("SELECT status FROM namespaces WHERE id=?", (namespace_id,)).fetchone()
            if namespace is None:
                raise KeyError("namespace_not_found")
            if namespace["status"] != "active":
                raise ValueError("namespace_not_active")
            database.execute(
                "INSERT INTO publications(namespace_id,target_id,capability_id,published_name,created_at) VALUES(?,?,?,?,?)",
                (namespace_id, target_id, capability_id, published.capability.name, timestamp),
            )
            database.execute("UPDATE namespaces SET inventory_revision=inventory_revision+1,updated_at=? WHERE id=?", (timestamp, namespace_id))
            revision = database.execute("SELECT inventory_revision FROM namespaces WHERE id=?", (namespace_id,)).fetchone()[0]
        return revision

    def unpublish(self, namespace_id: str, published_name: str) -> int:
        timestamp = now_iso()
        with connect(self.database_path) as database:
            cursor = database.execute("DELETE FROM publications WHERE namespace_id=? AND published_name=?", (namespace_id, published_name))
            if cursor.rowcount != 1:
                raise KeyError("publication_not_found")
            database.execute("UPDATE namespaces SET inventory_revision=inventory_revision+1,updated_at=? WHERE id=?", (timestamp, namespace_id))
            return database.execute("SELECT inventory_revision FROM namespaces WHERE id=?", (namespace_id,)).fetchone()[0]

    def list_publications(self) -> list[dict[str, object]]:
        with connect(self.database_path) as database:
            rows = database.execute("SELECT p.namespace_id,n.key namespace_key,p.target_id,t.key target_key,p.capability_id,p.published_name,n.inventory_revision FROM publications p JOIN namespaces n ON n.id=p.namespace_id JOIN targets t ON t.id=p.target_id ORDER BY n.key,p.published_name").fetchall()
        return [dict(row) for row in rows]

    def visible_capabilities(self, namespace_id: str) -> list[PublishedCapability]:
        with connect(self.database_path) as database:
            rows = database.execute(
                "SELECT p.target_id,p.capability_id,t.key target_key,t.adapter_type,t.configuration_json,t.encrypted_secret FROM publications p JOIN targets t ON t.id=p.target_id JOIN namespaces n ON n.id=p.namespace_id WHERE p.namespace_id=? AND n.status='active' AND t.enabled=1 AND t.technical_state='valid' ORDER BY p.published_name",
                (namespace_id,),
            ).fetchall()
        result = []
        for row in rows:
            try:
                published = self._row_capability(namespace_id, row)
            except ValueError:
                continue
            result.append(published)
        return result

    def resolve(self, namespace_id: str, published_name: str) -> PublishedCapability:
        for capability in self.visible_capabilities(namespace_id):
            if capability.capability.name == published_name:
                return capability
        raise KeyError("capability_not_available")

    def _target_capability(self, target_id: str, capability_id: str) -> PublishedCapability:
        with connect(self.database_path) as database:
            row = database.execute("SELECT id target_id,key target_key,adapter_type,configuration_json,encrypted_secret FROM targets WHERE id=? AND enabled=1 AND technical_state='valid'", (target_id,)).fetchone()
        if row is None:
            raise KeyError("target_not_available")
        return self._row_capability("", {**dict(row), "capability_id": capability_id})

    def _row_capability(self, namespace_id: str, row) -> PublishedCapability:
        configuration = json.loads(row["configuration_json"])
        adapter = self.registry.get(row["adapter_type"])
        capability_source=getattr(adapter,"capabilities_for_target",adapter.capabilities)
        capabilities=capability_source(configuration,row["target_key"]) if hasattr(adapter,"capabilities_for_target") else capability_source(configuration)
        capability = next((item.validated() for item in capabilities if item.capability_id == row["capability_id"]), None)
        if capability is None:
            raise ValueError("capability_not_available")
        return PublishedCapability(namespace_id, row["target_id"], row["target_key"], row["adapter_type"], configuration, row["encrypted_secret"], capability)

    def publication_fingerprint(self, namespace_id: str) -> str:
        encoded = json.dumps([(item.capability.name, item.capability.input_schema) for item in self.visible_capabilities(namespace_id)], sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()
