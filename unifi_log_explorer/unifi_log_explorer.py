#!/usr/bin/env python3
"""UniFi Log Explorer local collector and network activity explorer."""

from __future__ import annotations

import hmac
import hashlib
import http.client
import html
import ipaddress
import csv
import io
import json
import logging
import os
import re
import secrets
import socket
import sqlite3
import ssl
import stat
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # Host-side parser tests do not require the container dependency.
    Fernet = None
    InvalidToken = ValueError

DATA = Path(os.environ.get("UNIFI_LOG_EXPLORER_DATA", "/data"))
DB_PATH = DATA / "diagnostics.db"
OPTIONS_PATH = DATA / "options.json"
ENCRYPTED_API_KEY_PATH = DATA / "unifi_api_key.enc"
API_KEY_KEY_PATH = DATA / "unifi_api_key.key"
WEB_PORT = 8090
CEF_PORT = 5514
ASSET_DIR = Path(__file__).resolve().parent
CEF_HEADER = re.compile(r"(?:<\d+>)?\s*CEF:(\d+)\|((?:\\\||[^|])*)\|((?:\\\||[^|])*)\|((?:\\\||[^|])*)\|((?:\\\||[^|])*)\|((?:\\\||[^|])*)\|([^|]*)\|(.*)")
CEF_PAIR = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=((?:\\[=\\]|[^ ])*(?: (?![A-Za-z][A-Za-z0-9_]*=)[^ ]*)*)")
SYSLOG_HEADER = re.compile(r"^<(\d{1,3})>([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.*)$", re.DOTALL)
SYSLOG_NO_TIMESTAMP = re.compile(r"^<(\d{1,3})>(\S+)\s+(.*)$", re.DOTALL)
SYSLOG_TAG = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[(\d+)\])?:\s*(.*)$", re.DOTALL)
def load_options():
    defaults = {"allowed_source_ips": ["192.168.1.1"], "retention_hours": 168,
                "max_records": 250000,
                "unifi_base_url": "https://192.168.1.1", "unifi_site_slug": "default",
                "unifi_api_key": "", "verify_ssl": False,
                "unifi_certificate_sha256": "",
                "flow_collection_enabled": False, "flow_poll_interval_seconds": 120,
                "flow_initial_backfill_minutes": 1440,
                "log_level": "info"}
    try:
        defaults.update(json.loads(OPTIONS_PATH.read_text()))
    except (OSError, ValueError):
        pass
    allowed = set()
    for value in defaults["allowed_source_ips"]:
        try:
            allowed.add(str(ipaddress.ip_address(value)))
        except ValueError:
            logging.warning("Ignoring invalid allowed source IP: %s", value)
    if not allowed:
        raise SystemExit("allowed_source_ips must contain at least one valid address")
    defaults["allowed_source_ips"] = allowed
    configured_key = str(defaults.get("unifi_api_key") or "").strip()
    if configured_key and os.environ.get("UNIFI_LOG_EXPLORER_SECRETS_PREPARED") != "1":
        defaults["unifi_api_key"] = configured_key
    else:
        defaults["unifi_api_key"] = decrypt_api_key(required=False)
    defaults["unifi_certificate_sha256"] = normalize_certificate_sha256(
        defaults.get("unifi_certificate_sha256")
    )
    if defaults["unifi_api_key"] and not defaults.get("verify_ssl") and not defaults["unifi_certificate_sha256"]:
        raise RuntimeError(
            "Connexion TLS UniFi sécurisée refusée : activez verify_ssl ou configurez "
            "unifi_certificate_sha256 avant l'envoi de la clé API"
        )
    return defaults


def normalize_certificate_sha256(value):
    fingerprint = str(value or "").strip()
    fingerprint = re.sub(r"^sha256\s+fingerprint\s*=\s*", "", fingerprint, flags=re.I)
    fingerprint = fingerprint.replace(":", "").replace(" ", "").lower()
    if fingerprint and not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise RuntimeError("unifi_certificate_sha256 doit contenir exactement 64 caractères hexadécimaux")
    return fingerprint


def sanitize_unifi_error(value, api_key):
    return value.replace(api_key, "<redacted>") if api_key else value


def save_private(path, data):
    temp = path.with_suffix(path.suffix + ".tmp")
    with os.fdopen(os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as handle:
        handle.write(data)
    os.replace(temp, path)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def encryption_key():
    if Fernet is None:
        raise RuntimeError("cryptography is unavailable")
    try:
        key = API_KEY_KEY_PATH.read_bytes().strip()
    except FileNotFoundError:
        key = Fernet.generate_key()
        save_private(API_KEY_KEY_PATH, key + b"\n")
    Fernet(key)
    return key


def encrypt_api_key(value):
    token = Fernet(encryption_key()).encrypt(value.encode()).decode("ascii")
    save_private(ENCRYPTED_API_KEY_PATH, json.dumps({"version": 1, "algorithm": "fernet", "token": token}).encode() + b"\n")


def decrypt_api_key(required=True):
    if not ENCRYPTED_API_KEY_PATH.exists():
        if required: raise RuntimeError("Aucune clé API UniFi n'est configurée")
        return ""
    if Fernet is None:
        raise RuntimeError("cryptography is unavailable")
    try:
        payload = json.loads(ENCRYPTED_API_KEY_PATH.read_text())
        key = API_KEY_KEY_PATH.read_bytes().strip()
        return Fernet(key).decrypt(payload["token"].encode("ascii")).decode()
    except (OSError, KeyError, ValueError, InvalidToken, json.JSONDecodeError) as exc:
        raise RuntimeError("La clé API UniFi chiffrée ne peut pas être déchiffrée") from exc


def save_supervisor_options(options):
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN indisponible pour effacer la clé API des options")
    request = urllib.request.Request("http://supervisor/addons/self/options",
        data=json.dumps({"options": options}).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()


def prepare_secrets():
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        options = json.loads(OPTIONS_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return
    configured = str(options.get("unifi_api_key") or "").strip()
    if not configured:
        return
    encrypt_api_key(configured)
    sanitized = dict(options); sanitized["unifi_api_key"] = ""
    save_supervisor_options(sanitized)
    logging.info("UniFi API key encrypted locally and cleared from App options")


def traffic_flow_page(options, timestamp_from, timestamp_to, page_number=1, page_size=100):
    base_url = str(options.get("unifi_base_url") or "").rstrip("/")
    parsed_url = urllib.parse.urlparse(base_url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise RuntimeError("L'URL UniFi doit être une URL HTTPS valide")
    site = str(options.get("unifi_site_slug") or "default").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", site):
        raise RuntimeError("L'identifiant de site UniFi est invalide")
    empty_filters = ("risk action direction protocol policy policy_type service destination_domain "
                     "destination_host destination_ip destination_mac destination_network_id destination_port "
                     "destination_region destination_zone_id except_for in_network_id next_ai_query out_network_id "
                     "source_domain source_host source_ip source_mac source_network_id source_port source_region source_zone_id").split()
    payload = {key: [] for key in empty_filters}
    payload.update({"pageNumber": page_number, "pageSize": page_size, "search_text": "", "skip_count": False,
                    "timestampFrom": timestamp_from, "timestampTo": timestamp_to})
    url = f"{base_url}/proxy/network/v2/api/site/{site}/traffic-flows"
    request_url = urllib.parse.urlsplit(url)
    api_key = str(options.get("unifi_api_key") or decrypt_api_key())
    fingerprint = normalize_certificate_sha256(options.get("unifi_certificate_sha256"))
    verify_ssl = bool(options.get("verify_ssl"))
    if not verify_ssl and not fingerprint:
        raise RuntimeError(
            "Connexion TLS UniFi sécurisée refusée : activez verify_ssl ou configurez "
            "unifi_certificate_sha256 avant l'envoi de la clé API"
        )
    context = ssl.create_default_context() if verify_ssl else ssl._create_unverified_context()
    connection = http.client.HTTPSConnection(
        parsed_url.hostname, parsed_url.port or 443, timeout=15, context=context
    )
    try:
        connection.connect()
        if fingerprint:
            certificate = connection.sock.getpeercert(binary_form=True) if connection.sock else b""
            actual = hashlib.sha256(certificate).hexdigest()
            if not hmac.compare_digest(actual, fingerprint):
                raise RuntimeError(
                    "Connexion TLS UniFi refusée : empreinte SHA-256 du certificat différente "
                    f"(attendue {fingerprint.upper()}, reçue {actual.upper()})"
                )
        target = urllib.parse.urlunsplit(("", "", request_url.path or "/", request_url.query, ""))
        connection.request("POST", target, body=json.dumps(payload).encode(), headers={
            "Accept": "application/json", "Content-Type": "application/json", "X-API-KEY": api_key
        })
        response = connection.getresponse()
        body = response.read().decode("utf-8", "replace")
        if response.status >= 400:
            raise RuntimeError(f"HTTP {response.status}: {sanitize_unifi_error(body[:500], api_key)}")
        result = json.loads(body)
    except ssl.SSLCertVerificationError as exc:
        raise RuntimeError(
            "Connexion TLS UniFi refusée : le certificat n'est pas reconnu ; configurez son "
            "empreinte SHA-256 ou installez un certificat de confiance"
        ) from exc
    except (OSError, http.client.HTTPException) as exc:
        raise RuntimeError(sanitize_unifi_error(str(exc), api_key)) from exc
    finally:
        connection.close()
    if not isinstance(result, dict) or not isinstance(result.get("data"), list):
        raise RuntimeError("Réponse Traffic Flows inattendue")
    return result


def flow_probe(options):
    now = int(time.time() * 1000)
    result = traffic_flow_page(options, now - 5 * 60 * 1000, now, 1, 1)
    sample_fields = sorted(result["data"][0].keys()) if result["data"] else []
    return {"ok": True, "tested_at": int(time.time()), "returned": len(result["data"]),
            "total": result.get("total_element_count"), "has_next": result.get("has_next"),
            "sample_fields": sample_fields}


class Store:
    def __init__(self, options):
        DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.options = options
        self.lock = threading.RLock()
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA journal_mode=WAL;
          PRAGMA synchronous=NORMAL;
          CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS records(
            id INTEGER PRIMARY KEY, received_at INTEGER NOT NULL, kind TEXT NOT NULL,
            source_ip TEXT NOT NULL, summary TEXT NOT NULL, detail TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS records_time ON records(received_at);
          CREATE INDEX IF NOT EXISTS records_kind_time ON records(kind, received_at);
          CREATE TABLE IF NOT EXISTS counters(key TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS traffic_flows(
            id TEXT PRIMARY KEY, flow_start_time INTEGER NOT NULL, flow_end_time INTEGER NOT NULL,
            source_ip TEXT, destination_ip TEXT, service TEXT, action TEXT, detail TEXT NOT NULL,
            collected_at INTEGER NOT NULL);
          CREATE INDEX IF NOT EXISTS traffic_flows_end ON traffic_flows(flow_end_time);
          CREATE INDEX IF NOT EXISTS traffic_flows_source ON traffic_flows(source_ip);
          CREATE INDEX IF NOT EXISTS traffic_flows_destination ON traffic_flows(destination_ip);
          CREATE INDEX IF NOT EXISTS traffic_flows_service ON traffic_flows(service);
          CREATE INDEX IF NOT EXISTS traffic_flows_action ON traffic_flows(action);
        """)
        self.db.commit()

    def setting(self, key):
        with self.lock:
            row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row[0] if row else None

    def set_setting(self, key, value):
        with self.lock:
            self.db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
            self.db.commit()

    def increment(self, key, count=1):
        with self.lock:
            self.db.execute("INSERT INTO counters(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=value+?", (key, count, count))
            self.db.commit()

    def add(self, kind, source, summary, detail):
        with self.lock:
            self.db.execute("INSERT INTO records(received_at,kind,source_ip,summary,detail) VALUES(?,?,?,?,?)",
                            (int(time.time()), kind, source, summary, json.dumps(detail, separators=(",", ":"))))
            self.db.commit()

    def prune(self):
        cutoff = int(time.time()) - int(self.options["retention_hours"]) * 3600
        limit = int(self.options["max_records"])
        with self.lock:
            self.db.execute("DELETE FROM records WHERE received_at < ?", (cutoff,))
            count = self.db.execute("SELECT count(*) FROM records").fetchone()[0]
            if count > limit:
                self.db.execute("DELETE FROM records WHERE id IN (SELECT id FROM records ORDER BY id LIMIT ?)", (count - limit,))
            self.db.execute("DELETE FROM traffic_flows WHERE flow_end_time < ?", (cutoff * 1000,))
            flow_count = self.db.execute("SELECT count(*) FROM traffic_flows").fetchone()[0]
            if flow_count > limit:
                self.db.execute("DELETE FROM traffic_flows WHERE id IN (SELECT id FROM traffic_flows ORDER BY flow_end_time LIMIT ?)", (flow_count - limit,))
            self.db.commit()

    def add_flows(self, flows):
        inserted = 0
        with self.lock:
            for flow in flows:
                flow_id = str(flow.get("id") or "")
                start, end = flow.get("flow_start_time"), flow.get("flow_end_time")
                if not flow_id or not isinstance(start, int) or not isinstance(end, int):
                    continue
                cursor = self.db.execute("INSERT OR IGNORE INTO traffic_flows(id,flow_start_time,flow_end_time,source_ip,destination_ip,service,action,detail,collected_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (flow_id, start, end, flow.get("source", {}).get("ip"), flow.get("destination", {}).get("ip"),
                     flow.get("service"), flow.get("action"), json.dumps(flow, separators=(",", ":")), int(time.time())))
                inserted += cursor.rowcount
            self.db.commit()
        return inserted

    def known_flow_ids(self, identifiers):
        values = [str(value) for value in identifiers if value]
        if not values: return set()
        placeholders = ",".join("?" for _ in values)
        with self.lock:
            return {row[0] for row in self.db.execute(f"SELECT id FROM traffic_flows WHERE id IN ({placeholders})", values)}

    def dashboard(self):
        with self.lock:
            counts = {r["kind"]: r["n"] for r in self.db.execute("SELECT kind,count(*) n FROM records WHERE kind IN ('cef','syslog') GROUP BY kind")}
            counters = {r["key"]: r["value"] for r in self.db.execute("SELECT key,value FROM counters WHERE key LIKE 'cef_%'")}
            recent = self.recent_records()
            cef_types = [dict(r) for r in self.db.execute("SELECT json_extract(detail,'$.name') name,count(*) count FROM records WHERE kind='cef' GROUP BY name ORDER BY count DESC LIMIT 20")]
            syslog_apps = [dict(r) for r in self.db.execute("SELECT json_extract(detail,'$.app_name') app_name,count(*) count FROM records WHERE kind='syslog' GROUP BY app_name ORDER BY count DESC LIMIT 20")]
            rejected_sources = {}
            for row in self.db.execute("SELECT key,value FROM counters WHERE key LIKE 'cef_rejected_source:%'"):
                address = row["key"].split(":", 1)[1]
                rejected_sources[address] = rejected_sources.get(address, 0) + row["value"]
            flow_stats = dict(self.db.execute("SELECT count(*) count, min(flow_end_time) oldest, max(flow_end_time) newest FROM traffic_flows").fetchone())
        return {"counts": counts, "counters": counters, "recent": recent,
                "cef_types": cef_types, "syslog_apps": syslog_apps,
                "rejected_sources": rejected_sources,
                "flow_stats": flow_stats,
                "allowed_source_ips": sorted(self.options["allowed_source_ips"]),
                "retention_hours": self.options["retention_hours"], "max_records": self.options["max_records"]}

    def recent_records(self, kind=None, limit=100):
        clauses, values = ["kind IN ('cef','syslog')"], []
        if kind in ("cef", "syslog"):
            clauses.append("kind=?"); values.append(kind)
        with self.lock:
            return [dict(row) for row in self.db.execute(
                f"SELECT id,received_at,kind,source_ip,summary FROM records WHERE {' AND '.join(clauses)} ORDER BY id DESC LIMIT ?",
                values + [max(1, min(500, int(limit)))])]

    def query_events(self, filters, page=1, page_size=50):
        clauses, values = ["kind IN ('cef','syslog')"], []
        kind = str(filters.get("kind") or "").lower()
        if kind in ("cef", "syslog"):
            clauses.append("kind=?"); values.append(kind)
        hours = max(1, min(720, int(filters.get("hours") or 24)))
        clauses.append("received_at>=?"); values.append(int(time.time()) - hours * 3600)
        source = str(filters.get("source") or "").strip()
        if source:
            clauses.append("source_ip LIKE ?"); values.append(f"%{source}%")
        query = str(filters.get("q") or "").strip()
        if query:
            clauses.append("(summary LIKE ? OR detail LIKE ?)"); values.extend([f"%{query}%"] * 2)
        where = " AND ".join(clauses)
        page_size = max(10, min(100, int(page_size)))
        with self.lock:
            total = self.db.execute(f"SELECT count(*) FROM records WHERE {where}", values).fetchone()[0]
            pages = max(1, (total + page_size - 1) // page_size)
            page = max(1, min(int(page), pages))
            rows = [dict(row) for row in self.db.execute(
                f"SELECT id,received_at,kind,source_ip,summary FROM records WHERE {where} "
                "ORDER BY id DESC LIMIT ? OFFSET ?", values + [page_size, (page - 1) * page_size])]
        return {"rows": rows, "total": total, "page": page, "pages": pages,
                "page_size": page_size, "hours": hours, "kind": kind}

    def event_by_id(self, event_id):
        try: event_id = int(event_id)
        except (TypeError, ValueError): return None
        with self.lock:
            row = self.db.execute("SELECT * FROM records WHERE id=? AND kind IN ('cef','syslog')", (event_id,)).fetchone()
        if not row: return None
        result = dict(row); result["detail"] = json.loads(result["detail"])
        return result

    def operational_status(self):
        with self.lock:
            page_size = self.db.execute("PRAGMA page_size").fetchone()[0]
            page_count = self.db.execute("PRAGMA page_count").fetchone()[0]
            event = dict(self.db.execute("SELECT count(*) count,min(received_at) oldest,max(received_at) newest FROM records WHERE kind IN ('cef','syslog')").fetchone())
            flows = dict(self.db.execute("SELECT count(*) count,min(flow_end_time) oldest,max(flow_end_time) newest FROM traffic_flows").fetchone())
        raw = self.setting("flow_collection_status")
        try: collection = json.loads(raw) if raw else None
        except json.JSONDecodeError: collection = None
        reconciliation = self.setting("flow_last_reconciliation")
        return {"database_bytes": page_size * page_count, "events": event, "flows": flows,
                "collection": collection, "last_reconciliation": int(reconciliation) if reconciliation and reconciliation.isdigit() else None}

    def timeline(self, hours=24):
        now_hour = int(time.time()) // 3600 * 3600
        first = now_hour - (hours - 1) * 3600
        with self.lock:
            flow_values = {row["bucket"]: row["count"] for row in self.db.execute(
                "SELECT (flow_end_time/3600000)*3600 bucket,count(*) count FROM traffic_flows WHERE flow_end_time>=? GROUP BY bucket",
                (first * 1000,))}
            event_values = {row["bucket"]: row["count"] for row in self.db.execute(
                "SELECT (received_at/3600)*3600 bucket,count(*) count FROM records WHERE received_at>=? AND kind IN ('cef','syslog') GROUP BY bucket",
                (first,))}
        return [{"time": stamp, "flows": flow_values.get(stamp, 0), "events": event_values.get(stamp, 0)}
                for stamp in range(first, now_hour + 1, 3600)]

    def export_flow_rows(self, filters, limit=50000):
        result = self.query_flows(filters, 1, 100)
        rows = list(result["rows"])
        for page in range(2, min(result["pages"], (limit + 99) // 100) + 1):
            rows.extend(self.query_flows(filters, page, 100)["rows"])
        return rows[:limit]

    def export_event_rows(self, filters, limit=50000):
        result = self.query_events(filters, 1, 100)
        rows = list(result["rows"])
        for page in range(2, min(result["pages"], (limit + 99) // 100) + 1):
            rows.extend(self.query_events(filters, page, 100)["rows"])
        return rows[:limit]

    def purge(self, target):
        table = {"events": "records", "flows": "traffic_flows"}.get(target)
        if not table: raise ValueError("invalid purge target")
        with self.lock:
            count = self.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            self.db.execute(f"DELETE FROM {table}"); self.db.commit()
        return count

    def flow_overview(self, hours=24):
        cutoff = int(time.time() * 1000) - hours * 3600_000
        with self.lock:
            summary = dict(self.db.execute("""
                SELECT count(*) count, count(DISTINCT source_ip) sources,
                       count(DISTINCT destination_ip) destinations,
                       coalesce(sum(flow_end_time-flow_start_time),0) duration_ms
                FROM traffic_flows WHERE flow_end_time>=?""", (cutoff,)).fetchone())
            def top(column):
                return [dict(row) for row in self.db.execute(
                    f"SELECT coalesce({column},'Inconnu') label,count(*) count FROM traffic_flows "
                    "WHERE flow_end_time>=? GROUP BY label ORDER BY count DESC LIMIT 8", (cutoff,))]
            summary["services"] = top("service")
            summary["actions"] = top("action")
            summary["sources_top"] = top("coalesce(json_extract(detail,'$.source.client_name'),source_ip)")
            summary["destinations_top"] = top("coalesce(json_extract(detail,'$.destination.domain'),json_extract(detail,'$.destination.domains[0]'),destination_ip)")
        return summary

    def query_flows(self, filters, page=1, page_size=50):
        clauses, values = [], []
        hours = max(1, min(720, int(filters.get("hours") or 24)))
        clauses.append("flow_end_time>=?"); values.append(int(time.time() * 1000) - hours * 3600_000)
        columns = {"source": "source_ip", "destination": "destination_ip",
                   "service": "service", "action": "action"}
        for key, column in columns.items():
            value = str(filters.get(key) or "").strip()
            if value:
                clauses.append(f"{column} LIKE ?"); values.append(f"%{value}%")
        direction = str(filters.get("direction") or "").strip()
        if direction:
            clauses.append("json_extract(detail,'$.direction')=?"); values.append(direction)
        query = str(filters.get("q") or "").strip()
        if query:
            clauses.append("(source_ip LIKE ? OR destination_ip LIKE ? OR service LIKE ? OR detail LIKE ?)")
            values.extend([f"%{query}%"] * 4)
        where = " AND ".join(clauses)
        page_size = max(10, min(100, int(page_size)))
        with self.lock:
            total = self.db.execute(f"SELECT count(*) FROM traffic_flows WHERE {where}", values).fetchone()[0]
            pages = max(1, (total + page_size - 1) // page_size)
            page = max(1, min(int(page), pages))
            rows = [dict(row) for row in self.db.execute(
                f"SELECT id,flow_start_time,flow_end_time,source_ip,destination_ip,service,action,detail "
                f"FROM traffic_flows WHERE {where} ORDER BY flow_end_time DESC LIMIT ? OFFSET ?",
                values + [page_size, (page - 1) * page_size])]
        for row in rows:
            row["detail"] = json.loads(row["detail"])
        return {"rows": rows, "total": total, "page": page, "pages": pages,
                "page_size": page_size, "hours": hours}

    def flow_by_id(self, flow_id):
        with self.lock:
            row = self.db.execute("SELECT * FROM traffic_flows WHERE id=?", (flow_id,)).fetchone()
        if not row: return None
        result = dict(row); result["detail"] = json.loads(result["detail"])
        return result

    def export(self):
        with self.lock:
            rows = [dict(r) for r in self.db.execute("SELECT received_at,kind,summary,detail FROM records WHERE kind IN ('cef','syslog') ORDER BY id")]
        for row in rows:
            row["detail"] = json.loads(row["detail"])
        diagnostics = self.dashboard()
        for recent in diagnostics["recent"]:
            recent.pop("source_ip", None)
        diagnostics.pop("allowed_source_ips", None)
        return {"generated_at": int(time.time()), "diagnostics": diagnostics, "records": rows}


def parse_cef(raw):
    text = raw.decode("utf-8", "replace").strip("\x00\r\n ")
    match = CEF_HEADER.search(text)
    if not match:
        raise ValueError("message does not contain a valid CEF header")
    version, vendor, product, device_version, event_id, name, severity, extension = match.groups()
    fields = {m.group(1): m.group(2).replace("\\=", "=").replace("\\\\", "\\") for m in CEF_PAIR.finditer(extension)}
    return {"cef_version": version, "vendor": vendor, "product": product,
            "device_version": device_version, "event_id": event_id, "name": name,
            "severity": severity, "fields": fields, "bytes": len(raw), "_kind": "cef"}


def parse_syslog_or_cef(raw):
    text = raw.decode("utf-8", "replace").strip("\x00\r\n ")
    if "CEF:" in text:
        return parse_cef(raw)
    match = SYSLOG_HEADER.match(text)
    if match:
        priority_text, timestamp, hostname, body = match.groups()
    else:
        fallback = SYSLOG_NO_TIMESTAMP.match(text)
        if not fallback:
            raise ValueError("message is neither CEF nor supported syslog")
        priority_text, hostname, body = fallback.groups()
        timestamp = None
    priority = int(priority_text)
    if body.startswith(hostname + " "):
        body = body[len(hostname) + 1:]
    tag = SYSLOG_TAG.match(body)
    if tag:
        app_name, process_id, message = tag.groups()
    else:
        app_name, process_id, message = None, None, body
    return {"_kind": "syslog", "priority": priority, "facility": priority // 8,
            "severity": priority % 8, "timestamp": timestamp, "hostname": hostname,
            "app_name": app_name, "process_id": int(process_id) if process_id else None,
            "message": message, "bytes": len(raw)}


class Collector(threading.Thread):
    def __init__(self, name, port, store, parser):
        super().__init__(name=name, daemon=True)
        self.port, self.store, self.parser = port, store, parser

    def run(self):
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        sock.bind(("::", self.port))
        logging.info("%s listening on UDP %s", self.name, self.port)
        while True:
            raw, peer = sock.recvfrom(65535)
            if not raw:
                continue
            source = peer[0].removeprefix("::ffff:")
            if source not in self.store.options["allowed_source_ips"]:
                self.store.increment(f"{self.name}_rejected_source")
                self.store.increment(f"{self.name}_rejected_source:{source}")
                continue
            self.store.increment(f"{self.name}_datagrams")
            self.store.increment(f"{self.name}_bytes", len(raw))
            try:
                parsed = self.parser(raw)
                kind = parsed.pop("_kind", "cef")
                if kind == "cef":
                    summary = f"{parsed['name']} · severity {parsed['severity']}"
                else:
                    label = parsed.get("app_name") or "syslog"
                    summary = f"{label} · {parsed.get('message', '')[:120]}"
                self.store.add(kind, source, summary, parsed)
            except Exception as exc:
                self.store.increment(f"{self.name}_parse_errors")
                self.store.add(f"{self.name}_error", source, str(exc), {"bytes": len(raw), "prefix_hex": raw[:64].hex()})


class FlowCollector(threading.Thread):
    CHUNK_MS = 30 * 60_000
    SCAN_WINDOW_MS = 24 * 60 * 60_000
    FAST_SCAN_MAX_PAGES = 5
    RECONCILE_INTERVAL_SECONDS = 6 * 60 * 60
    BACKFILL_VERSION = "2"

    def __init__(self, store):
        super().__init__(name="traffic-flows", daemon=True)
        self.store = store

    def collect_window(self, start, end, depth=0):
        first = traffic_flow_page(self.store.options, start, end, 1, 100)
        if first.get("or_more") and end - start > 60_000 and depth < 12:
            middle = start + (end - start) // 2
            left = self.collect_window(start, middle, depth + 1)
            right = self.collect_window(middle + 1, end, depth + 1)
            return tuple(a + b for a, b in zip(left, right))
        fetched = len(first["data"])
        inserted = self.store.add_flows(first["data"])
        pages = 1
        page = 2
        while first.get("has_next") and page <= int(first.get("total_page_count") or 100):
            result = traffic_flow_page(self.store.options, start, end, page, 100)
            fetched += len(result["data"])
            inserted += self.store.add_flows(result["data"])
            pages += 1
            if not result.get("has_next"): break
            page += 1
        return fetched, inserted, pages

    def repair_backfill(self, now):
        totals = [0, 0, 0]
        backfill_ms = max(1440, int(self.store.options["flow_initial_backfill_minutes"])) * 60_000
        cursor = now - backfill_ms
        while cursor < now:
            chunk_end = min(cursor + self.CHUNK_MS, now)
            values = self.collect_window(cursor, chunk_end)
            totals = [a + b for a, b in zip(totals, values)]
            cursor = chunk_end + 1
        self.store.set_setting("flow_backfill_version", self.BACKFILL_VERSION)
        logging.info("Traffic Flows 24h repair: fetched=%s inserted=%s pages=%s", *totals)
        return totals

    def scan_newest(self, now):
        start = now - self.SCAN_WINDOW_MS
        totals = [0, 0, 0]
        consecutive_known_pages = 0
        page = 1
        while page <= self.FAST_SCAN_MAX_PAGES:
            result = traffic_flow_page(self.store.options, start, now, page, 100)
            flows = result["data"]
            identifiers = [flow.get("id") for flow in flows]
            known_before = self.store.known_flow_ids(identifiers)
            inserted = self.store.add_flows(flows)
            totals[0] += len(flows); totals[1] += inserted; totals[2] += 1
            if flows and len(known_before) == len(flows):
                consecutive_known_pages += 1
            else:
                consecutive_known_pages = 0
            if not result.get("has_next") or consecutive_known_pages >= 2:
                break
            page += 1
        return totals

    def reconciliation_due(self, now_seconds):
        value = self.store.setting("flow_last_reconciliation")
        if value is None:
            # An installation upgraded from 0.3.1 has already completed its
            # initial repair. Start the new schedule without repeating it.
            self.store.set_setting("flow_last_reconciliation", str(now_seconds))
            return False
        try:
            return now_seconds - int(value) >= self.RECONCILE_INTERVAL_SECONDS
        except (TypeError, ValueError):
            return True

    def cycle(self):
        now = int(time.time() * 1000)
        if self.store.setting("flow_backfill_version") != self.BACKFILL_VERSION:
            totals = self.repair_backfill(now)
            strategy = "initial-repair"
            self.store.set_setting("flow_last_reconciliation", str(now // 1000))
        elif self.reconciliation_due(now // 1000):
            totals = self.repair_backfill(now)
            strategy = "scheduled-reconciliation"
            self.store.set_setting("flow_last_reconciliation", str(now // 1000))
        else:
            totals = self.scan_newest(now)
            strategy = "fast-scan"
        status = {"ok": True, "time": int(time.time()), "fetched": totals[0],
                  "inserted": totals[1], "pages": totals[2], "strategy": strategy}
        self.store.set_setting("flow_collection_status", json.dumps(status, separators=(",", ":")))
        logging.info("Traffic Flows cycle: fetched=%s inserted=%s pages=%s", *totals)

    def run(self):
        interval = int(self.store.options["flow_poll_interval_seconds"])
        while True:
            try:
                self.cycle()
            except Exception as exc:
                logging.warning("Traffic Flows collection failed: %s", exc)
                status = {"ok": False, "time": int(time.time()), "error": str(exc)}
                self.store.set_setting("flow_collection_status", json.dumps(status, separators=(",", ":")))
            time.sleep(interval)


CSRF_TOKEN = secrets.token_urlsafe(32)
INGRESS_PROXY_IP = os.environ.get("UNIFI_LOG_EXPLORER_INGRESS_PROXY_IP", "172.30.32.2")

EN = {
    "Vue d’ensemble": "Overview", "Traffic Flows": "Traffic Flows", "CEF / Syslog": "CEF / Syslog", "Paramètres": "Settings",
    "Mode clair": "Light mode", "Mode sombre": "Dark mode",
    "Activité réseau des dernières 24 heures": "Network activity over the last 24 hours",
    "Flows sur 24 h": "Flows over 24 h", "Sources actives": "Active sources", "Destinations": "Destinations", "Flows archivés": "Archived flows",
    "Événements CEF": "CEF events", "Messages Syslog": "Syslog messages", "Principaux clients": "Top clients", "Services": "Services",
    "Actions": "Actions", "Activité horaire": "Hourly activity", "Collecte opérationnelle": "Collection operational",
    "Collecte en attente": "Collection pending", "Collecte opérationnelle": "Collection operational",
    "Recherchez et inspectez les connexions archivées.": "Search and inspect archived connections.",
    "Recherche": "Search", "Source": "Source", "Destination": "Destination", "Service": "Service", "Direction": "Direction",
    "Période": "Period", "Filtrer": "Filter", "Toutes": "All", "Sortant": "Outgoing", "Entrant": "Incoming",
    "1 heure": "1 hour", "6 heures": "6 hours", "24 heures": "24 hours", "3 jours": "3 days", "7 jours": "7 days", "30 jours": "30 days",
    "Exporter les résultats CSV": "Export filtered CSV", "Date": "Date", "Action": "Action", "Détails": "Details",
    "Précédent": "Previous", "Suivant": "Next", "Aucun flow ne correspond à ces filtres.": "No flow matches these filters.",
    "Retour aux flows": "Back to flows", "Résumé": "Summary", "Début": "Start", "Fin": "End", "Durée": "Duration",
    "Protocole": "Protocol", "Risque": "Risk", "Nom": "Name", "Adresse IP": "IP address", "Port": "Port", "Région": "Region", "Zone": "Zone",
    "Données UniFi complètes": "Complete UniFi data", "Recherchez dans les événements transmis par vos équipements UniFi.": "Search events forwarded by your UniFi devices.",
    "Type": "Type", "Émetteur": "Sender", "Aucun événement ne correspond à ces filtres.": "No event matches these filters.",
    "Retour aux événements": "Back to events", "Événement": "Event", "Données complètes": "Complete data",
    "Outils et état de la configuration locale.": "Tools and local configuration status.", "État et stockage": "Status and storage",
    "Base SQLite": "SQLite database", "Événements": "Events", "Prochaine réconciliation": "Next reconciliation",
    "Apparence": "Appearance", "Le choix est mémorisé uniquement dans ce navigateur.": "The choice is stored only in this browser.",
    "Langue": "Language", "Français": "French", "Anglais": "English", "API UniFi": "UniFi API", "Tester la connexion": "Test connection",
    "Aucun test effectué.": "No test performed.", "Diagnostic": "Diagnostics", "Exporter le diagnostic JSON": "Export diagnostic JSON",
    "Configuration": "Configuration", "Sources autorisées": "Allowed sources", "Rétention": "Retention", "Limite": "Limit",
    "Collecte des flows": "Flow collection", "Fréquence": "Frequency", "Site": "Site", "Vérification TLS": "TLS verification",
    "Activée": "Enabled", "Désactivée": "Disabled", "Maintenance des données": "Data maintenance", "Données à supprimer": "Data to delete",
    "Événements CEF / Syslog": "CEF / Syslog events", "Saisissez PURGER pour confirmer": "Enter PURGE to confirm",
    "Supprimer les données": "Delete data", "Opérationnelle": "Operational", "En retard": "Delayed", "Aucun cycle enregistré.": "No recorded cycle.",
    "Lecture seule · les modifications s’effectuent dans les options de l’App Home Assistant.": "Read-only · make changes in the Home Assistant App options.",
    "Le test lit au maximum un flow récent et ne le conserve pas. La clé API n’est jamais affichée.": "The test reads at most one recent flow and does not retain it. The API key is never displayed.",
    "L’export contient les compteurs et événements CEF/Syslog, sans les Traffic Flows ni la clé API.": "The export contains counters and CEF/Syslog events, without Traffic Flows or the API key.",
    "Cette suppression est définitive et ne modifie pas les options de collecte.": "This deletion is permanent and does not change collection options.",
    "Outils et état de la configuration locale.": "Tools and local configuration status.",
    "Aucune donnée n’a été supprimée.": "No data was deleted.", "Retour": "Back",
    "Détail du flow": "Flow details", "Détail de l’événement": "Event details",
    "Purge refusée": "Purge rejected",
    "Confirmation incorrecte. Aucune donnée n’a été supprimée.": "Incorrect confirmation. No data was deleted.",
}


STYLE = """
:root{color-scheme:light;--bg:#f4f7fa;--surface:#fff;--surface2:#edf3f8;--text:#17212b;--muted:#64748b;--line:#d8e1ea;--accent:#0787a8;--accent2:#dff5fa;--good:#16845b;--bad:#c43f55;--shadow:0 5px 22px #1e3a5f12}
html[data-theme=dark]{color-scheme:dark;--bg:#0d1420;--surface:#172235;--surface2:#202c41;--text:#e7edf5;--muted:#a4b2c6;--line:#30415d;--accent:#52c9e6;--accent2:#173b4a;--good:#50c895;--bad:#ff8293;--shadow:none}
*{box-sizing:border-box}body{font:15px system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);margin:0}main{max-width:1440px;margin:auto;padding:24px}.top{display:flex;align-items:center;gap:20px;margin-bottom:22px}.brand{font-size:25px;font-weight:800;color:var(--accent);margin-right:auto}.nav{display:flex;gap:5px;flex-wrap:wrap}.nav a,.linkbtn{color:var(--text);text-decoration:none;padding:9px 12px;border-radius:7px}.nav a:hover,.nav .active{background:var(--accent2);color:var(--accent)}h1{font-size:28px;margin:10px 0 4px}h2{margin:0 0 16px;font-size:19px}.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px;box-shadow:var(--shadow)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:12px;margin:16px 0}.metric{font-size:28px;font-variant-numeric:tabular-nums}.muted{color:var(--muted)}.bad{color:var(--bad)}.good{color:var(--good)}button,.button{display:inline-block;background:var(--accent);color:#fff;border:0;border-radius:7px;padding:9px 14px;font-weight:700;text-decoration:none;cursor:pointer}button.secondary,.button.secondary{background:var(--surface2);color:var(--text);border:1px solid var(--line)}form.inline{display:inline}.filters{display:grid;grid-template-columns:2fr repeat(5,minmax(120px,1fr)) auto;gap:10px;align-items:end;margin:16px 0}.filters label{font-size:12px;color:var(--muted)}input,select{display:block;width:100%;margin-top:5px;padding:9px 10px;color:var(--text);background:var(--surface);border:1px solid var(--line);border-radius:7px}.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:10px}table{width:100%;border-collapse:collapse;white-space:nowrap}td,th{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line)}th{font-size:12px;color:var(--muted);background:var(--surface2)}tr:last-child td{border:0}td.wrap{white-space:normal;min-width:160px}.pill{display:inline-block;padding:3px 8px;border-radius:999px;background:var(--surface2);font-size:12px}.bars{display:grid;gap:9px}.barline{display:grid;grid-template-columns:minmax(90px,1fr) 3fr 55px;gap:10px;align-items:center}.bar{height:8px;border-radius:5px;background:var(--surface2);overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}.twocol{display:grid;grid-template-columns:1fr 1fr;gap:12px}.pager{display:flex;justify-content:space-between;align-items:center;margin-top:14px}.route{display:flex;align-items:center;gap:12px;flex-wrap:wrap;font-size:17px}.arrow{color:var(--accent);font-size:22px}.details{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}.kv{display:grid;grid-template-columns:120px 1fr;gap:7px 12px}.kv dt{color:var(--muted)}.kv dd{margin:0;overflow-wrap:anywhere}pre{overflow:auto;background:var(--surface2);padding:14px;border-radius:8px;font-size:12px}.empty{text-align:center;padding:38px;color:var(--muted)}@media(max-width:1100px){main{padding:14px}.top{align-items:flex-start;flex-wrap:wrap}.filters{grid-template-columns:1fr 1fr}.twocol{grid-template-columns:1fr}}@media(max-width:560px){.filters{grid-template-columns:1fr}.brand{width:100%}}
input[type=hidden]{display:none!important}.barlink{color:var(--text);text-decoration:none;border-radius:6px}.barlink:hover{background:var(--accent2)}.clickcard{display:block;color:var(--text);text-decoration:none;transition:transform .15s,border-color .15s}.clickcard:hover{transform:translateY(-2px);border-color:var(--accent)}
.toplogo{display:flex;align-items:center;gap:10px;color:var(--accent);text-decoration:none;font-size:25px;font-weight:800;margin-right:auto}.toplogo img{width:42px;height:42px;border-radius:10px}.toplogo b{font-size:12px;color:var(--muted);font-weight:650}.menu{display:flex;align-items:center;gap:5px;position:relative;z-index:2}.menu a{display:block;position:relative;color:var(--text);text-decoration:none;padding:9px 12px;border-radius:7px}.menu a:hover,.menu a.active{background:var(--accent2);color:var(--accent)}.headeractions{display:flex;gap:8px}.toggle{color:var(--text);padding:9px 12px;border-radius:7px;background:var(--surface);border:1px solid var(--line);cursor:pointer;font:inherit;text-decoration:none}.logfilters{display:flex;gap:8px;margin:16px 0}.logfilters a{background:var(--surface);color:var(--text);border:1px solid var(--line)}.logfilters a.active{background:var(--accent);color:#fff;border-color:var(--accent)}@media(max-width:800px){.menu{width:100%;overflow-x:auto}.toplogo{width:100%}.headeractions{margin-left:auto}}
.barline{grid-template-columns:minmax(0,1.4fr) minmax(80px,3fr) 55px}.barlabel{display:block;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.eventfilters{grid-template-columns:2fr minmax(130px,1fr) minmax(130px,1fr) minmax(130px,1fr) auto}
.overviewhead{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:center;margin:8px 0 12px}.overviewhead h1{margin-top:0}.overviewhead p{margin-bottom:0}.statuscard{margin:0;box-shadow:var(--shadow)}@media(max-width:800px){.overviewhead{grid-template-columns:1fr;gap:12px}}
.settingsgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:16px}.readonly{background:var(--surface2);border-radius:8px;padding:12px}.readonly .kv{grid-template-columns:minmax(150px,220px) 1fr}@media(max-width:800px){.settingsgrid{grid-template-columns:1fr}}
.stackform{display:grid;gap:10px}.stackform label{color:var(--muted);font-size:13px}.statusnote{padding:10px 12px;border-left:4px solid var(--accent);background:var(--surface2);border-radius:6px}
.chart{display:grid;grid-template-columns:repeat(24,1fr);gap:4px;height:130px;align-items:end}.chartcol{height:100%;display:flex;gap:2px;align-items:end}.chartbar{display:block;flex:1;min-height:2px;border-radius:3px 3px 0 0;background:var(--accent)}.chartbar.events{background:var(--good)}.legend{display:flex;gap:18px;margin-top:10px;color:var(--muted)}.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;background:var(--accent);margin-right:5px}.legend i.events{background:var(--good)}.danger{border-color:var(--bad)}.danger button{background:var(--bad)}
"""


def fmt_ms(value):
    if not value: return "—"
    return time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(value / 1000))


def fmt_bytes(value, language="fr"):
    size = float(value or 0)
    units = ("B", "KiB", "MiB", "GiB") if language == "en" else ("o", "Kio", "Mio", "Gio")
    for unit in units:
        if size < 1024 or unit == units[-1]: return f"{size:.1f} {unit}"
        size /= 1024


def csv_safe(value):
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def party_label(flow, side):
    item = flow.get(side) or {}
    if not isinstance(item, dict): return str(item)
    fingerprint = item.get("client_fingerprint") or {}
    if not isinstance(fingerprint, dict): fingerprint = {}
    return str(item.get("name") or item.get("client_name") or item.get("host") or
               fingerprint.get("name") or fingerprint.get("device_name") or item.get("ip") or "—")


def query_link(path, query, **changes):
    values = dict(query); values.update(changes)
    return path + "?" + urllib.parse.urlencode({k: v for k, v in values.items() if v not in (None, "")})


class Web(BaseHTTPRequestHandler):
    store = None
    server_version = "UniFiLogExplorer/0.1"

    def log_message(self, fmt, *args):
        logging.debug("web: " + fmt, *args)

    def theme(self):
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        return "dark" if jar.get("ule_theme") and jar["ule_theme"].value == "dark" else "light"

    def language(self):
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        if jar.get("ule_language") and jar["ule_language"].value in ("fr", "en"):
            return jar["ule_language"].value
        preferred = self.headers.get("Accept-Language", "").lower()
        for item in preferred.split(","):
            code = item.split(";", 1)[0].strip()
            if code.startswith("en"): return "en"
            if code.startswith("fr"): return "fr"
        return "fr"

    def t(self, value):
        return EN.get(value, value) if self.language() == "en" else value

    def localize_markup(self, markup):
        if self.language() != "en": return markup
        for french, english in EN.items():
            markup = markup.replace(f">{french}<", f">{english}<")
        return markup

    def ingress_base(self):
        prefix = self.headers.get("X-Ingress-Path", "").rstrip("/")
        if not re.fullmatch(r"/[A-Za-z0-9/_-]+", prefix):
            return ""
        return prefix

    def url_for(self, path="/"):
        if not path.startswith("/") or path.startswith("//"):
            path = "/"
        return self.ingress_base() + path

    def ingress_request(self):
        address = self.client_address[0] if getattr(self, "client_address", None) else ""
        return address == INGRESS_PROXY_IP and bool(self.ingress_base())

    def prefix_markup(self, markup):
        base = self.ingress_base()
        if not base:
            return markup
        return re.sub(r"(?P<attr>\b(?:href|src|action)=)(?P<quote>['\"]?)/(?P<path>[^'\" >]*)",
                      lambda match: match.group("attr") + match.group("quote") + base + "/" + match.group("path"), markup)

    def send_html(self, body, status=200, headers=None, title="UniFi Log Explorer"):
        body = self.prefix_markup(self.localize_markup(body)); title = self.t(title)
        raw = (f"<!doctype html><html lang='{self.language()}' data-theme='{self.theme()}'><head><meta charset=utf-8>"
               f"<meta name=viewport content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>"
               f"<style>{STYLE}</style></head><body><main>{body}</main></body></html>").encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'self'")
        for key, value in (headers or {}).items(): self.send_header(key, value)
        self.end_headers(); self.wfile.write(raw)

    def send_asset(self, filename):
        try: raw = (ASSET_DIR / filename).read_bytes()
        except OSError: return self.send_error(404)
        self.send_response(200); self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def send_csv(self, filename, headers, rows):
        output = io.StringIO(); writer = csv.writer(output)
        writer.writerow(headers); writer.writerows([[csv_safe(value) for value in row] for row in rows])
        raw = output.getvalue().encode("utf-8-sig")
        self.send_response(200); self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f"attachment; filename={filename}")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def nav(self, active):
        version = html.escape(os.environ.get("BUILD_VERSION", "dev"), quote=True)
        current_path = self.path if self.path.startswith("/") and not self.path.startswith("//") else "/"
        next_query = urllib.parse.urlencode({"next": current_path})
        other_language = "en" if self.language() == "fr" else "fr"
        language_label = "EN" if other_language == "en" else "FR"
        opposite_theme = "dark" if self.theme() == "light" else "light"
        theme_icon = "☾" if opposite_theme == "dark" else "☀"
        theme_title = self.t("Mode sombre") if opposite_theme == "dark" else self.t("Mode clair")
        return (f"<header class=top><a class=toplogo href=/><img src=/icon.png alt=''><span>UniFi Log Explorer <b>v{version}</b></span></a><nav class=menu>"
                f"<a class='{'active' if active=='overview' else ''}' href='/'>{self.t('Vue d’ensemble')}</a>"
                f"<a class='{'active' if active=='flows' else ''}' href='/flows'>Traffic Flows</a>"
                f"<a class='{'active' if active=='events' else ''}' href='/events'>CEF / Syslog</a>"
                f"<a class='{'active' if active=='settings' else ''}' href='/settings'>{self.t('Paramètres')}</a>"
                f"</nav><div class=headeractions><a id=language class=toggle href='/language?value={other_language}&amp;{next_query}' title='{self.t('Langue')}'>{language_label}</a>"
                f"<a id=theme class=toggle href='/theme?value={opposite_theme}&amp;{next_query}' title='{html.escape(theme_title)}'>{theme_icon}</a></div></header>")

    @staticmethod
    def bars(title, rows, filter_name=None):
        maximum = max([row["count"] for row in rows] or [1])
        lines = ""
        for row in rows:
            label = str(row["label"] or "Inconnu")
            inner = "<span class=barlabel title='{0}'>{0}</span><span class=bar><i style='width:{1:.1f}%'></i></span><b>{2}</b>".format(
                html.escape(label), row["count"] * 100 / maximum, row["count"])
            if filter_name:
                url = "/flows?" + urllib.parse.urlencode({"hours": 24, filter_name: label})
                lines += f"<a class='barline barlink' href='{html.escape(url)}'>{inner}</a>"
            else: lines += f"<div class=barline>{inner}</div>"
        return f"<section class=card><h2>{html.escape(title)}</h2><div class=bars>{lines}</div></section>"

    def timeline_chart(self, points):
        maximum = max([max(point["flows"], point["events"]) for point in points] or [1]) or 1
        columns = "".join(f"<span class=chartcol title='{time.strftime('%H:%M',time.localtime(point['time']))} · {point['flows']} flows · {point['events']} {self.t('Événements').lower()}'><i class=chartbar style='height:{max(2,point['flows']*100/maximum):.1f}%'></i><i class='chartbar events' style='height:{max(2,point['events']*100/maximum):.1f}%'></i></span>" for point in points)
        return f"<section class=card><h2>{self.t('Activité horaire')}</h2><div class=chart>" + columns + "</div><div class=legend><span><i></i>Traffic Flows</span><span><i class=events></i>CEF / Syslog</span></div></section>"

    def form(self):
        length = min(int(self.headers.get("Content-Length", "0")), 8192)
        return {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}

    def redirect(self, path, cookie=None):
        self.send_response(303); self.send_header("Location", self.url_for(path))
        if cookie: self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path); path = parsed.path
        if path == "/health":
            self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"OK"); return
        if not self.ingress_request():
            return self.send_error(403)
        if path in ("/logo.png", "/icon.png"):
            return self.send_asset("logo.png" if path == "/logo.png" else "icon.png")
        if path == "/theme":
            query = parse_qs(parsed.query); value = query.get("value", ["light"])[0]
            value = "dark" if value == "dark" else "light"
            target = query.get("next", ["/"])[0]
            if not target.startswith("/") or target.startswith("//"): target = "/"
            return self.redirect(target, f"ule_theme={value}; Path={self.ingress_base()}/; Max-Age=31536000; SameSite=Strict")
        if path == "/language":
            query = parse_qs(parsed.query); value = query.get("value", ["fr"])[0]
            value = "en" if value == "en" else "fr"
            target = query.get("next", ["/"])[0]
            if not target.startswith("/") or target.startswith("//"): target = "/"
            return self.redirect(target, f"ule_language={value}; Path={self.ingress_base()}/; Max-Age=31536000; SameSite=Strict")
        if path == "/export.json":
            payload = json.dumps(self.store.export(), indent=2).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Disposition", "attachment; filename=unifi-log-explorer-diagnostics.json"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload); return
        if path == "/flows.csv":
            filters = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            rows = []
            for row in self.store.export_flow_rows(filters):
                detail = row["detail"] if isinstance(row["detail"], dict) else {}
                rows.append((fmt_ms(row["flow_start_time"]), fmt_ms(row["flow_end_time"]), row["source_ip"], row["destination_ip"],
                             row["service"], row["action"], detail.get("direction"), detail.get("protocol"), row["id"]))
            return self.send_csv("unifi-traffic-flows.csv", ("start", "end", "source_ip", "destination_ip", "service", "action", "direction", "protocol", "id"), rows)
        if path == "/events.csv":
            filters = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            rows = [(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row["received_at"])), row["kind"], row["source_ip"], row["summary"], row["id"])
                    for row in self.store.export_event_rows(filters)]
            return self.send_csv("unifi-cef-syslog.csv", ("date", "type", "source_ip", "summary", "id"), rows)
        if path == "/":
            data = self.store.dashboard(); flow = self.store.flow_overview(24)
            counts = data["counts"]; counters = data["counters"]
            metrics = [(self.t("Flows sur 24 h"), flow["count"]), (self.t("Sources actives"), flow["sources"]),
                       (self.t("Destinations"), flow["destinations"]), (self.t("Flows archivés"), data["flow_stats"].get("count", 0)),
                       (self.t("Événements CEF"), counts.get("cef", 0)), (self.t("Messages Syslog"), counts.get("syslog", 0))]
            cards = ""
            for index, (label, value) in enumerate(metrics):
                target = f"/events?kind={'cef' if index == 4 else 'syslog'}&hours=24" if index >= 4 else "/flows?hours=24"
                cards += f"<a class='card clickcard' href='{target}'><div class=metric>{value:,}</div><div class=muted>{html.escape(label)}</div></a>"
            raw = self.store.setting("flow_collection_status"); collection = json.loads(raw) if raw else None
            if collection and collection.get("ok"):
                if self.language() == "en":
                    state = (f"<span class=good>● Collection operational</span> · last cycle: "
                             f"{collection.get('inserted')} new / {collection.get('fetched')} read / {collection.get('pages')} pages · {html.escape(collection.get('strategy',''))}")
                else:
                    state = (f"<span class=good>● Collecte opérationnelle</span> · dernier cycle : "
                             f"{collection.get('inserted')} nouveaux / {collection.get('fetched')} lus / {collection.get('pages')} pages · {html.escape(collection.get('strategy',''))}")
            elif collection: state = f"<span class=bad>● {'Failure' if self.language()=='en' else 'Échec'} : {html.escape(str(collection.get('error')))}</span>"
            else: state = f"<span class=muted>{self.t('Collecte en attente')}</span>"
            body = (self.nav("overview") + f"<div class=overviewhead><div><h1>{self.t('Vue d’ensemble')}</h1><p class=muted>{self.t('Activité réseau des dernières 24 heures')}</p></div>"
                    f"<section class='card statuscard'>{state}</section></div><div class=grid>{cards}</div><div class=twocol>"
                    + self.bars(self.t("Principaux clients"), flow["sources_top"], "q") + self.bars(self.t("Services"), flow["services"], "service")
                    + self.bars(self.t("Destinations"), flow["destinations_top"], "q") + self.bars(self.t("Actions"), flow["actions"], "action")
                    + "</div>" + self.timeline_chart(self.store.timeline()))
            return self.send_html(body, title="Vue d’ensemble · UniFi Log Explorer")
        if path == "/flows":
            raw_query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            result = self.store.query_flows(raw_query, raw_query.get("page", 1), raw_query.get("size", 50))
            def val(name): return html.escape(str(raw_query.get(name, "")), quote=True)
            options = "".join(f"<option value={n} {'selected' if result['hours']==n else ''}>{self.t(label)}</option>" for n,label in ((1,"1 heure"),(6,"6 heures"),(24,"24 heures"),(72,"3 jours"),(168,"7 jours"),(720,"30 jours")))
            directions = "".join(f"<option value='{v}' {'selected' if raw_query.get('direction')==v else ''}>{self.t(label)}</option>" for v,label in (("","Toutes"),("outgoing","Sortant"),("incoming","Entrant")))
            filters = (f"<form class=filters method=get><label>{self.t('Recherche')}<input name=q value='"+val("q")+"' placeholder='IP, client, domain…'></label>"
                       f"<label>{self.t('Source')}<input name=source value='"+val("source")+f"'></label><label>{self.t('Destination')}<input name=destination value='"+val("destination")+"'></label>"
                       f"<label>{self.t('Service')}<input name=service value='"+val("service")+f"'></label><label>{self.t('Direction')}<select name=direction>"+directions+"</select></label>"
                       f"<label>{self.t('Période')}<select name=hours>"+options+f"</select></label><button>{self.t('Filtrer')}</button></form>")
            rows = []
            for row in result["rows"]:
                detail = row["detail"] if isinstance(row["detail"], dict) else {}
                source = detail.get("source") if isinstance(detail.get("source"), dict) else {}
                destination = detail.get("destination") if isinstance(detail.get("destination"), dict) else {}
                direction = "→" if detail.get("direction") == "outgoing" else "←" if detail.get("direction") == "incoming" else "↔"
                rows.append(f"<tr><td>{fmt_ms(row['flow_end_time'])}</td><td class=wrap><b>{html.escape(party_label(detail,'source'))}</b><br><span class=muted>{html.escape(str(source.get('ip') or row['source_ip'] or '—'))}</span></td>"
                    f"<td class=arrow>{direction}</td><td class=wrap><b>{html.escape(party_label(detail,'destination'))}</b><br><span class=muted>{html.escape(str(destination.get('ip') or row['destination_ip'] or '—'))}</span></td>"
                    f"<td>{html.escape(str(row['service'] or detail.get('protocol') or '—'))}</td><td><span class=pill>{html.escape(str(row['action'] or '—'))}</span></td><td><a class=button href='/flow?id={urllib.parse.quote(row['id'])}'>{self.t('Détails')}</a></td></tr>")
            table = "".join(rows) or f"<tr><td class=empty colspan=7>{self.t('Aucun flow ne correspond à ces filtres.')}</td></tr>"
            query_without_page = dict(raw_query); query_without_page.pop("page", None)
            previous = query_link("/flows", query_without_page, page=result["page"]-1) if result["page"] > 1 else ""
            following = query_link("/flows", query_without_page, page=result["page"]+1) if result["page"] < result["pages"] else ""
            previous_link = f"<a class='button secondary' href='{html.escape(previous)}'>{self.t('Précédent')}</a>" if previous else ""
            following_link = f"<a class='button secondary' href='{html.escape(following)}'>{self.t('Suivant')}</a>" if following else ""
            count_label = "results · page" if self.language()=="en" else "résultats · page"
            pager = f"<div class=pager><span>{result['total']:,} {count_label} {result['page']} / {result['pages']}</span><span>{previous_link} {following_link}</span></div>"
            export_url = "/flows.csv?" + urllib.parse.urlencode({k:v for k,v in raw_query.items() if k != "page"})
            body = self.nav("flows") + f"<h1>Traffic Flows</h1><p class=muted>{self.t('Recherchez et inspectez les connexions archivées.')}</p>" + filters + f"<p><a class='button secondary' href='{html.escape(export_url)}'>{self.t('Exporter les résultats CSV')}</a></p><section class=card><div class=tablewrap><table><thead><tr><th>{self.t('Date')}</th><th>{self.t('Source')}</th><th></th><th>{self.t('Destination')}</th><th>{self.t('Service')}</th><th>{self.t('Action')}</th><th></th></tr></thead><tbody>{table}</tbody></table></div>{pager}</section>"
            return self.send_html(body, title="Traffic Flows · UniFi Log Explorer")
        if path == "/flow":
            flow_id = parse_qs(parsed.query).get("id", [""])[0]; row = self.store.flow_by_id(flow_id)
            if not row: return self.send_error(404)
            detail = row["detail"] if isinstance(row["detail"], dict) else {}
            source = detail.get("source") if isinstance(detail.get("source"), dict) else {}
            destination = detail.get("destination") if isinstance(detail.get("destination"), dict) else {}
            def endpoint(item):
                return f"<dl class=kv><dt>Nom</dt><dd>{html.escape(party_label({ 'item': item }, 'item'))}</dd><dt>Adresse IP</dt><dd>{html.escape(str(item.get('ip') or '—'))}</dd><dt>Port</dt><dd>{html.escape(str(item.get('port') or '—'))}</dd><dt>Région</dt><dd>{html.escape(str(item.get('region') or '—'))}</dd><dt>Zone</dt><dd>{html.escape(str(item.get('zone_name') or '—'))}</dd></dl>"
            duration = max(0, row["flow_end_time"] - row["flow_start_time"])
            route = f"<div class=route><b>{html.escape(party_label(detail,'source'))}</b><span class=arrow>→</span><b>{html.escape(party_label(detail,'destination'))}</b></div>"
            summary = f"<dl class=kv><dt>Début</dt><dd>{fmt_ms(row['flow_start_time'])}</dd><dt>Fin</dt><dd>{fmt_ms(row['flow_end_time'])}</dd><dt>Durée</dt><dd>{duration/1000:.1f} s</dd><dt>Service</dt><dd>{html.escape(str(row['service'] or '—'))}</dd><dt>Protocole</dt><dd>{html.escape(str(detail.get('protocol') or '—'))}</dd><dt>Action</dt><dd>{html.escape(str(row['action'] or '—'))}</dd><dt>Risque</dt><dd>{html.escape(str(detail.get('risk') or '—'))}</dd></dl>"
            body = self.nav("flows") + f"<p><a class='button secondary' href=/flows>← {self.t('Retour aux flows')}</a></p>" + f"<section class=card>{route}</section><div class=details><section class=card><h2>{self.t('Résumé')}</h2>{summary}</section><section class=card><h2>{self.t('Source')}</h2>{endpoint(source)}</section><section class=card><h2>{self.t('Destination')}</h2>{endpoint(destination)}</section></div><section class=card><h2>{self.t('Données UniFi complètes')}</h2><pre>{html.escape(json.dumps(detail,indent=2,ensure_ascii=False))}</pre></section>"
            return self.send_html(body, title=f"{self.t('Détail du flow')} · UniFi Log Explorer")
        if path == "/logs":
            target = "/events" + ("?" + parsed.query if parsed.query else "")
            return self.redirect(target)
        if path == "/events":
            raw_query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            result = self.store.query_events(raw_query, raw_query.get("page", 1), raw_query.get("size", 50))
            def event_val(name): return html.escape(str(raw_query.get(name, "")), quote=True)
            types = "".join(f"<option value='{value}' {'selected' if result['kind']==value else ''}>{self.t(label)}</option>" for value,label in (("","Toutes"),("cef","CEF"),("syslog","Syslog")))
            periods = "".join(f"<option value={value} {'selected' if result['hours']==value else ''}>{self.t(label)}</option>" for value,label in ((1,"1 heure"),(6,"6 heures"),(24,"24 heures"),(72,"3 jours"),(168,"7 jours"),(720,"30 jours")))
            filters = (f"<form class='filters eventfilters' method=get><label>{self.t('Recherche')}<input name=q value='"+event_val("q")+"' placeholder='Message, application, event…'></label>"
                       f"<label>{self.t('Type')}<select name=kind>"+types+f"</select></label><label>{self.t('Source')}<input name=source value='"+event_val("source")+"' placeholder='IP address'></label>"
                       f"<label>{self.t('Période')}<select name=hours>"+periods+f"</select></label><button>{self.t('Filtrer')}</button></form>")
            rows = "".join(f"<tr><td>{time.strftime('%d/%m/%Y %H:%M:%S',time.localtime(r['received_at']))}</td><td><span class=pill>{html.escape(r['kind'])}</span></td><td>{html.escape(r['source_ip'])}</td><td class=wrap>{html.escape(r['summary'])}</td><td><a class=button href='/event?id={r['id']}'>{self.t('Détails')}</a></td></tr>" for r in result["rows"])
            rows = rows or f"<tr><td class=empty colspan=5>{self.t('Aucun événement ne correspond à ces filtres.')}</td></tr>"
            query_without_page = dict(raw_query); query_without_page.pop("page", None)
            previous = query_link("/events", query_without_page, page=result["page"]-1) if result["page"] > 1 else ""
            following = query_link("/events", query_without_page, page=result["page"]+1) if result["page"] < result["pages"] else ""
            previous_link = f"<a class='button secondary' href='{html.escape(previous)}'>{self.t('Précédent')}</a>" if previous else ""
            following_link = f"<a class='button secondary' href='{html.escape(following)}'>{self.t('Suivant')}</a>" if following else ""
            count_label = "events · page" if self.language()=="en" else "événements · page"
            pager = f"<div class=pager><span>{result['total']:,} {count_label} {result['page']} / {result['pages']}</span><span>{previous_link} {following_link}</span></div>"
            export_url = "/events.csv?" + urllib.parse.urlencode({k:v for k,v in raw_query.items() if k != "page"})
            body = self.nav("events") + f"<h1>CEF / Syslog</h1><p class=muted>{self.t('Recherchez dans les événements transmis par vos équipements UniFi.')}</p>" + filters + f"<p><a class='button secondary' href='{html.escape(export_url)}'>{self.t('Exporter les résultats CSV')}</a></p><section class=card><div class=tablewrap><table><thead><tr><th>{self.t('Date')}</th><th>{self.t('Type')}</th><th>{self.t('Émetteur')}</th><th>{self.t('Résumé')}</th><th></th></tr></thead><tbody>" + rows + "</tbody></table></div>" + pager + "</section>"
            return self.send_html(body, title="CEF / Syslog · UniFi Log Explorer")
        if path == "/event":
            event_id = parse_qs(parsed.query).get("id", [""])[0]; event = self.store.event_by_id(event_id)
            if not event: return self.send_error(404)
            detail = event["detail"] if isinstance(event["detail"], dict) else {"value": event["detail"]}
            summary = (f"<dl class=kv><dt>Date</dt><dd>{time.strftime('%d/%m/%Y %H:%M:%S',time.localtime(event['received_at']))}</dd>"
                       f"<dt>Type</dt><dd>{html.escape(event['kind'])}</dd><dt>Émetteur</dt><dd>{html.escape(event['source_ip'])}</dd>"
                       f"<dt>Résumé</dt><dd>{html.escape(event['summary'])}</dd></dl>")
            body = self.nav("events") + f"<p><a class='button secondary' href=/events>← {self.t('Retour aux événements')}</a></p>" + f"<div class=details><section class=card><h2>{self.t('Événement')}</h2>{summary}</section><section class=card><h2>{self.t('Données complètes')}</h2><pre>{html.escape(json.dumps(detail,indent=2,ensure_ascii=False))}</pre></section></div>"
            return self.send_html(body, title=f"{self.t('Détail de l’événement')} · UniFi Log Explorer")
        if path == "/settings":
            csrf = html.escape(CSRF_TOKEN)
            raw_probe = self.store.setting("flow_probe_result"); probe = json.loads(raw_probe) if raw_probe else None
            if probe and probe.get("ok"):
                tested = time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(probe.get("tested_at", 0)))
                probe_state = (f"<span class=good>● Connection successful</span><br><span class=muted>Last test: {tested} · window total: {probe.get('total', '—')}</span>" if self.language()=="en" else
                               f"<span class=good>● Connexion réussie</span><br><span class=muted>Dernier test : {tested} · total de la fenêtre : {probe.get('total', '—')}</span>")
            elif probe:
                failure = "Failure" if self.language() == "en" else "Échec"
                unknown = "unknown error" if self.language() == "en" else "erreur inconnue"
                probe_state = f"<span class=bad>● {failure} : {html.escape(str(probe.get('error', unknown)))}</span>"
            else: probe_state = f"<span class=muted>{self.t('Aucun test effectué.')}</span>"
            disabled = "disabled" if not self.store.options.get("unifi_api_key") else ""
            api = ("<section class=card><h2>API UniFi</h2><p>" + probe_state + "</p>"
                   f"<form method=post action=/probe><input type=hidden name=csrf value='{csrf}'><button {disabled}>Tester la connexion</button></form>"
                   "<p class=muted>Le test lit au maximum un flow récent et ne le conserve pas. La clé API n’est jamais affichée.</p></section>")
            diagnostic = ("<section class=card><h2>Diagnostic</h2><p class=muted>L’export contient les compteurs et événements CEF/Syslog, sans les Traffic Flows ni la clé API.</p>"
                          "<a class=button href=/export.json>Exporter le diagnostic JSON</a></section>")
            options = self.store.options
            sources = ", ".join(html.escape(value) for value in sorted(options.get("allowed_source_ips", []))) or "—"
            verify = self.t("Activée" if options.get("verify_ssl") else "Désactivée")
            enabled = self.t("Activée" if options.get("flow_collection_enabled") else "Désactivée")
            hour_unit = "hours" if self.language() == "en" else "heures"
            record_unit = "records" if self.language() == "en" else "enregistrements"
            second_unit = "seconds" if self.language() == "en" else "secondes"
            config = ("<section class=card><h2>Configuration</h2><p class=muted>Lecture seule · les modifications s’effectuent dans les options de l’App Home Assistant.</p><div class=readonly><dl class=kv>"
                      f"<dt>Sources autorisées</dt><dd>{sources}</dd><dt>Rétention</dt><dd>{options.get('retention_hours', '—')} {hour_unit}</dd>"
                      f"<dt>Limite</dt><dd>{options.get('max_records', '—')} {record_unit}</dd><dt>Collecte des flows</dt><dd>{enabled}</dd>"
                      f"<dt>Fréquence</dt><dd>{options.get('flow_poll_interval_seconds', '—')} {second_unit}</dd><dt>URL UniFi</dt><dd>{html.escape(str(options.get('unifi_base_url', '—')))}</dd>"
                      f"<dt>Site</dt><dd>{html.escape(str(options.get('unifi_site_slug', '—')))}</dd><dt>Vérification TLS</dt><dd>{verify}</dd></dl></div></section>")
            operation = self.store.operational_status(); collection = operation["collection"]
            if collection and collection.get("ok"):
                age = max(0, int(time.time()) - int(collection.get("time", 0)))
                stale_after = max(600, int(options.get("flow_poll_interval_seconds", 120)) * 3)
                if self.language() == "en": collection_state = f"<span class={'bad' if age > stale_after else 'good'}>● {'Delayed' if age > stale_after else 'Operational'}</span> · last success {age // 60} min ago"
                else: collection_state = f"<span class={'bad' if age > stale_after else 'good'}>● {'En retard' if age > stale_after else 'Opérationnelle'}</span> · dernier succès il y a {age // 60} min"
            elif collection:
                failure = "Failure" if self.language() == "en" else "Échec"
                unknown = "unknown" if self.language() == "en" else "inconnu"
                collection_state = f"<span class=bad>● {failure} : {html.escape(str(collection.get('error', unknown)))}</span>"
            else: collection_state = f"<span class=muted>{self.t('Aucun cycle enregistré.')}</span>"
            reconciliation = operation["last_reconciliation"]
            if reconciliation:
                next_reconciliation = reconciliation + FlowCollector.RECONCILE_INTERVAL_SECONDS
                reconciliation_text = time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(next_reconciliation))
            else: reconciliation_text = "—"
            monitoring = ("<section class=card><h2>État et stockage</h2><p class=statusnote>" + collection_state + "</p><dl class=kv>"
                          f"<dt>Base SQLite</dt><dd>{fmt_bytes(operation['database_bytes'], self.language())}</dd><dt>Traffic Flows</dt><dd>{operation['flows']['count']:,}</dd>"
                          f"<dt>Événements</dt><dd>{operation['events']['count']:,}</dd><dt>Prochaine réconciliation</dt><dd>{reconciliation_text}</dd></dl></section>")
            maintenance_card = ("<section class='card danger'><h2>Maintenance des données</h2><p class=muted>Cette suppression est définitive et ne modifie pas les options de collecte.</p>"
                                f"<form class=stackform method=post action=/purge><input type=hidden name=csrf value='{csrf}'>"
                                "<label>Données à supprimer<select name=target required><option value=events>Événements CEF / Syslog</option><option value=flows>Traffic Flows</option></select></label>"
                                f"<label>{'Enter PURGE to confirm' if self.language()=='en' else 'Saisissez PURGER pour confirmer'}<input name=confirm required autocomplete=off></label><button>Supprimer les données</button></form></section>")
            body = self.nav("settings") + "<h1>Paramètres</h1><p class=muted>Outils et état de la configuration locale.</p><div class=settingsgrid>" + monitoring + api + diagnostic + config + maintenance_card + "</div>"
            return self.send_html(body, title="Paramètres · UniFi Log Explorer")
        return self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path; form = self.form()
        if not self.ingress_request():
            return self.send_error(403)
        if not hmac.compare_digest(form.get("csrf", ""), CSRF_TOKEN):
            return self.send_error(403)
        if path == "/purge":
            if form.get("confirm") not in ("PURGER", "PURGE") or form.get("target") not in ("events", "flows"):
                content = f"<h1>{self.t('Purge refusée')}</h1><p class=bad>{self.t('Confirmation incorrecte. Aucune donnée n’a été supprimée.')}</p><a class=button href=/settings>{self.t('Retour')}</a>"
                return self.send_html(content, 400)
            count = self.store.purge(form["target"])
            self.store.set_setting("maintenance_notice", json.dumps({"time": int(time.time()), "target": form["target"], "count": count}))
            return self.redirect("/settings")
        if path == "/probe":
            try:
                result = flow_probe(self.store.options)
            except Exception as exc:
                logging.warning("Traffic Flows API probe failed: %s", exc)
                result = {"ok": False, "tested_at": int(time.time()), "error": str(exc)}
            self.store.set_setting("flow_probe_result", json.dumps(result, separators=(",", ":")))
            return self.redirect("/settings")
        self.send_error(403)


def maintenance(store):
    while True:
        store.prune()
        time.sleep(300)


def main():
    options = load_options()
    logging.basicConfig(level=getattr(logging, str(options["log_level"]).upper()), format="%(asctime)s %(levelname)s %(message)s")
    if options.get("unifi_api_key"):
        if options.get("verify_ssl"):
            logging.info("Authentification TLS UniFi : validation du certificat système activée")
        else:
            logging.info("Authentification TLS UniFi : empreinte SHA-256 épinglée activée")
    store = Store(options)
    Collector("cef", CEF_PORT, store, parse_syslog_or_cef).start()
    threading.Thread(target=maintenance, args=(store,), daemon=True).start()
    if options.get("flow_collection_enabled"):
        if not options.get("unifi_api_key"):
            logging.warning("Traffic Flows collection enabled but no UniFi API key is configured")
        else:
            FlowCollector(store).start()
    Web.store = store
    logging.info("Web interface listening on TCP %s; allowed sources: %s", WEB_PORT, ", ".join(sorted(options["allowed_source_ips"])))
    ThreadingHTTPServer(("", WEB_PORT), Web).serve_forever()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--prepare-secrets":
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        prepare_secrets()
    else:
        main()
