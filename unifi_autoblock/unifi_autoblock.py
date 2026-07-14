#!/usr/bin/env python3
"""Home Assistant app that autoblocks UniFi IDS/IPS attacker IPs."""

from __future__ import annotations

import datetime as dt
import ipaddress
import json
import logging
import os
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


OPTIONS_PATH = "/data/options.json"
STATE_PATH = "/data/state.json"
LIST_TYPE = "IPV4_ADDRESSES"
ITEM_TYPE = "IP_ADDRESS"
MANAGED_VERSION = 1


LOGGER = logging.getLogger("unifi_autoblock")
UPDATE_LOCK = threading.Lock()


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def isoformat(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()


def parse_iso(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def load_json_file(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as err:
        raise RuntimeError(f"Invalid JSON in {path}: {err}") from err


def save_json_file(path: str, data: Any) -> None:
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, path)


def redact(value: str | None) -> str:
    if not value:
        return "<empty>"
    return "<redacted>"


class Config:
    def __init__(self, raw: dict[str, Any]) -> None:
        self.unifi_base_url = str(raw["unifi_base_url"]).rstrip("/")
        self.unifi_site_id = str(raw.get("unifi_site_id") or "").strip()
        self.traffic_matching_list_id = str(raw.get("traffic_matching_list_id") or "").strip()
        self.traffic_matching_list_name = str(raw.get("traffic_matching_list_name") or "").strip()
        self.unifi_api_key = str(raw["unifi_api_key"])
        self.webhook_token = str(raw.get("webhook_token") or "").strip()
        self.webhook_base_url = str(raw.get("webhook_base_url") or "").rstrip("/")
        self.verify_ssl = bool(raw.get("verify_ssl", False))
        self.dry_run = bool(raw.get("dry_run", True))
        self.allowed_destinations = set(str(v) for v in raw.get("allowed_destinations", []))
        destination_ports = raw.get("allowed_destination_ports", [443])
        self.allowed_destination_ports = set(int(v) for v in destination_ports)
        self.min_severity = int(raw.get("min_severity", 0))
        self.ban_ttl_days = int(raw.get("ban_ttl_days", 30))
        self.max_new_blocks_per_hour = int(raw.get("max_new_blocks_per_hour", 20))
        self.max_list_size = int(raw.get("max_list_size", 1000))
        self.allowed_webhook_sources = [
            ipaddress.ip_network(str(v), strict=False)
            for v in raw.get("allowed_webhook_sources", [])
            if str(v).strip()
        ]
        self.allowlist_cidrs = [
            ipaddress.ip_network(str(v), strict=False)
            for v in raw.get("allowlist_cidrs", [])
            if str(v).strip()
        ]
        self.log_level = str(raw.get("log_level", "info")).upper()

    @classmethod
    def load(cls) -> "Config":
        raw = load_json_file(OPTIONS_PATH, {})
        required = [
            "unifi_base_url",
            "unifi_api_key",
        ]
        missing = [key for key in required if not raw.get(key)]
        if missing:
            raise RuntimeError(f"Missing required options: {', '.join(missing)}")
        config = cls(raw)
        if config.webhook_token and config.webhook_token == config.unifi_api_key:
            raise RuntimeError("webhook_token must be different from unifi_api_key")
        return config

    def integration_url(self, path: str) -> str:
        return f"{self.unifi_base_url}/proxy/network/integration/v1{path}"

    @property
    def traffic_list_url(self) -> str:
        if not self.unifi_site_id or not self.traffic_matching_list_id:
            raise RuntimeError("UniFi site and traffic matching list must be resolved before use")
        return self.integration_url(
            f"/sites/{self.unifi_site_id}/traffic-matching-lists/{self.traffic_matching_list_id}"
        )


def extract_collection(response: Any, label: str) -> list[dict[str, Any]]:
    if isinstance(response, dict) and isinstance(response.get("data"), list):
        return [item for item in response["data"] if isinstance(item, dict)]
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    raise RuntimeError(f"Unexpected UniFi API response while listing {label}")


def describe_items(items: list[dict[str, Any]]) -> str:
    if not items:
        return "<none>"
    lines = []
    for item in items:
        name = item.get("name") or item.get("desc") or item.get("id") or "<unnamed>"
        item_id = item.get("id", "<no id>")
        item_type = item.get("type")
        suffix = f" type={item_type}" if item_type else ""
        lines.append(f"- {name}: {item_id}{suffix}")
    return "\n".join(lines)


def resolve_unifi_targets(config: Config, client: UniFiClient) -> None:
    if not config.unifi_site_id:
        sites = client.list_sites()
        if len(sites) == 1:
            config.unifi_site_id = str(sites[0].get("id", ""))
            if not config.unifi_site_id:
                raise RuntimeError("The only UniFi site returned by the API has no id")
            LOGGER.info("Auto-detected UniFi site: %s", config.unifi_site_id)
        elif not sites:
            raise RuntimeError("No UniFi sites returned by the API")
        else:
            raise RuntimeError(
                "Multiple UniFi sites found; set unifi_site_id explicitly:\n"
                + describe_items(sites)
            )
    else:
        LOGGER.info("Using configured UniFi site: %s", config.unifi_site_id)

    if not config.traffic_matching_list_id:
        lists = client.list_traffic_matching_lists()
        ipv4_lists = [item for item in lists if item.get("type") == LIST_TYPE]
        if config.traffic_matching_list_name:
            matches = [
                item for item in ipv4_lists
                if item.get("name") == config.traffic_matching_list_name
            ]
            error_hint = "set traffic_matching_list_id explicitly"
        else:
            matches = ipv4_lists
            error_hint = "set traffic_matching_list_name or traffic_matching_list_id explicitly"

        if len(matches) == 1:
            selected = matches[0]
            config.traffic_matching_list_id = str(selected.get("id", ""))
            config.traffic_matching_list_name = str(selected.get("name", ""))
            if not config.traffic_matching_list_id or not config.traffic_matching_list_name:
                raise RuntimeError("The matching UniFi traffic matching list has no id or name")
            LOGGER.info(
                "Auto-detected traffic matching list %r: %s",
                config.traffic_matching_list_name,
                config.traffic_matching_list_id,
            )
        elif not matches:
            raise RuntimeError(
                f"No IPV4_ADDRESSES traffic matching list named "
                f"{config.traffic_matching_list_name!r} found. Available IPv4 lists:\n"
                + describe_items(ipv4_lists)
            )
        else:
            raise RuntimeError(
                f"Multiple IPV4_ADDRESSES traffic matching lists found; {error_hint}:\n"
                + describe_items(matches)
            )
    else:
        LOGGER.info("Using configured traffic matching list: %s", config.traffic_matching_list_id)

    traffic_list = client.get_traffic_list()
    validate_traffic_list(traffic_list, config)


class UniFiClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        if config.verify_ssl:
            self.context = ssl.create_default_context()
        else:
            self.context = ssl._create_unverified_context()

    def request(self, method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None
        headers = {
            "Accept": "application/json",
            "X-API-KEY": self.config.unifi_api_key,
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, context=self.context, timeout=15) as response:
                body = response.read().decode("utf-8")
                if not body:
                    return {}
                return json.loads(body)
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"UniFi API {method} {url} failed: HTTP {err.code}: {body}") from err
        except urllib.error.URLError as err:
            raise RuntimeError(f"UniFi API {method} {url} failed: {err}") from err

    def list_sites(self) -> list[dict[str, Any]]:
        response = self.request("GET", self.config.integration_url("/sites?limit=200"))
        return extract_collection(response, "sites")

    def list_traffic_matching_lists(self) -> list[dict[str, Any]]:
        if not self.config.unifi_site_id:
            raise RuntimeError("UniFi site must be resolved before listing traffic matching lists")
        response = self.request(
            "GET",
            self.config.integration_url(
                f"/sites/{self.config.unifi_site_id}/traffic-matching-lists?limit=200"
            ),
        )
        return extract_collection(response, "traffic matching lists")

    def get_traffic_list(self) -> dict[str, Any]:
        return self.request("GET", self.config.traffic_list_url)

    def update_traffic_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("PUT", self.config.traffic_list_url, payload)


def ensure_webhook_token(config: Config) -> str:
    state = load_state()
    if config.webhook_token:
        state["webhook_token"] = config.webhook_token
        save_json_file(STATE_PATH, state)
        return config.webhook_token

    token = str(state.get("webhook_token") or "").strip()
    if not token:
        token = secrets.token_urlsafe(32)
        state["webhook_token"] = token
        save_json_file(STATE_PATH, state)
        LOGGER.info("Generated a persistent webhook token")
    config.webhook_token = token
    return token


def webhook_path(config: Config) -> str:
    if not config.webhook_token:
        raise RuntimeError("webhook token has not been initialized")
    return f"/webhook/{config.webhook_token}"


def display_webhook_url(config: Config) -> str:
    path = webhook_path(config)
    if config.webhook_base_url:
        return f"{config.webhook_base_url}{path}"
    return path


def load_state() -> dict[str, Any]:
    state = load_json_file(STATE_PATH, {})
    if not state:
        state = {
            "version": MANAGED_VERSION,
            "managed_ips": {},
            "new_block_timestamps": [],
        }
    state.setdefault("version", MANAGED_VERSION)
    state.setdefault("managed_ips", {})
    state.setdefault("new_block_timestamps", [])
    return state


def cleanup_rate_window(state: dict[str, Any], now: dt.datetime) -> None:
    cutoff = now - dt.timedelta(hours=1)
    timestamps = []
    for value in state.get("new_block_timestamps", []):
        try:
            if parse_iso(value) >= cutoff:
                timestamps.append(value)
        except ValueError:
            continue
    state["new_block_timestamps"] = timestamps


def is_allowed_source(remote_ip: str, config: Config) -> bool:
    if not config.allowed_webhook_sources:
        return True
    try:
        parsed = ipaddress.ip_address(remote_ip)
    except ValueError:
        return False
    return any(parsed in network for network in config.allowed_webhook_sources)


def public_ipv4(value: str) -> ipaddress.IPv4Address:
    parsed = ipaddress.ip_address(value)
    if not isinstance(parsed, ipaddress.IPv4Address):
        raise ValueError("source is not an IPv4 address")
    if not parsed.is_global:
        raise ValueError("source is not a public global IPv4 address")
    return parsed


def is_allowlisted(ip: ipaddress.IPv4Address, config: Config) -> bool:
    return any(ip in network for network in config.allowlist_cidrs)


def validate_event(event: dict[str, Any], config: Config) -> tuple[str, dict[str, Any]]:
    parameters = event.get("parameters")
    if not isinstance(parameters, dict):
        raise ValueError("missing parameters object")

    checks = {
        "name": event.get("name") == "Threat Detected and Blocked",
        "act": parameters.get("act") == "blocked",
        "direction": parameters.get("UNIFIdirection") == "incoming",
        "policy_type": parameters.get("UNIFIpolicyType") == "IDS/IPS",
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise ValueError(f"event did not match required fields: {', '.join(failed)}")

    severity = int(event.get("severity", 0))
    if severity < config.min_severity:
        raise ValueError(f"severity {severity} is below configured minimum {config.min_severity}")

    dst = str(parameters.get("dst", ""))
    if config.allowed_destinations and dst not in config.allowed_destinations:
        raise ValueError(f"destination {dst} is not configured")

    try:
        dpt = int(parameters.get("dpt"))
    except (TypeError, ValueError) as err:
        raise ValueError("destination port is missing or invalid") from err
    if config.allowed_destination_ports and dpt not in config.allowed_destination_ports:
        raise ValueError(f"destination port {dpt} is not configured")

    source_ip = public_ipv4(str(parameters.get("src", "")))
    if is_allowlisted(source_ip, config):
        raise ValueError(f"source {source_ip} is allowlisted")

    details = {
        "severity": severity,
        "destination": dst,
        "destination_port": dpt,
        "protocol": parameters.get("proto"),
        "signature": parameters.get("UNIFIipsSignature"),
        "region": parameters.get("UNIFIsrcRegion"),
        "event_time": parameters.get("UNIFIutcTime"),
        "alarm_id": event.get("alarm_id"),
    }
    return str(source_ip), details


def validate_traffic_list(data: dict[str, Any], config: Config) -> list[dict[str, str]]:
    if data.get("type") != LIST_TYPE:
        raise RuntimeError(f"Traffic matching list type is {data.get('type')!r}, expected {LIST_TYPE}")
    if data.get("id") != config.traffic_matching_list_id:
        raise RuntimeError("Traffic matching list id mismatch")

    list_name = str(data.get("name") or "").strip()
    if config.traffic_matching_list_name and list_name != config.traffic_matching_list_name:
        raise RuntimeError(
            f"Traffic matching list name is {list_name!r}, "
            f"expected {config.traffic_matching_list_name!r}"
        )
    if not config.traffic_matching_list_name:
        if not list_name:
            raise RuntimeError("Traffic matching list name is missing")
        config.traffic_matching_list_name = list_name
    items = data.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Traffic matching list items are missing")
    validated = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") != ITEM_TYPE:
            continue
        value = str(item.get("value", ""))
        try:
            public_ipv4(value)
        except ValueError:
            LOGGER.warning("Ignoring non-public IPv4 item already in UniFi list: %s", value)
            continue
        validated.append({"type": ITEM_TYPE, "value": value})
    return validated


def remove_expired_managed_items(
    items: list[dict[str, str]],
    state: dict[str, Any],
    now: dt.datetime,
) -> tuple[list[dict[str, str]], list[str]]:
    managed_ips = state.get("managed_ips", {})
    expired = []
    for ip, record in list(managed_ips.items()):
        try:
            expires_at = parse_iso(record["expires_at"])
        except (KeyError, ValueError, TypeError):
            expires_at = now
        if expires_at <= now:
            expired.append(ip)
            managed_ips.pop(ip, None)

    if not expired:
        return items, []

    expired_set = set(expired)
    filtered = [item for item in items if item["value"] not in expired_set]
    return filtered, expired


def process_event(event: dict[str, Any], config: Config, client: UniFiClient) -> dict[str, Any]:
    source_ip, details = validate_event(event, config)
    now = utc_now()

    with UPDATE_LOCK:
        state = load_state()
        cleanup_rate_window(state, now)

        if config.dry_run:
            LOGGER.info("DRY RUN: would add %s to %s", source_ip, config.traffic_matching_list_name)
            return {"status": "dry_run", "ip": source_ip, "details": details}

        if len(state["new_block_timestamps"]) >= config.max_new_blocks_per_hour:
            raise RuntimeError("hourly new block limit reached")

        traffic_list = client.get_traffic_list()
        items = validate_traffic_list(traffic_list, config)
        items, expired = remove_expired_managed_items(items, state, now)

        existing_ips = {item["value"] for item in items}
        if source_ip in existing_ips:
            if source_ip in state["managed_ips"]:
                record = state["managed_ips"][source_ip]
                record["last_seen"] = isoformat(now)
                record["hit_count"] = int(record.get("hit_count", 0)) + 1
                record["expires_at"] = isoformat(now + dt.timedelta(days=config.ban_ttl_days))
                record["last_details"] = details

            if expired:
                payload = {
                    "type": LIST_TYPE,
                    "name": config.traffic_matching_list_name,
                    "items": items,
                }
                client.update_traffic_list(payload)
            save_json_file(STATE_PATH, state)
            LOGGER.info("IP %s is already present in UniFi blocklist", source_ip)
            return {"status": "already_present", "ip": source_ip, "expired_removed": expired}

        if len(items) >= config.max_list_size:
            raise RuntimeError("traffic matching list size limit reached")

        items.append({"type": ITEM_TYPE, "value": source_ip})
        payload = {
            "type": LIST_TYPE,
            "name": config.traffic_matching_list_name,
            "items": items,
        }
        client.update_traffic_list(payload)
        verify = client.get_traffic_list()
        verified_items = validate_traffic_list(verify, config)
        if source_ip not in {item["value"] for item in verified_items}:
            raise RuntimeError("UniFi update verification failed")

        state["managed_ips"][source_ip] = {
            "first_seen": isoformat(now),
            "last_seen": isoformat(now),
            "expires_at": isoformat(now + dt.timedelta(days=config.ban_ttl_days)),
            "hit_count": 1,
            "last_details": details,
        }
        state["new_block_timestamps"].append(isoformat(now))
        save_json_file(STATE_PATH, state)

    LOGGER.info("Added %s to %s", source_ip, config.traffic_matching_list_name)
    return {"status": "blocked", "ip": source_ip, "expired_removed": expired}


class Handler(BaseHTTPRequestHandler):
    server_version = "UniFiAutoblock/0.3"

    def log_message(self, fmt: str, *args: Any) -> None:
        LOGGER.debug("HTTP %s - %s", self.address_string(), fmt % args)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "dry_run": self.server.config.dry_run})
            return
        self.send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        config: Config = self.server.config
        expected_path = webhook_path(config)
        if self.path != expected_path:
            self.send_json(404, {"error": "not_found"})
            return

        remote_ip = self.client_address[0]
        if not is_allowed_source(remote_ip, config):
            LOGGER.warning("Rejected webhook from unauthorized source %s", remote_ip)
            self.send_json(403, {"error": "forbidden"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(411, {"error": "invalid_content_length"})
            return
        if length <= 0 or length > 1024 * 1024:
            self.send_json(413, {"error": "invalid_body_size"})
            return

        raw_body = self.rfile.read(length)
        try:
            event = json.loads(raw_body.decode("utf-8"))
            if not isinstance(event, dict):
                raise ValueError("payload must be a JSON object")
            result = process_event(event, config, self.server.unifi_client)
            self.send_json(200, result)
        except ValueError as err:
            LOGGER.info("Ignored webhook event: %s", err)
            self.send_json(202, {"status": "ignored", "reason": str(err)})
        except Exception as err:
            LOGGER.exception("Failed to process webhook")
            self.send_json(500, {"error": "processing_failed", "reason": str(err)})


class AutoblockServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], config: Config, client: UniFiClient) -> None:
        super().__init__(address, Handler)
        self.config = config
        self.unifi_client = client


def configure_logging(level: str) -> None:
    numeric = getattr(logging, level, logging.INFO)
    logging.basicConfig(
        level=numeric,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    config = Config.load()
    configure_logging(config.log_level)
    LOGGER.info("Starting UniFi Autoblock")
    LOGGER.info("UniFi base URL: %s", config.unifi_base_url)
    LOGGER.info("Traffic matching list name: %s", config.traffic_matching_list_name or "<auto-detect>")
    LOGGER.info("UniFi API key: %s", redact(config.unifi_api_key))
    LOGGER.info("Dry run: %s", config.dry_run)
    ensure_webhook_token(config)
    LOGGER.info("Webhook URL to configure in UniFi Alarm Manager: %s", display_webhook_url(config))

    client = UniFiClient(config)
    resolve_unifi_targets(config, client)
    LOGGER.info("Resolved UniFi site ID: %s", config.unifi_site_id)
    LOGGER.info("Resolved traffic matching list ID: %s", config.traffic_matching_list_id)

    server = AutoblockServer(("0.0.0.0", 37989), config, client)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Stopping UniFi Autoblock")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
