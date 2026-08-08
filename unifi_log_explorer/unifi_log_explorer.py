#!/usr/bin/env python3
"""UniFi Log Explorer diagnostic collector (phase 1)."""

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
import struct
import threading
import time
from collections import Counter
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DATA = Path(os.environ.get("UNIFI_LOG_EXPLORER_DATA", "/data"))
DB_PATH = DATA / "diagnostics.db"
OPTIONS_PATH = DATA / "options.json"
WEB_PORT = 8090
IPFIX_PORT = 2055
CEF_PORT = 5514
CEF_HEADER = re.compile(r"(?:<\d+>)?\s*CEF:(\d+)\|((?:\\\||[^|])*)\|((?:\\\||[^|])*)\|((?:\\\||[^|])*)\|((?:\\\||[^|])*)\|((?:\\\||[^|])*)\|([^|]*)\|(.*)")
CEF_PAIR = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=((?:\\[=\\]|[^ ])*(?: (?![A-Za-z][A-Za-z0-9_]*=)[^ ]*)*)")
SYSLOG_HEADER = re.compile(r"^<(\d{1,3})>([A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(\S+)\s+(.*)$")
SYSLOG_TAG = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[(\d+)\])?:\s*(.*)$", re.DOTALL)
IPFIX_NAMES = {1: "octetDeltaCount", 2: "packetDeltaCount", 4: "protocolIdentifier",
               7: "sourceTransportPort", 8: "sourceIPv4Address", 11: "destinationTransportPort",
               12: "destinationIPv4Address", 21: "flowEndSysUpTime", 22: "flowStartSysUpTime",
               27: "sourceIPv6Address", 28: "destinationIPv6Address", 58: "vlanId",
               60: "ipVersion", 61: "flowDirection", 152: "flowStartMilliseconds",
               153: "flowEndMilliseconds"}


def load_options():
    defaults = {"allowed_source_ips": ["192.168.1.1"], "retention_hours": 168,
                "max_records": 250000, "session_timeout_minutes": 60,
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
    return defaults


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
            self.db.commit()

    def dashboard(self):
        with self.lock:
            counts = {r["kind"]: r["n"] for r in self.db.execute("SELECT kind,count(*) n FROM records GROUP BY kind")}
            counters = {r["key"]: r["value"] for r in self.db.execute("SELECT key,value FROM counters")}
            recent = [dict(r) for r in self.db.execute("SELECT id,received_at,kind,source_ip,summary FROM records ORDER BY id DESC LIMIT 100")]
            cef_types = [dict(r) for r in self.db.execute("SELECT json_extract(detail,'$.name') name,count(*) count FROM records WHERE kind='cef' GROUP BY name ORDER BY count DESC LIMIT 20")]
            syslog_apps = [dict(r) for r in self.db.execute("SELECT json_extract(detail,'$.app_name') app_name,count(*) count FROM records WHERE kind='syslog' GROUP BY app_name ORDER BY count DESC LIMIT 20")]
            templates = [dict(r) for r in self.db.execute("SELECT json_extract(detail,'$.template_id') template_id,count(*) count FROM records WHERE kind='ipfix_template' GROUP BY template_id ORDER BY count DESC")]
            rejected_sources = {}
            for row in self.db.execute("SELECT key,value FROM counters WHERE key LIKE 'cef_rejected_source:%' OR key LIKE 'ipfix_rejected_source:%'"):
                address = row["key"].split(":", 1)[1]
                rejected_sources[address] = rejected_sources.get(address, 0) + row["value"]
        return {"counts": counts, "counters": counters, "recent": recent,
                "cef_types": cef_types, "syslog_apps": syslog_apps, "templates": templates,
                "rejected_sources": rejected_sources,
                "allowed_source_ips": sorted(self.options["allowed_source_ips"]),
                "retention_hours": self.options["retention_hours"], "max_records": self.options["max_records"]}

    def export(self):
        with self.lock:
            rows = [dict(r) for r in self.db.execute("SELECT received_at,kind,summary,detail FROM records ORDER BY id")]
        for row in rows:
            row["detail"] = json.loads(row["detail"])
        diagnostics = self.dashboard()
        for recent in diagnostics["recent"]:
            recent.pop("source_ip", None)
        diagnostics.pop("allowed_source_ips", None)
        return {"generated_at": int(time.time()), "diagnostics": diagnostics, "records": rows}


def parse_ipfix(data):
    if len(data) < 16:
        raise ValueError("packet shorter than IPFIX header")
    version, length, export_time, sequence, domain = struct.unpack("!HHIII", data[:16])
    if version != 10:
        raise ValueError(f"unsupported flow version {version}")
    if length > len(data) or length < 16:
        raise ValueError("invalid IPFIX message length")
    result = {"version": version, "message_length": length, "export_time": export_time,
              "sequence": sequence, "observation_domain_id": domain, "sets": []}
    offset = 16
    while offset + 4 <= length:
        set_id, set_length = struct.unpack("!HH", data[offset:offset + 4])
        if set_length < 4 or offset + set_length > length:
            raise ValueError("invalid IPFIX set length")
        payload = data[offset + 4:offset + set_length]
        item = {"set_id": set_id, "length": set_length}
        if set_id in (2, 3):
            templates = []
            pos = 0
            while pos + 4 <= len(payload):
                template_id, field_count = struct.unpack("!HH", payload[pos:pos + 4])
                pos += 4
                scope_count = None
                if set_id == 3:
                    if pos + 2 > len(payload): break
                    scope_count = struct.unpack("!H", payload[pos:pos + 2])[0]
                    pos += 2
                fields = []
                valid = True
                for _ in range(field_count):
                    if pos + 4 > len(payload): valid = False; break
                    element, field_len = struct.unpack("!HH", payload[pos:pos + 4]); pos += 4
                    enterprise = None
                    if element & 0x8000:
                        element &= 0x7fff
                        if pos + 4 > len(payload): valid = False; break
                        enterprise = struct.unpack("!I", payload[pos:pos + 4])[0]; pos += 4
                    fields.append({"element_id": element, "length": field_len, "enterprise": enterprise})
                if not valid: break
                templates.append({"template_id": template_id, "field_count": field_count,
                                  "scope_field_count": scope_count, "fields": fields})
            item["templates"] = templates
        else:
            item["data_bytes"] = len(payload)
            item["template_id"] = set_id if set_id >= 256 else None
            item["_payload"] = payload
        result["sets"].append(item)
        offset += set_length
    return result


def decode_ipfix_records(payload, template, max_samples=10):
    fields = template["fields"]
    if any(field["length"] == 65535 for field in fields):
        return [], "variable-length fields are not decoded yet"
    record_length = sum(field["length"] for field in fields)
    if not record_length:
        return [], "zero-length template"
    samples = []
    for base in range(0, len(payload) - record_length + 1, record_length):
        if len(samples) >= max_samples: break
        pos, sample = base, {}
        for field in fields:
            size = field["length"]; value = payload[pos:pos + size]; pos += size
            key = IPFIX_NAMES.get(field["element_id"], f"element_{field['element_id']}")
            if field["enterprise"] is not None: key = f"enterprise_{field['enterprise']}_{key}"
            try:
                if field["element_id"] in (8, 12) and size == 4: decoded = str(ipaddress.ip_address(value))
                elif field["element_id"] in (27, 28) and size == 16: decoded = str(ipaddress.ip_address(value))
                elif size <= 8: decoded = int.from_bytes(value, "big")
                else: decoded = value.hex()
            except ValueError:
                decoded = value.hex()
            sample[key] = decoded
        samples.append(sample)
    return samples, None


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
    if not match:
        raise ValueError("message is neither CEF nor supported RFC3164 syslog")
    priority_text, timestamp, hostname, body = match.groups()
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
        self.templates = {}

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
                if self.name == "ipfix":
                    domain = parsed["observation_domain_id"]
                    for item in parsed["sets"]:
                        for template in item.get("templates", []):
                            self.templates[(domain, template["template_id"])] = template
                    for item in parsed["sets"]:
                        payload = item.pop("_payload", None)
                        template = self.templates.get((domain, item.get("template_id")))
                        if payload is not None and template:
                            item["record_samples"], item["decode_note"] = decode_ipfix_records(payload, template)
                            item["estimated_records"] = len(payload) // max(1, sum(f["length"] for f in template["fields"] if f["length"] != 65535))
                    self.store.add("ipfix_message", source, f"IPFIX seq={parsed['sequence']} sets={len(parsed['sets'])}", parsed)
                    for item in parsed["sets"]:
                        for template in item.get("templates", []):
                            self.store.add("ipfix_template", source, f"Template {template['template_id']} ({template['field_count']} fields)", template)
                else:
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


STYLE = """body{font:15px system-ui;background:#0d1420;color:#e7edf5;margin:0}main{max-width:1100px;margin:auto;padding:28px}h1{color:#66d9ef}.card{background:#172235;border:1px solid #293a55;border-radius:10px;padding:18px;margin:14px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}.metric{font-size:28px}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:8px;border-bottom:1px solid #293a55}input{display:block;width:100%;box-sizing:border-box;padding:10px;margin:8px 0 14px}button,.button{background:#25a6c8;color:#07131b;border:0;border-radius:6px;padding:10px 16px;font-weight:700;text-decoration:none}.bad{color:#ff8293}.muted{color:#9fb0c5}nav{float:right}code{word-break:break-all}"""


class Web(BaseHTTPRequestHandler):
    store = None
    server_version = "UniFiLogExplorer/0.1"

    def log_message(self, fmt, *args):
        logging.debug("web: " + fmt, *args)

    def send_html(self, body, status=200, headers=None):
        raw = ("<!doctype html><html lang=fr><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
               f"<style>{STYLE}</style><main>{body}</main></html>").encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        for key, value in (headers or {}).items(): self.send_header(key, value)
        self.end_headers(); self.wfile.write(raw)

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
        path = urlparse(self.path).path
        if path == "/health":
            self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"OK"); return
        if not self.store.setting("admin_hash"):
            return self.send_html("<h1>UniFi Log Explorer</h1><div class=card><h2>Créer le compte administrateur</h2><form method=post action=/setup><label>Nom d’utilisateur<input name=username required minlength=3 maxlength=64 autocomplete=username></label><label>Mot de passe<input type=password name=password required minlength=12 autocomplete=new-password></label><label>Confirmation<input type=password name=confirm required minlength=12 autocomplete=new-password></label><button>Créer le compte</button></form></div>")
        session = self.session()
        if path == "/login":
            return self.send_html("<h1>UniFi Log Explorer</h1><div class=card><form method=post action=/login><label>Utilisateur<input name=username autocomplete=username required></label><label>Mot de passe<input type=password name=password autocomplete=current-password required></label><button>Connexion</button></form></div>")
        if not session: return self.redirect("/login")
        if path == "/export.json":
            payload = json.dumps(self.store.export(), indent=2).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Disposition", "attachment; filename=unifi-log-explorer-diagnostics.json"); self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload); return
        if path != "/": return self.send_error(404)
        data = self.store.dashboard(); counts = data["counts"]; counters = data["counters"]
        metrics = [("Datagrammes IPFIX", counters.get("ipfix_datagrams",0)), ("Messages IPFIX", counts.get("ipfix_message",0)), ("Templates", counts.get("ipfix_template",0)), ("Événements CEF", counts.get("cef",0)), ("Messages Syslog", counts.get("syslog",0)), ("Sources refusées", counters.get("ipfix_rejected_source",0)+counters.get("cef_rejected_source",0)), ("Erreurs de parsing", counters.get("ipfix_parse_errors",0)+counters.get("cef_parse_errors",0))]
        cards = "".join(f"<div class=card><div class=metric>{v}</div><div class=muted>{html.escape(k)}</div></div>" for k,v in metrics)
        rows = "".join(f"<tr><td>{time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(r['received_at']))}</td><td>{html.escape(r['kind'])}</td><td>{html.escape(r['source_ip'])}</td><td>{html.escape(r['summary'])}</td></tr>" for r in data["recent"])
        csrf = session["csrf"]
        rejected = ", ".join(f"{html.escape(ip)} ({count})" for ip,count in sorted(data["rejected_sources"].items())) or "aucune"
        body = f"<nav><form method=post action=/logout><input type=hidden name=csrf value='{csrf}'><button>Déconnexion</button></form></nav><h1>UniFi Log Explorer</h1><p>Phase 1 · collecte diagnostique</p><div class=grid>{cards}</div><div class=card><b>Sources autorisées :</b> {', '.join(map(html.escape,data['allowed_source_ips']))}<br><b>Sources refusées observées :</b> {rejected}<br><b>Rétention :</b> {data['retention_hours']} h · <b>Limite :</b> {data['max_records']} enregistrements</div><p><a class=button href=/export.json>Exporter le diagnostic JSON</a></p><div class=card><h2>Derniers enregistrements</h2><table><thead><tr><th>Date</th><th>Type</th><th>Source</th><th>Résumé</th></tr></thead><tbody>{rows}</tbody></table></div>"
        self.send_html(body)

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
    for collector in (Collector("ipfix", IPFIX_PORT, store, parse_ipfix), Collector("cef", CEF_PORT, store, parse_syslog_or_cef)):
        collector.start()
    threading.Thread(target=maintenance, args=(store,), daemon=True).start()
    Web.store = store
    logging.info("Web interface listening on TCP %s; allowed sources: %s", WEB_PORT, ", ".join(sorted(options["allowed_source_ips"])))
    ThreadingHTTPServer(("", WEB_PORT), Web).serve_forever()


if __name__ == "__main__":
    main()
