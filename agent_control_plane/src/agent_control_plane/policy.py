"""Version-one deny-by-default control-plane policy evaluation."""

from __future__ import annotations

from dataclasses import dataclass


KNOWN_ACTIONS = frozenset(
    {
        "control_plane.status.read",
        "permissions.effective.read",
        "events.create",
        "events.read",
        "jobs.read",
        "jobs.claim",
        "jobs.heartbeat",
        "jobs.complete",
        "jobs.fail",
        "reports.read",
    }
)


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason_code: str


def validate_actions(actions: object) -> tuple[str, ...]:
    if not isinstance(actions, list) or any(not isinstance(item, str) for item in actions):
        raise ValueError("Policy actions must be a list of strings")
    unknown = set(actions) - KNOWN_ACTIONS
    if unknown:
        raise ValueError(f"Unknown policy actions: {', '.join(sorted(unknown))}")
    return tuple(sorted(set(actions)))


def decide(action: str, allowed_actions: tuple[str, ...]) -> PolicyDecision:
    if action not in KNOWN_ACTIONS:
        return PolicyDecision(False, "unknown_action")
    if action not in allowed_actions:
        return PolicyDecision(False, "not_granted")
    return PolicyDecision(True, "explicit_grant")
