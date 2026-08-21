"""Static adapter, capability and ACP-compatible schema contracts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

MAX_SCHEMA_BYTES = 16 * 1024
TOOL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
SUPPORTED_KEYWORDS = frozenset({
    "$anchor", "$comment", "$defs", "$dynamicAnchor", "$dynamicRef", "$id", "$ref", "$schema",
    "additionalProperties", "allOf", "anyOf", "const", "contains", "contentEncoding",
    "contentMediaType", "contentSchema", "default", "definitions", "dependentRequired",
    "dependentSchemas", "deprecated", "description", "else", "enum", "examples",
    "exclusiveMaximum", "exclusiveMinimum", "format", "if", "items", "maxContains", "maximum",
    "maxItems", "maxLength", "maxProperties", "minContains", "minimum", "minItems", "minLength",
    "minProperties", "multipleOf", "not", "oneOf", "pattern", "patternProperties", "prefixItems",
    "properties", "propertyNames", "readOnly", "required", "then", "title", "type",
    "unevaluatedItems", "unevaluatedProperties", "uniqueItems", "writeOnly",
})
CHILD = frozenset({"additionalProperties", "contains", "contentSchema", "else", "if", "items", "not", "propertyNames", "then", "unevaluatedItems", "unevaluatedProperties"})
ARRAY = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
MAPPING = frozenset({"$defs", "definitions", "dependentSchemas", "patternProperties", "properties"})
FORMAT_CHECKER = FormatChecker()


def _audit(node: object) -> None:
    if isinstance(node, bool):
        return
    if not isinstance(node, dict) or set(node) - SUPPORTED_KEYWORDS:
        raise ValueError("unsupported_json_schema_keyword")
    if node.get("$schema") not in {None, "https://json-schema.org/draft/2020-12/schema", "https://json-schema.org/draft/2020-12/schema#"}:
        raise ValueError("unsupported_json_schema_dialect")
    reference = node.get("$ref") or node.get("$dynamicRef")
    if reference is not None and (not isinstance(reference, str) or not reference.startswith("#")):
        raise ValueError("unsupported_external_json_schema_reference")
    format_name = node.get("format")
    if format_name is not None and (not isinstance(format_name, str) or format_name not in FORMAT_CHECKER.checkers):
        raise ValueError("unsupported_json_schema_format")
    for key in CHILD & node.keys():
        if key == "items" and isinstance(node[key], list):
            raise ValueError("unsupported_json_schema_keyword")
        _audit(node[key])
    for key in ARRAY & node.keys():
        if not isinstance(node[key], list):
            raise ValueError("invalid_json_schema")
        for child in node[key]:
            _audit(child)
    for key in MAPPING & node.keys():
        if not isinstance(node[key], dict):
            raise ValueError("invalid_json_schema")
        for child in node[key].values():
            _audit(child)


def validate_schema(schema: dict[str, Any]) -> str:
    encoded = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode()) > MAX_SCHEMA_BYTES:
        raise ValueError("schema_too_large")
    _audit(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError("invalid_json_schema") from exc
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise ValueError("unsafe_tool_schema")
    return encoded


@dataclass(frozen=True)
class Capability:
    capability_id: str
    name: str
    description: str
    input_schema: dict[str, Any]
    effect_capable: bool = False

    def validated(self) -> "Capability":
        if not TOOL_NAME.fullmatch(self.name):
            raise ValueError("invalid_tool_name")
        if not 1 <= len(self.capability_id) <= 64 or not 1 <= len(self.description) <= 2000:
            raise ValueError("invalid_capability_metadata")
        validate_schema(self.input_schema)
        return self


class Adapter(Protocol):
    type_key: str
    display_name: str

    def validate_target(self, configuration: dict[str, Any], secret: bytes | None) -> None: ...
    def capabilities(self, configuration: dict[str, Any]) -> tuple[Capability, ...]: ...
    async def invoke(self, capability_id: str, configuration: dict[str, Any], secret: bytes | None, arguments: dict[str, Any]) -> object: ...


class AdapterRegistry:
    def __init__(self, adapters: tuple[Adapter, ...] = ()):
        self._adapters: dict[str, Adapter] = {}
        for adapter in adapters:
            if not re.fullmatch(r"[a-z][a-z0-9_]{1,31}", adapter.type_key) or adapter.type_key in self._adapters:
                raise ValueError("invalid_adapter_registry")
            self._adapters[adapter.type_key] = adapter

    def get(self, type_key: str) -> Adapter:
        try:
            return self._adapters[type_key]
        except KeyError as exc:
            raise ValueError("unknown_adapter") from exc

    def describe(self) -> list[dict[str, str]]:
        return [{"type_key": key, "display_name": adapter.display_name} for key, adapter in sorted(self._adapters.items())]
