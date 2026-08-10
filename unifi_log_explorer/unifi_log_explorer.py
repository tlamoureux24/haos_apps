#!/usr/bin/env python3
"""UniFi Log Explorer local collector and network activity explorer."""

from __future__ import annotations

import hashlib
import hmac
import html
import ipaddress
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
                "max_records": 250000, "session_timeout_minutes": 60,
                "unifi_base_url": "https://192.168.1.1", "unifi_site_slug": "default",
                "unifi_api_key": "", "verify_ssl": False,
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
    return defaults


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
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
        headers={"Accept": "application/json", "Content-Type": "application/json",
                 "X-API-KEY": str(options.get("unifi_api_key") or decrypt_api_key())})
    context = ssl.create_default_context() if options.get("verify_ssl") else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, context=context, timeout=15) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc
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


SESSIONS = {}
SESSION_LOCK = threading.Lock()


def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def password_valid(password, encoded):
    try:
        _, salt, expected = encoded.split("$")
        actual = password_hash(password, bytes.fromhex(salt)).split("$")[2]
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


STYLE = """
:root{color-scheme:light;--bg:#f4f7fa;--surface:#fff;--surface2:#edf3f8;--text:#17212b;--muted:#64748b;--line:#d8e1ea;--accent:#0787a8;--accent2:#dff5fa;--good:#16845b;--bad:#c43f55;--shadow:0 5px 22px #1e3a5f12}
html[data-theme=dark]{color-scheme:dark;--bg:#0d1420;--surface:#172235;--surface2:#202c41;--text:#e7edf5;--muted:#a4b2c6;--line:#30415d;--accent:#52c9e6;--accent2:#173b4a;--good:#50c895;--bad:#ff8293;--shadow:none}
*{box-sizing:border-box}body{font:15px system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);margin:0}main{max-width:1440px;margin:auto;padding:24px}.top{display:flex;align-items:center;gap:20px;margin-bottom:22px}.brand{font-size:25px;font-weight:800;color:var(--accent);margin-right:auto}.nav{display:flex;gap:5px;flex-wrap:wrap}.nav a,.linkbtn{color:var(--text);text-decoration:none;padding:9px 12px;border-radius:7px}.nav a:hover,.nav .active{background:var(--accent2);color:var(--accent)}h1{font-size:28px;margin:10px 0 4px}h2{margin:0 0 16px;font-size:19px}.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:18px;box-shadow:var(--shadow)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:12px;margin:16px 0}.metric{font-size:28px;font-variant-numeric:tabular-nums}.muted{color:var(--muted)}.bad{color:var(--bad)}.good{color:var(--good)}button,.button{display:inline-block;background:var(--accent);color:#fff;border:0;border-radius:7px;padding:9px 14px;font-weight:700;text-decoration:none;cursor:pointer}button.secondary,.button.secondary{background:var(--surface2);color:var(--text);border:1px solid var(--line)}form.inline{display:inline}.filters{display:grid;grid-template-columns:2fr repeat(5,minmax(120px,1fr)) auto;gap:10px;align-items:end;margin:16px 0}.filters label{font-size:12px;color:var(--muted)}input,select{display:block;width:100%;margin-top:5px;padding:9px 10px;color:var(--text);background:var(--surface);border:1px solid var(--line);border-radius:7px}.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:10px}table{width:100%;border-collapse:collapse;white-space:nowrap}td,th{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line)}th{font-size:12px;color:var(--muted);background:var(--surface2)}tr:last-child td{border:0}td.wrap{white-space:normal;min-width:160px}.pill{display:inline-block;padding:3px 8px;border-radius:999px;background:var(--surface2);font-size:12px}.bars{display:grid;gap:9px}.barline{display:grid;grid-template-columns:minmax(90px,1fr) 3fr 55px;gap:10px;align-items:center}.bar{height:8px;border-radius:5px;background:var(--surface2);overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}.twocol{display:grid;grid-template-columns:1fr 1fr;gap:12px}.pager{display:flex;justify-content:space-between;align-items:center;margin-top:14px}.route{display:flex;align-items:center;gap:12px;flex-wrap:wrap;font-size:17px}.arrow{color:var(--accent);font-size:22px}.details{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}.kv{display:grid;grid-template-columns:120px 1fr;gap:7px 12px}.kv dt{color:var(--muted)}.kv dd{margin:0;overflow-wrap:anywhere}pre{overflow:auto;background:var(--surface2);padding:14px;border-radius:8px;font-size:12px}.empty{text-align:center;padding:38px;color:var(--muted)}@media(max-width:1100px){main{padding:14px}.top{align-items:flex-start;flex-wrap:wrap}.filters{grid-template-columns:1fr 1fr}.twocol{grid-template-columns:1fr}}@media(max-width:560px){.filters{grid-template-columns:1fr}.brand{width:100%}}
input[type=hidden]{display:none!important}.barlink{color:var(--text);text-decoration:none;border-radius:6px}.barlink:hover{background:var(--accent2)}.clickcard{display:block;color:var(--text);text-decoration:none;transition:transform .15s,border-color .15s}.clickcard:hover{transform:translateY(-2px);border-color:var(--accent)}.authwrap{min-height:calc(100vh - 48px);display:grid;place-items:center}.authbox{width:min(430px,100%)}.authbrand{text-align:center;margin-bottom:18px}.authbrand img{width:96px;height:96px;border-radius:22px}.authbrand h1{margin:10px 0 3px;color:var(--accent)}.authcard{padding:24px}.authcard button{width:100%;margin-top:4px}.publictheme{position:fixed;right:20px;top:16px;color:var(--text);text-decoration:none;padding:9px 12px;border-radius:7px;background:var(--surface)}
.toplogo{display:flex;align-items:center;gap:10px;color:var(--accent);text-decoration:none;font-size:25px;font-weight:800;margin-right:auto}.toplogo img{width:42px;height:42px;border-radius:10px}.menu{display:flex;align-items:center;gap:5px;position:relative;z-index:2}.menu a{display:block;position:relative;color:var(--text);text-decoration:none;padding:9px 12px;border-radius:7px}.menu a:hover,.menu a.active{background:var(--accent2);color:var(--accent)}.logout{margin:0;position:relative;z-index:2}.logfilters{display:flex;gap:8px;margin:16px 0}.logfilters a{background:var(--surface);color:var(--text);border:1px solid var(--line)}.logfilters a.active{background:var(--accent);color:#fff;border-color:var(--accent)}@media(max-width:800px){.menu{width:100%;overflow-x:auto}.toplogo{width:100%}}
"""


def fmt_ms(value):
    if not value: return "—"
    return time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(value / 1000))


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

    def send_html(self, body, status=200, headers=None, title="UniFi Log Explorer"):
        raw = (f"<!doctype html><html lang=fr data-theme='{self.theme()}'><head><meta charset=utf-8>"
               f"<meta name=viewport content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title>"
               "<link rel=icon type=image/png href=/favicon.png>"
               f"<style>{STYLE}</style></head><body><main>{body}</main></body></html>").encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        for key, value in (headers or {}).items(): self.send_header(key, value)
        self.end_headers(); self.wfile.write(raw)

    def send_asset(self, filename):
        try: raw = (ASSET_DIR / filename).read_bytes()
        except OSError: return self.send_error(404)
        self.send_response(200); self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "public, max-age=86400")
        self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def auth_page(self, content, title):
        opposite = "dark" if self.theme() == "light" else "light"
        label = "☾ Mode sombre" if opposite == "dark" else "☀ Mode clair"
        theme_url = "/theme?" + urllib.parse.urlencode({"value": opposite, "next": self.path})
        return (f"<a class=publictheme href='{html.escape(theme_url)}'>{label}</a><div class=authwrap><div class=authbox>"
                "<div class=authbrand><img src=/logo.png alt='Logo UniFi Log Explorer'><h1>UniFi Log Explorer</h1>"
                f"<div class=muted>{html.escape(title)}</div></div><section class='card authcard'>{content}</section></div></div>")

    def nav(self, active, session):
        csrf = html.escape(session["csrf"])
        opposite = "dark" if self.theme() == "light" else "light"
        theme_label = "☾ Sombre" if opposite == "dark" else "☀ Clair"
        theme_url = "/theme?" + urllib.parse.urlencode({"value": opposite, "next": self.path})
        return ("<header class=top><a class=toplogo href=/><img src=/icon.png alt=''><span>UniFi Log Explorer</span></a><nav class=menu>"
                f"<a class={'active' if active=='overview' else ''} href=/>Vue d’ensemble</a>"
                f"<a class={'active' if active=='flows' else ''} href=/flows>Traffic Flows</a>"
                f"<a class={'active' if active=='logs' else ''} href=/logs>Journaux</a>"
                f"<a href='{html.escape(theme_url)}'>{theme_label}</a>"
                "</nav>"
                f"<form class=logout method=post action=/logout><input type=hidden name=csrf value='{csrf}'><button>Déconnexion</button></form></header>")

    @staticmethod
    def bars(title, rows, filter_name=None):
        maximum = max([row["count"] for row in rows] or [1])
        lines = ""
        for row in rows:
            label = str(row["label"] or "Inconnu")
            inner = "<span title='{0}'>{0}</span><span class=bar><i style='width:{1:.1f}%'></i></span><b>{2}</b>".format(
                html.escape(label), row["count"] * 100 / maximum, row["count"])
            if filter_name:
                url = "/flows?" + urllib.parse.urlencode({"hours": 24, filter_name: label})
                lines += f"<a class='barline barlink' href='{html.escape(url)}'>{inner}</a>"
            else: lines += f"<div class=barline>{inner}</div>"
        return f"<section class=card><h2>{html.escape(title)}</h2><div class=bars>{lines}</div></section>"

    def form(self):
        length = min(int(self.headers.get("Content-Length", "0")), 8192)
        return {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}

    def session(self):
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        token = jar.get("ule_session")
        if not token: return None
        with SESSION_LOCK:
            session = SESSIONS.get(token.value)
            if not session: return None
            if time.time() - session["last"] > int(self.store.options["session_timeout_minutes"]) * 60:
                SESSIONS.pop(token.value, None); return None
            session["last"] = time.time(); return session

    def redirect(self, path, cookie=None):
        self.send_response(303); self.send_header("Location", path)
        if cookie: self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path); path = parsed.path
        if path == "/health":
            self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"OK"); return
        if path in ("/logo.png", "/icon.png", "/favicon.png"):
            return self.send_asset("logo.png" if path == "/logo.png" else "icon.png")
        if path == "/theme":
            query = parse_qs(parsed.query); value = query.get("value", ["light"])[0]
            value = "dark" if value == "dark" else "light"
            target = query.get("next", ["/"])[0]
            if not target.startswith("/") or target.startswith("//"): target = "/"
            return self.redirect(target, f"ule_theme={value}; Path=/; Max-Age=31536000; SameSite=Strict")
        if not self.store.setting("admin_hash"):
            form = "<form method=post action=/setup><label>Nom d’utilisateur<input name=username required minlength=3 maxlength=64 autocomplete=username></label><label>Mot de passe<input type=password name=password required minlength=12 autocomplete=new-password></label><label>Confirmation<input type=password name=confirm required minlength=12 autocomplete=new-password></label><button>Créer le compte</button></form>"
            return self.send_html(self.auth_page(form, "Créer le compte administrateur"))
        session = self.session()
        if path == "/login":
            form = "<form method=post action=/login><label>Utilisateur<input name=username autocomplete=username required autofocus></label><label>Mot de passe<input type=password name=password autocomplete=current-password required></label><button>Connexion</button></form>"
            return self.send_html(self.auth_page(form, "Connexion à votre espace local"))
        if not session: return self.redirect("/login")
        if path == "/export.json":
            payload = json.dumps(self.store.export(), indent=2).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Disposition", "attachment; filename=unifi-log-explorer-diagnostics.json"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload); return
        if path == "/":
            data = self.store.dashboard(); flow = self.store.flow_overview(24)
            counts = data["counts"]; counters = data["counters"]
            metrics = [("Flows sur 24 h", flow["count"]), ("Sources actives", flow["sources"]),
                       ("Destinations", flow["destinations"]), ("Flows archivés", data["flow_stats"].get("count", 0)),
                       ("Événements CEF", counts.get("cef", 0)), ("Messages Syslog", counts.get("syslog", 0))]
            cards = ""
            for index, (label, value) in enumerate(metrics):
                target = f"/logs?kind={'cef' if index == 4 else 'syslog'}" if index >= 4 else "/flows?hours=24"
                cards += f"<a class='card clickcard' href='{target}'><div class=metric>{value:,}</div><div class=muted>{html.escape(label)}</div></a>"
            raw = self.store.setting("flow_collection_status"); collection = json.loads(raw) if raw else None
            if collection and collection.get("ok"):
                state = (f"<span class=good>● Collecte opérationnelle</span> · dernier cycle : "
                         f"{collection.get('inserted')} nouveaux / {collection.get('fetched')} lus / "
                         f"{collection.get('pages')} pages · {html.escape(collection.get('strategy',''))}")
            elif collection: state = f"<span class=bad>● Échec : {html.escape(str(collection.get('error')))}</span>"
            else: state = "<span class=muted>Collecte en attente</span>"
            body = (self.nav("overview", session) + "<h1>Vue d’ensemble</h1><p class=muted>Activité réseau des dernières 24 heures</p>"
                    f"<div class=grid>{cards}</div><section class=card>{state}</section><div class=twocol>"
                    + self.bars("Principaux clients", flow["sources_top"], "q") + self.bars("Services", flow["services"], "service")
                    + self.bars("Destinations", flow["destinations_top"], "q") + self.bars("Actions", flow["actions"], "action")
                    + "</div>")
            return self.send_html(body, title="Vue d’ensemble · UniFi Log Explorer")
        if path == "/flows":
            raw_query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
            result = self.store.query_flows(raw_query, raw_query.get("page", 1), raw_query.get("size", 50))
            def val(name): return html.escape(str(raw_query.get(name, "")), quote=True)
            options = "".join(f"<option value={n} {'selected' if result['hours']==n else ''}>{label}</option>" for n,label in ((1,"1 heure"),(6,"6 heures"),(24,"24 heures"),(72,"3 jours"),(168,"7 jours"),(720,"30 jours")))
            directions = "".join(f"<option value='{v}' {'selected' if raw_query.get('direction')==v else ''}>{label}</option>" for v,label in (("","Toutes"),("outgoing","Sortant"),("incoming","Entrant")))
            filters = ("<form class=filters method=get><label>Recherche<input name=q value='"+val("q")+"' placeholder='IP, client, domaine…'></label>"
                       "<label>Source<input name=source value='"+val("source")+"'></label><label>Destination<input name=destination value='"+val("destination")+"'></label>"
                       "<label>Service<input name=service value='"+val("service")+"'></label><label>Direction<select name=direction>"+directions+"</select></label>"
                       "<label>Période<select name=hours>"+options+"</select></label><button>Filtrer</button></form>")
            rows = []
            for row in result["rows"]:
                detail = row["detail"] if isinstance(row["detail"], dict) else {}
                source = detail.get("source") if isinstance(detail.get("source"), dict) else {}
                destination = detail.get("destination") if isinstance(detail.get("destination"), dict) else {}
                direction = "→" if detail.get("direction") == "outgoing" else "←" if detail.get("direction") == "incoming" else "↔"
                rows.append(f"<tr><td>{fmt_ms(row['flow_end_time'])}</td><td class=wrap><b>{html.escape(party_label(detail,'source'))}</b><br><span class=muted>{html.escape(str(source.get('ip') or row['source_ip'] or '—'))}</span></td>"
                    f"<td class=arrow>{direction}</td><td class=wrap><b>{html.escape(party_label(detail,'destination'))}</b><br><span class=muted>{html.escape(str(destination.get('ip') or row['destination_ip'] or '—'))}</span></td>"
                    f"<td>{html.escape(str(row['service'] or detail.get('protocol') or '—'))}</td><td><span class=pill>{html.escape(str(row['action'] or '—'))}</span></td><td><a class=button href='/flow?id={urllib.parse.quote(row['id'])}'>Détails</a></td></tr>")
            table = "".join(rows) or "<tr><td class=empty colspan=7>Aucun flow ne correspond à ces filtres.</td></tr>"
            query_without_page = dict(raw_query); query_without_page.pop("page", None)
            previous = query_link("/flows", query_without_page, page=result["page"]-1) if result["page"] > 1 else ""
            following = query_link("/flows", query_without_page, page=result["page"]+1) if result["page"] < result["pages"] else ""
            pager = f"<div class=pager><span>{result['total']:,} résultats · page {result['page']} / {result['pages']}</span><span>{f'<a class=button secondary href={html.escape(previous)}>Précédent</a>' if previous else ''} {f'<a class=button secondary href={html.escape(following)}>Suivant</a>' if following else ''}</span></div>"
            body = self.nav("flows", session) + "<h1>Traffic Flows</h1><p class=muted>Recherchez et inspectez les connexions archivées.</p>" + filters + f"<section class=card><div class=tablewrap><table><thead><tr><th>Date</th><th>Source</th><th></th><th>Destination</th><th>Service</th><th>Action</th><th></th></tr></thead><tbody>{table}</tbody></table></div>{pager}</section>"
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
            body = self.nav("flows", session) + "<p><a class='button secondary' href=/flows>← Retour aux flows</a></p>" + f"<section class=card>{route}</section><div class=details><section class=card><h2>Résumé</h2>{summary}</section><section class=card><h2>Source</h2>{endpoint(source)}</section><section class=card><h2>Destination</h2>{endpoint(destination)}</section></div><section class=card><h2>Données UniFi complètes</h2><pre>{html.escape(json.dumps(detail,indent=2,ensure_ascii=False))}</pre></section>"
            return self.send_html(body, title="Détail du flow · UniFi Log Explorer")
        if path == "/logs":
            kind = parse_qs(parsed.query).get("kind", [""])[0]
            if kind not in ("cef", "syslog"): kind = ""
            records = self.store.recent_records(kind)
            rows = "".join(f"<tr><td>{time.strftime('%d/%m/%Y %H:%M:%S',time.localtime(r['received_at']))}</td><td><span class=pill>{html.escape(r['kind'])}</span></td><td>{html.escape(r['source_ip'])}</td><td class=wrap>{html.escape(r['summary'])}</td></tr>" for r in records)
            rows = rows or "<tr><td class=empty colspan=4>Aucun événement pour ce filtre.</td></tr>"
            tabs = "<div class=logfilters>" + "".join(f"<a class='button {'active' if kind == value else ''}' href='{url}'>" + label + "</a>" for value,url,label in (("","/logs","Tous"),("cef","/logs?kind=cef","CEF"),("syslog","/logs?kind=syslog","Syslog"))) + "</div>"
            body = self.nav("logs", session) + "<h1>Journaux</h1><p class=muted>Les 100 derniers événements Syslog et CEF.</p>" + tabs + "<section class=card><div class=tablewrap><table><thead><tr><th>Date</th><th>Type</th><th>Émetteur</th><th>Résumé</th></tr></thead><tbody>" + rows + "</tbody></table></div></section><p><a class=button href=/export.json>Exporter le diagnostic JSON</a></p>"
            return self.send_html(body, title="Journaux · UniFi Log Explorer")
        return self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path; form = self.form()
        if path == "/setup" and not self.store.setting("admin_hash"):
            username = form.get("username", "").strip(); password = form.get("password", "")
            if len(username) < 3 or len(password) < 12 or password != form.get("confirm"):
                return self.send_html("<h1>Configuration refusée</h1><p>Utilisateur ≥ 3 caractères, mot de passe ≥ 12 caractères et confirmation identique.</p><a href=/ >Retour</a>", 400)
            self.store.set_setting("admin_user", username); self.store.set_setting("admin_hash", password_hash(password)); return self.redirect("/login")
        if path == "/login":
            if hmac.compare_digest(form.get("username", ""), self.store.setting("admin_user") or "") and password_valid(form.get("password", ""), self.store.setting("admin_hash")):
                token = secrets.token_urlsafe(32)
                with SESSION_LOCK: SESSIONS[token] = {"last": time.time(), "csrf": secrets.token_urlsafe(24)}
                return self.redirect("/", f"ule_session={token}; Path=/; HttpOnly; SameSite=Strict")
            time.sleep(0.5); return self.send_html("<h1>Connexion refusée</h1><a href=/login>Réessayer</a>", 401)
        session = self.session()
        if path == "/probe" and session and hmac.compare_digest(form.get("csrf", ""), session["csrf"]):
            try:
                result = flow_probe(self.store.options)
            except Exception as exc:
                logging.warning("Traffic Flows API probe failed: %s", exc)
                result = {"ok": False, "tested_at": int(time.time()), "error": str(exc)}
            self.store.set_setting("flow_probe_result", json.dumps(result, separators=(",", ":")))
            return self.redirect("/")
        if path == "/logout" and session and hmac.compare_digest(form.get("csrf", ""), session["csrf"]):
            jar = cookies.SimpleCookie(self.headers.get("Cookie", "")); token = jar.get("ule_session")
            if token:
                with SESSION_LOCK: SESSIONS.pop(token.value, None)
            return self.redirect("/login", "ule_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict")
        self.send_error(403)


def maintenance(store):
    while True:
        store.prune()
        time.sleep(300)


def main():
    options = load_options()
    logging.basicConfig(level=getattr(logging, str(options["log_level"]).upper()), format="%(asctime)s %(levelname)s %(message)s")
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
