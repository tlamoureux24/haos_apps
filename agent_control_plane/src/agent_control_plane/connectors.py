"""Generic MCP connector validation, secret protection and discovery."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from urllib.parse import urlsplit, urlunsplit

from agent_control_plane.json_contracts import validate_json_schema
from agent_control_plane.pinned_http import async_client_kwargs, normalize_certificate_sha256


MAX_TOOLS = 200
MAX_SCHEMA_BYTES = 16 * 1024
MAX_RESULT_BYTES = 256 * 1024
SCHEMA_REJECTION_CODES = frozenset(
    {
        "unsupported_json_schema_keyword",
        "unsupported_json_schema_dialect",
        "unsupported_json_schema_format",
        "unsupported_external_json_schema_reference",
        "upstream_tool_schema_too_large",
        "invalid_json_schema",
    }
)

# Upstream client libraries may otherwise log full request URLs, whose path or
# query can contain administrator-supplied credentials.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("mcp.client.streamable_http").setLevel(logging.WARNING)


class ConnectorSchemaRejected(ValueError):
    """A reachable MCP server published a schema that cannot be admitted safely."""

    def __init__(self, code: str, tool_name: str = "") -> None:
        self.code = code if code in SCHEMA_REJECTION_CODES else "invalid_json_schema"
        self.tool_name = tool_name[:160]
        super().__init__(self.code)


class ConnectorCertificateMismatch(ConnectionError):
    code = "certificate_sha256_mismatch"


def _contains_error_message(error: BaseException | None, message: str) -> bool:
    if error is None:
        return False
    if message in str(error):
        return True
    return (
        any(_contains_error_message(item, message) for item in getattr(error, "exceptions", ()))
        or _contains_error_message(error.__cause__, message)
        or _contains_error_message(error.__context__, message)
    )


def validate_discovered_tool_schema(tool_name: str, schema: dict[str, object]) -> str:
    """Return the canonical schema encoding or preserve a safe rejection cause."""
    try:
        encoded = json.dumps(
            schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ConnectorSchemaRejected("invalid_json_schema", tool_name) from exc
    if len(encoded.encode()) > MAX_SCHEMA_BYTES:
        raise ConnectorSchemaRejected("upstream_tool_schema_too_large", tool_name)
    try:
        validate_json_schema(schema)
    except ValueError as exc:
        raise ConnectorSchemaRejected(str(exc), tool_name) from exc
    return encoded


def validate_streamable_http_url(value: str) -> str:
    url = value.strip()
    if not 1 <= len(url) <= 2048 or any(character.isspace() for character in url):
        raise ValueError("invalid_connector_url")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("invalid_connector_url")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid_connector_url") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("invalid_connector_url")
    if parsed.fragment:
        raise ValueError("invalid_connector_url")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def connector_display_endpoint(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def connector_fernet(pepper: bytes):
    from cryptography.fernet import Fernet

    key = hmac.new(pepper, b"agent-control-plane-connector-secrets-v1", hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def protect_connector_config(pepper: bytes, url: str, bearer_token: str, certificate_sha256: str = "") -> str:
    normalized_url = validate_streamable_http_url(url)
    normalized_fingerprint = normalize_certificate_sha256(certificate_sha256)
    if normalized_fingerprint and urlsplit(normalized_url).scheme != "https":
        raise ValueError("certificate_sha256_requires_https")
    payload = json.dumps(
        {"url": normalized_url, "bearer_token": bearer_token, "certificate_sha256": normalized_fingerprint},
        separators=(",", ":"),
    ).encode()
    return connector_fernet(pepper).encrypt(payload).decode("ascii")


def reveal_connector_config(pepper: bytes, protected: str) -> tuple[str, str]:
    try:
        payload = json.loads(connector_fernet(pepper).decrypt(protected.encode("ascii")))
        return validate_streamable_http_url(payload["url"]), str(payload.get("bearer_token", ""))
    except Exception as exc:
        raise ValueError("invalid_connector_secret") from exc


def reveal_connector_transport_config(pepper: bytes, protected: str) -> tuple[str, str, str]:
    try:
        payload = json.loads(connector_fernet(pepper).decrypt(protected.encode("ascii")))
        return validate_streamable_http_url(payload["url"]), str(payload.get("bearer_token", "")), normalize_certificate_sha256(payload.get("certificate_sha256", ""))
    except Exception as exc:
        raise ValueError("invalid_connector_secret") from exc


async def discover_streamable_http(url: str, bearer_token: str, certificate_sha256: str = "") -> list[dict[str, object]]:
    """Initialize one upstream MCP session and return bounded tool metadata."""
    import anyio
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    if normalize_certificate_sha256(certificate_sha256) and urlsplit(url).scheme != "https":
        raise ValueError("certificate_sha256_requires_https")
    if urlsplit(url).scheme == "http":
        logging.getLogger(__name__).warning("ACP_MCP_OUTBOUND unencrypted_http endpoint=%s", connector_display_endpoint(url))
    headers = {"Origin": connector_display_endpoint(url)}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    timeout = httpx.Timeout(8.0, read=8.0)
    try:
        async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=False, **async_client_kwargs(certificate_sha256)) as client:
            with anyio.fail_after(10):
                async with streamable_http_client(url, http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.list_tools()
    except BaseException as error:
        if _contains_error_message(error, "certificate_sha256_mismatch"):
            logging.getLogger(__name__).warning("ACP_MCP_PIN rejected endpoint=%s code=certificate_sha256_mismatch", connector_display_endpoint(url))
            raise ConnectorCertificateMismatch("certificate_sha256_mismatch") from None
        raise
    inventory: list[dict[str, object]] = []
    for tool in result.tools[:MAX_TOOLS]:
        schema = tool.inputSchema if isinstance(tool.inputSchema, dict) else {}
        tool_name = str(tool.name)[:160]
        encoded = validate_discovered_tool_schema(tool_name, schema)
        inventory.append(
            {
                "name": tool_name,
                "description": str(tool.description or "")[:2000],
                "input_schema": schema,
                "schema_fingerprint": hashlib.sha256(encoded.encode()).hexdigest(),
            }
        )
    return inventory


async def invoke_streamable_http(
    url: str, bearer_token: str, tool_name: str, arguments: dict[str, object], certificate_sha256: str = ""
) -> dict[str, object]:
    """Invoke one exact upstream tool and return a bounded protocol-neutral result."""
    import anyio
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    if normalize_certificate_sha256(certificate_sha256) and urlsplit(url).scheme != "https":
        raise ValueError("certificate_sha256_requires_https")
    if urlsplit(url).scheme == "http":
        logging.getLogger(__name__).warning("ACP_MCP_OUTBOUND unencrypted_http endpoint=%s", connector_display_endpoint(url))
    headers = {"Origin": connector_display_endpoint(url)}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    timeout = httpx.Timeout(20.0, read=20.0)
    try:
        async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=False, **async_client_kwargs(certificate_sha256)) as client:
            with anyio.fail_after(25):
                async with streamable_http_client(url, http_client=client) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool_name, arguments=arguments)
    except BaseException as error:
        if _contains_error_message(error, "certificate_sha256_mismatch"):
            logging.getLogger(__name__).warning("ACP_MCP_PIN rejected endpoint=%s code=certificate_sha256_mismatch", connector_display_endpoint(url))
            raise ConnectorCertificateMismatch("certificate_sha256_mismatch") from None
        raise
    payload = result.model_dump(mode="json", by_alias=True, exclude_none=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > MAX_RESULT_BYTES:
        raise ValueError("upstream_result_too_large")
    return payload
