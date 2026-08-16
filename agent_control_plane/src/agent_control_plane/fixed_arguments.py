"""Optional top-level fixed-argument restrictions for virtual MCP tools."""

from __future__ import annotations

import copy
import json
from typing import Any

from agent_control_plane.connectors import connector_fernet


STANDARD_MODE = "standard"
FIXED_ARGUMENTS_MODE = "fixed_arguments_v1"
ARGUMENT_RULES = frozenset({"editable", "fixed_ordinary", "fixed_sensitive"})


def _protect_sensitive(pepper: bytes, values: dict[str, Any]) -> str:
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return connector_fernet(pepper).encrypt(encoded).decode("ascii")


def _reveal_sensitive(pepper: bytes, protected: str) -> dict[str, Any]:
    try:
        value = json.loads(connector_fernet(pepper).decrypt(protected.encode("ascii")))
    except Exception as exc:
        raise ValueError("invalid_fixed_arguments_secret") from exc
    if not isinstance(value, dict):
        raise ValueError("invalid_fixed_arguments_secret")
    return value


def build_virtual_schema(upstream_schema: dict[str, Any], editable: set[str]) -> dict[str, Any]:
    """Return an object schema containing only agent-editable top-level properties."""
    properties = upstream_schema.get("properties")
    if upstream_schema.get("type", "object") != "object" or not isinstance(properties, dict):
        raise ValueError("fixed_arguments_requires_object_schema")
    if any(not isinstance(name, str) or not isinstance(schema, dict) for name, schema in properties.items()):
        raise ValueError("invalid_upstream_tool_schema")
    unsupported = {
        "allOf", "anyOf", "oneOf", "not", "if", "then", "else",
        "dependentRequired", "dependentSchemas", "dependencies", "patternProperties",
    }
    if unsupported & upstream_schema.keys():
        raise ValueError("fixed_arguments_unsupported_schema")
    if not editable <= properties.keys():
        raise ValueError("invalid_fixed_argument_property")
    virtual = {
        "type": "object",
        "properties": {name: copy.deepcopy(properties[name]) for name in properties if name in editable},
    }
    for metadata in ("$defs", "$id", "$schema", "definitions", "title", "description"):
        if metadata in upstream_schema:
            virtual[metadata] = copy.deepcopy(upstream_schema[metadata])
    required = upstream_schema.get("required", [])
    if not isinstance(required, list) or any(not isinstance(name, str) for name in required):
        raise ValueError("invalid_upstream_tool_schema")
    virtual["required"] = [name for name in required if name in editable]
    virtual["additionalProperties"] = False
    return virtual


def build_constraints(
    pepper: bytes,
    upstream_schema: dict[str, Any],
    mode: str,
    example_arguments: dict[str, Any],
    argument_rules: dict[str, str],
    validate,
) -> dict[str, Any]:
    """Validate an administrator example and create the immutable stored contract."""
    if mode == STANDARD_MODE:
        if example_arguments or argument_rules:
            raise ValueError("standard_mode_has_fixed_arguments")
        return {"mode": STANDARD_MODE}
    if mode != FIXED_ARGUMENTS_MODE:
        raise ValueError("invalid_argument_exposure_mode")
    properties = upstream_schema.get("properties")
    if upstream_schema.get("type", "object") != "object" or not isinstance(properties, dict):
        raise ValueError("fixed_arguments_requires_object_schema")
    if not argument_rules or any(rule not in ARGUMENT_RULES for rule in argument_rules.values()):
        raise ValueError("invalid_fixed_argument_rules")
    if not argument_rules.keys() <= properties.keys():
        raise ValueError("invalid_fixed_argument_property")
    if not example_arguments.keys() <= properties.keys():
        raise ValueError("invalid_fixed_argument_example")
    validate(example_arguments, upstream_schema, "example_arguments")
    fixed_names = {
        name for name, rule in argument_rules.items() if rule in {"fixed_ordinary", "fixed_sensitive"}
    }
    if not fixed_names or any(name not in example_arguments for name in fixed_names):
        raise ValueError("fixed_argument_value_required")
    if any(name in example_arguments and name not in argument_rules for name in example_arguments):
        raise ValueError("unclassified_example_argument")
    editable = {name for name, rule in argument_rules.items() if rule == "editable"}
    ordinary = {
        name: copy.deepcopy(example_arguments[name])
        for name, rule in argument_rules.items()
        if rule == "fixed_ordinary"
    }
    sensitive = {
        name: copy.deepcopy(example_arguments[name])
        for name, rule in argument_rules.items()
        if rule == "fixed_sensitive"
    }
    virtual_schema = build_virtual_schema(upstream_schema, editable)
    reduced_example = {
        name: copy.deepcopy(example_arguments[name])
        for name in editable
        if name in example_arguments
    }
    validate(reduced_example, virtual_schema, "example_arguments")
    return {
        "mode": FIXED_ARGUMENTS_MODE,
        "editable": sorted(editable),
        "fixed_ordinary": ordinary,
        "fixed_sensitive_names": sorted(sensitive),
        "protected_fixed_sensitive": _protect_sensitive(pepper, sensitive) if sensitive else "",
        "virtual_schema": virtual_schema,
    }


def parse_constraints(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid_stored_fixed_arguments") from exc
    if not isinstance(value, dict):
        raise ValueError("invalid_stored_fixed_arguments")
    if not value:
        return {"mode": STANDARD_MODE}
    mode = value.get("mode", STANDARD_MODE)
    if mode not in {STANDARD_MODE, FIXED_ARGUMENTS_MODE}:
        raise ValueError("invalid_stored_fixed_arguments")
    return value


def effective_schema(upstream_schema: dict[str, Any], constraints: dict[str, Any]) -> dict[str, Any]:
    if constraints.get("mode") != FIXED_ARGUMENTS_MODE:
        return copy.deepcopy(upstream_schema)
    schema = constraints.get("virtual_schema")
    if not isinstance(schema, dict):
        raise ValueError("invalid_stored_fixed_arguments")
    return copy.deepcopy(schema)


def merge_arguments(
    pepper: bytes,
    arguments: dict[str, Any],
    upstream_schema: dict[str, Any],
    constraints: dict[str, Any],
    validate,
) -> dict[str, Any]:
    """Validate the reduced surface, inject fixed values, then validate upstream."""
    merged, _ = merge_arguments_with_sensitive_values(
        pepper, arguments, upstream_schema, constraints, validate
    )
    return merged


def merge_arguments_with_sensitive_values(
    pepper: bytes,
    arguments: dict[str, Any],
    upstream_schema: dict[str, Any],
    constraints: dict[str, Any],
    validate,
) -> tuple[dict[str, Any], list[Any]]:
    """Merge arguments and return sensitive values for transient result redaction."""
    if constraints.get("mode") != FIXED_ARGUMENTS_MODE:
        validate(arguments, upstream_schema, "arguments")
        return copy.deepcopy(arguments), []
    validate(arguments, effective_schema(upstream_schema, constraints), "arguments")
    ordinary = constraints.get("fixed_ordinary", {})
    sensitive_names = constraints.get("fixed_sensitive_names", [])
    protected = constraints.get("protected_fixed_sensitive", "")
    if not isinstance(ordinary, dict) or not isinstance(sensitive_names, list):
        raise ValueError("invalid_stored_fixed_arguments")
    sensitive = _reveal_sensitive(pepper, protected) if sensitive_names else {}
    if sorted(sensitive) != sorted(sensitive_names):
        raise ValueError("invalid_stored_fixed_arguments")
    hidden = set(ordinary) | set(sensitive)
    if hidden & arguments.keys():
        raise ValueError("hidden_fixed_argument")
    merged = copy.deepcopy(arguments)
    merged.update(copy.deepcopy(ordinary))
    merged.update(copy.deepcopy(sensitive))
    validate(merged, upstream_schema, "upstream_arguments")
    return merged, [copy.deepcopy(value) for value in sensitive.values()]


def administrative_summary(constraints: dict[str, Any]) -> dict[str, Any]:
    """Expose effective capability details without protected sensitive values."""
    if constraints.get("mode") != FIXED_ARGUMENTS_MODE:
        return {"mode": STANDARD_MODE, "editable": [], "fixed": {}}
    ordinary = constraints.get("fixed_ordinary", {})
    sensitive = constraints.get("fixed_sensitive_names", [])
    if not isinstance(ordinary, dict) or not isinstance(sensitive, list):
        raise ValueError("invalid_stored_fixed_arguments")
    fixed = {name: {"classification": "ordinary", "value": copy.deepcopy(value)} for name, value in ordinary.items()}
    fixed.update({name: {"classification": "sensitive", "protected": True} for name in sensitive})
    return {
        "mode": FIXED_ARGUMENTS_MODE,
        "editable": list(constraints.get("editable", [])),
        "fixed": fixed,
    }
