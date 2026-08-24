"""Bounded delivery of persistent ACP notifications to Home Assistant Core."""

from __future__ import annotations

import os

import httpx

from agent_control_plane.control_plane import ControlPlane


EVENT_URL = "http://supervisor/core/api/events/agent_control_plane_notification"


async def deliver_one(control_plane: ControlPlane) -> bool:
    item = control_plane.claim_notification()
    if item is None:
        return False
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    error_code: str | None = None
    if not token:
        error_code = "supervisor_token_unavailable"
    else:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                response = await client.post(
                    EVENT_URL,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json=item["payload"],
                )
            if response.status_code in {401, 403}:
                error_code = "home_assistant_unauthorized"
            elif not 200 <= response.status_code < 300:
                error_code = "home_assistant_rejected"
        except httpx.TimeoutException:
            error_code = "home_assistant_timeout"
        except httpx.HTTPError:
            error_code = "home_assistant_unreachable"
    control_plane.finish_notification(str(item["id"]), str(item["lease_id"]), error_code)
    return True


async def deliver_batch(control_plane: ControlPlane, limit: int = 20) -> int:
    delivered = 0
    for _ in range(limit):
        if not await deliver_one(control_plane):
            break
        delivered += 1
    return delivered
