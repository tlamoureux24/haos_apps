"""Integration proof for two independent MCP connectors exposing the same tool name."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from agent_control_plane.connectors import discover_streamable_http, invoke_streamable_http
from agent_control_plane.control_plane import ControlPlane
from agent_control_plane.database import initialize_database


ROOT = Path(__file__).resolve().parents[1]
FAKE_SERVER = ROOT / "scripts" / "fake_mcp_server.py"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


class IndependentDuplicateToolConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.processes: list[subprocess.Popen[str]] = []

    def tearDown(self) -> None:
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
        for process in self.processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def start_server(self, marker: str) -> tuple[str, subprocess.Popen[str]]:
        port = free_port()
        process = subprocess.Popen(
            [
                sys.executable,
                str(FAKE_SERVER),
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--server-marker",
                marker,
            ],
            cwd=ROOT,
            env=os.environ.copy(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.processes.append(process)
        return f"http://127.0.0.1:{port}/mcp", process

    @staticmethod
    def discover_when_ready(url: str, process: subprocess.Popen[str]) -> list[dict[str, object]]:
        last_error: Exception | None = None
        for _ in range(50):
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                raise AssertionError(f"fake MCP exited early: {output}")
            try:
                return asyncio.run(discover_streamable_http(url, ""))
            except Exception as exc:  # server may still be binding its socket
                last_error = exc
                time.sleep(0.1)
        raise AssertionError(f"fake MCP did not become ready: {last_error}")

    def test_two_independent_servers_with_same_tool_route_without_collision(self) -> None:
        first_url, first_process = self.start_server("independent-alpha")
        second_url, second_process = self.start_server("independent-beta")
        first_inventory = self.discover_when_ready(first_url, first_process)
        second_inventory = self.discover_when_ready(second_url, second_process)

        self.assertIn("ha_get_addon", {tool["name"] for tool in first_inventory})
        self.assertIn("ha_get_addon", {tool["name"] for tool in second_inventory})

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "control_plane.db"
            initialize_database(database)
            control_plane = ControlPlane(database, root / "private")

            first_connector = control_plane.create_connector(
                "Independent Alpha",
                first_url,
                "",
                first_inventory,
                "integration-alpha",
            )
            second_connector = control_plane.create_connector(
                "Independent Beta",
                second_url,
                "",
                second_inventory,
                "integration-beta",
            )
            task_id = control_plane.create_task(
                "Duplicate tool routing",
                "duplicate_tool_routing",
                "Call each independently configured connector and preserve its identity.",
                1,
                [
                    {"connector_id": first_connector, "tool_name": "ha_get_addon"},
                    {"connector_id": second_connector, "tool_name": "ha_get_addon"},
                ],
                "integration-task",
            )
            task = control_plane.list_tasks()[0]
            self.assertEqual(task["id"], task_id)
            self.assertEqual(task["status"], "ready")
            self.assertEqual(len(task["tools"]), 2)
            virtual_names = [tool["namespaced_name"] for tool in task["tools"]]
            self.assertEqual(len(set(virtual_names)), 2)
            self.assertEqual({tool["tool_name"] for tool in task["tools"]}, {"ha_get_addon"})

            job_id = control_plane.enqueue_manual_task(task_id, {}, "integration-job")
            created = control_plane.create_identity(
                "Integration worker",
                "client",
                ["jobs.claim"],
                "integration-worker",
            )
            worker = control_plane.authenticate(created.credential.token)
            advertised = control_plane.next_queued_capabilities(worker)
            self.assertEqual({item["name"] for item in advertised}, set(virtual_names))
            lease = control_plane.claim_job(worker, "integration-claim")
            self.assertIsNotNone(lease)
            assert lease is not None
            self.assertEqual(lease.job["id"], job_id)

            observed_markers: set[str] = set()
            routed_connectors: set[str] = set()
            for virtual_name in virtual_names:
                resolved = control_plane.resolve_active_capability(
                    worker,
                    virtual_name,
                    {"slug": "gatus", "source": "installed"},
                    f"integration-{virtual_name}",
                )
                routed_connectors.add(str(resolved["connector_id"]))
                result = asyncio.run(
                    invoke_streamable_http(
                        str(resolved["url"]),
                        str(resolved["bearer_token"]),
                        str(resolved["tool_name"]),
                        resolved["arguments"],
                    )
                )
                encoded = json.dumps(result, ensure_ascii=False)
                if "independent-alpha" in encoded:
                    observed_markers.add("independent-alpha")
                if "independent-beta" in encoded:
                    observed_markers.add("independent-beta")

            self.assertEqual(routed_connectors, {first_connector, second_connector})
            self.assertEqual(observed_markers, {"independent-alpha", "independent-beta"})


if __name__ == "__main__":
    unittest.main()
