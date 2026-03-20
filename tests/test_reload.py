"""
Tests for hot-reload fixtures functionality.

Tests:
- POST /_reload returns 200 with fixture count
- POST /_reload picks up changes to fixture files
- /health shows watch status
- Reloading doesn't break existing endpoints
"""

import json
import tempfile
import shutil
from pathlib import Path
import subprocess
import time
import socket
import pytest
import httpx


def get_free_port():
    """Get a free port by creating a socket and letting the OS assign one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture
def temp_scenario_server():
    """
    Start a server with a temporary scenario directory.

    Copies the greenfield scenario and server.py to a temp directory and starts
    the server. This allows tests to modify fixture files without affecting
    the real fixtures.

    Yields the URL and temp directory path.
    """
    port = get_free_port()
    url = f"http://localhost:{port}"

    # Find git root
    git_root = Path(__file__).parent.parent
    while git_root != git_root.parent and not (git_root / ".git").exists():
        git_root = git_root.parent

    # Copy greenfield scenario to temp directory
    src_scenario = git_root / "scenarios" / "gcc-moderate" / "greenfield"
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        scenarios_dir = tmpdir_path / "scenarios" / "gcc-moderate" / "greenfield"
        scenarios_dir.mkdir(parents=True)

        # Copy all JSON files
        for json_file in src_scenario.glob("*.json"):
            shutil.copy2(json_file, scenarios_dir / json_file.name)

        # Copy server.py to temp directory
        shutil.copy2(git_root / "server.py", tmpdir_path / "server.py")

        # Start subprocess with --scenario pointing to temp
        process = subprocess.Popen(
            ["python3", "server.py", "--port", str(port), "--scenario", "greenfield"],
            cwd=str(tmpdir_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Wait for server to be ready
        start_time = time.time()
        timeout = 5
        while time.time() - start_time < timeout:
            try:
                response = httpx.get(f"{url}/health", timeout=1.0)
                if response.status_code == 200:
                    break
            except (httpx.ConnectError, httpx.TimeoutException):
                time.sleep(0.1)
        else:
            process.kill()
            raise RuntimeError(f"Server failed to start on port {port} within {timeout}s")

        yield url, scenarios_dir

        # Cleanup
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()


class TestReloadEndpoint:
    """Tests for POST /_reload endpoint."""

    def test_reload_endpoint_returns_200(self, mock_server, auth_headers):
        """POST /v1.0/_reload returns 200 with fixture count and scenario."""
        response = httpx.post(f"{mock_server}/v1.0/_reload", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reloaded"
        assert "fixtures_loaded" in data
        assert data["fixtures_loaded"] > 0
        assert data["scenario"] == "greenfield"
        assert data["cloud"] == "gcc-moderate"

    def test_reload_picks_up_changes(self, temp_scenario_server, auth_headers):
        """After modifying a fixture file, POST /_reload picks up the change."""
        url, scenarios_dir = temp_scenario_server

        # Get initial user count
        response = httpx.get(f"{url}/v1.0/users", headers=auth_headers)
        assert response.status_code == 200
        initial_users = response.json()["value"]
        initial_count = len(initial_users)

        # Modify users.json to add a new user
        users_file = scenarios_dir / "users.json"
        with open(users_file, "r") as f:
            users_data = json.load(f)

        # Add a new user
        new_user = {
            "id": "new-user-id-test",
            "displayName": "Test User Added",
            "userPrincipalName": "testuser@contoso-defense.com",
            "mail": "testuser@contoso-defense.com",
        }
        users_data["value"].append(new_user)

        with open(users_file, "w") as f:
            json.dump(users_data, f)

        # Give server a moment to potentially auto-detect (though without --watch it won't)
        time.sleep(0.5)

        # Reload fixtures via POST /_reload
        response = httpx.post(f"{url}/v1.0/_reload", headers=auth_headers)
        assert response.status_code == 200

        # Verify the new user appears in the response
        response = httpx.get(f"{url}/v1.0/users", headers=auth_headers)
        assert response.status_code == 200
        updated_users = response.json()["value"]
        updated_count = len(updated_users)

        assert updated_count == initial_count + 1
        assert any(u.get("id") == "new-user-id-test" for u in updated_users)

    def test_health_shows_watch_false_by_default(self, mock_server):
        """GET /health returns watch: false by default."""
        response = httpx.get(f"{mock_server}/health")
        assert response.status_code == 200
        data = response.json()
        assert "watch" in data
        assert data["watch"] is False

    def test_reload_does_not_break_existing_fixtures(self, mock_server, auth_headers):
        """POST /_reload doesn't break subsequent endpoint calls."""
        # Reload
        response = httpx.post(f"{mock_server}/v1.0/_reload", headers=auth_headers)
        assert response.status_code == 200

        # Verify multiple endpoints still work
        response = httpx.get(f"{mock_server}/v1.0/users", headers=auth_headers)
        assert response.status_code == 200
        assert "value" in response.json()

        response = httpx.get(f"{mock_server}/v1.0/me", headers=auth_headers)
        assert response.status_code == 200

        response = httpx.get(f"{mock_server}/v1.0/devices", headers=auth_headers)
        assert response.status_code == 200
        assert "value" in response.json()
