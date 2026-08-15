"""Fail-closed JSON Schema validation for MCP contracts."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError


SCHEMA_2020_12 = "https://json-schema.org/draft/2020-12/schema"
SUPPORTED_KEYWORDS = frozenset(
    {
        "$anchor",
        "$comment",
        "$defs",
        "$dynamicAnchor",
        "$dynamicRef",
        "$id",
        "$ref",
        "$schema",
        "additionalProperties",
        "allOf",
        "anyOf",
        "const",
        "contains",
        "contentEncoding",
        "contentMediaType",
        "contentSchema",
        "default",
        "definitions",
        "dependentRequired",
        "dependentSchemas",
        "deprecated",
        "description",
        "else",
        "enum",
        "examples",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "format",
        "if",
        "items",
        "maxContains",
        "maximum",
        "maxItems",
        "maxLength",
        "maxProperties",
        "minContains",
        "minimum",
        "minItems",
        "minLength",
        "minProperties",
        "multipleOf",
        "not",
        "oneOf",
        "pattern",
        "patternProperties",
        "prefixItems",
        "properties",
        "propertyNames",
        "readOnly",
        "required",
        "then",
        "title",
        "type",
        "unevaluatedItems",
        "unevaluatedProperties",
        "uniqueItems",
        "writeOnly",
    }
)
SINGLE_SCHEMA_KEYWORDS = frozenset(
    {
        "additionalProperties",
        "contains",
        "contentSchema",
        "else",
        "if",
        "items",
        "not",
        "propertyNames",
        "then",
        "unevaluatedItems",
        "unevaluatedProperties",
    }
)
SCHEMA_ARRAY_KEYWORDS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
SCHEMA_MAP_KEYWORDS = frozenset(
    {"$defs", "definitions", "dependentSchemas", "patternProperties", "properties"}
)
FORMAT_CHECKER = FormatChecker()


def _audit_schema_node(schema: object) -> None:
    if isinstance(schema, bool):
        return
    if not isinstance(schema, dict):
        raise ValueError("invalid_json_schema")
    unknown = set(schema) - SUPPORTED_KEYWORDS
    if unknown:
        raise ValueError("unsupported_json_schema_keyword")
    dialect = schema.get("$schema")
    if dialect not in {None, SCHEMA_2020_12, f"{SCHEMA_2020_12}#"}:
        raise ValueError("unsupported_json_schema_dialect")
    reference = schema.get("$ref") or schema.get("$dynamicRef")
    if reference is not None and (not isinstance(reference, str) or not reference.startswith("#")):
        raise ValueError("unsupported_external_json_schema_reference")
    format_name = schema.get("format")
    if format_name is not None and (
        not isinstance(format_name, str) or format_name not in FORMAT_CHECKER.checkers
    ):
        raise ValueError("unsupported_json_schema_format")
    for keyword in SINGLE_SCHEMA_KEYWORDS & schema.keys():
        child = schema[keyword]
        if keyword == "items" and isinstance(child, list):
            raise ValueError("unsupported_json_schema_keyword")
        _audit_schema_node(child)
    for keyword in SCHEMA_ARRAY_KEYWORDS & schema.keys():
        children = schema[keyword]
        if not isinstance(children, list):
            raise ValueError("invalid_json_schema")
        for child in children:
            _audit_schema_node(child)
    for keyword in SCHEMA_MAP_KEYWORDS & schema.keys():
        children = schema[keyword]
        if not isinstance(children, dict):
            raise ValueError("invalid_json_schema")
        for child in children.values():
            _audit_schema_node(child)


@lru_cache(maxsize=256)
def _compiled_validator(encoded_schema: str) -> Draft202012Validator:
    schema = json.loads(encoded_schema)
    _audit_schema_node(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError("invalid_json_schema") from exc
    return Draft202012Validator(schema, format_checker=FORMAT_CHECKER)


def validate_json_schema(schema: dict[str, Any]) -> None:
    """Validate one bounded MCP schema without silently ignoring constraints."""
    try:
        encoded = json.dumps(
            schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_json_schema") from exc
    _compiled_validator(encoded)


def validate_json_contract(value: object, schema: dict[str, Any], path: str = "report") -> None:
    """Validate a JSON value against the complete admitted MCP schema contract."""
    try:
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid_contract:{path}:json_value") from exc
    try:
        encoded = json.dumps(
            schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        _compiled_validator(encoded).validate(value)
    except ValidationError as exc:
        keyword = {
            "additionalProperties": "additional_property",
            "maxItems": "max_items",
            "maxLength": "max_length",
            "minItems": "min_items",
            "minLength": "min_length",
        }.get(str(exc.validator), str(exc.validator or "schema"))
        raise ValueError(f"invalid_contract:{path}:{keyword}") from None
    except ValueError:
        raise
    except Exception as exc:
        # Includes unresolved local references and any validator condition that
        # cannot be interpreted safely. Never expose instance values in errors.
        raise ValueError(f"invalid_contract:{path}:schema") from exc
