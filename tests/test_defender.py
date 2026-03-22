"""
Tests for Defender for Endpoint API endpoints (/api/*).

Tests coverage:
- All 7 endpoints return 200 with correct response shape
- Auth enforcement (no header → 401)
- Scenario-specific data validation (greenfield, hardened, partial)
- Query parameters ($top, $filter)
- Parameterized endpoints (machine_id)
- Unmapped /api/unknown returns 404
"""

import pytest
import httpx


class TestDefenderEndpointStructure:
    """Test that all Defender endpoints exist and return correct shapes."""

    def test_alerts_returns_200_with_value(self, mock_server, auth_headers):
        """GET /api/alerts returns 200 with value array."""
        response = httpx.get(f"{mock_server}/api/alerts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert isinstance(data["value"], list)
        assert "@odata.context" in data

    def test_apps_returns_200_with_value(self, mock_server, auth_headers):
        """GET /api/apps returns 200 with value array."""
        response = httpx.get(f"{mock_server}/api/apps", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert isinstance(data["value"], list)
        assert "@odata.context" in data

    def test_deviceavinfo_returns_200_with_value(self, mock_server, auth_headers):
        """GET /api/deviceavinfo returns 200 with value array."""
        response = httpx.get(f"{mock_server}/api/deviceavinfo", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert isinstance(data["value"], list)
        assert "@odata.context" in data

    def test_recommendations_returns_200_with_value(self, mock_server, auth_headers):
        """GET /api/machines/{machine_id}/recommendations returns 200 with value array."""
        response = httpx.get(
            f"{mock_server}/api/machines/test-machine-id/recommendations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert isinstance(data["value"], list)
        assert "@odata.context" in data

    def test_vulnerabilities_returns_200_with_value(self, mock_server, auth_headers):
        """GET /api/machines/{machine_id}/vulnerabilities returns 200 with value array."""
        response = httpx.get(
            f"{mock_server}/api/machines/test-machine-id/vulnerabilities",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert isinstance(data["value"], list)
        assert "@odata.context" in data

    def test_appcontrol_returns_200_with_value(self, mock_server, auth_headers):
        """GET /api/policies/appcontrol returns 200 with value array."""
        response = httpx.get(f"{mock_server}/api/policies/appcontrol", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert isinstance(data["value"], list)
        assert "@odata.context" in data

    def test_machine_vulnerabilities_returns_200_with_value(self, mock_server, auth_headers):
        """GET /api/vulnerabilities/machinesVulnerabilities returns 200 with value array."""
        response = httpx.get(
            f"{mock_server}/api/vulnerabilities/machinesVulnerabilities",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert isinstance(data["value"], list)
        assert "@odata.context" in data


class TestDefenderAuthentication:
    """Test authentication enforcement on Defender endpoints."""

    def test_alerts_auth_required(self, mock_server):
        """GET /api/alerts without auth returns 401."""
        response = httpx.get(f"{mock_server}/api/alerts")
        assert response.status_code == 401
        data = response.json()
        assert "error" in data

    def test_apps_auth_required(self, mock_server):
        """GET /api/apps without auth returns 401."""
        response = httpx.get(f"{mock_server}/api/apps")
        assert response.status_code == 401

    def test_deviceavinfo_auth_required(self, mock_server):
        """GET /api/deviceavinfo without auth returns 401."""
        response = httpx.get(f"{mock_server}/api/deviceavinfo")
        assert response.status_code == 401

    def test_recommendations_auth_required(self, mock_server):
        """GET /api/machines/{machine_id}/recommendations without auth returns 401."""
        response = httpx.get(f"{mock_server}/api/machines/test-id/recommendations")
        assert response.status_code == 401

    def test_vulnerabilities_auth_required(self, mock_server):
        """GET /api/machines/{machine_id}/vulnerabilities without auth returns 401."""
        response = httpx.get(f"{mock_server}/api/machines/test-id/vulnerabilities")
        assert response.status_code == 401

    def test_appcontrol_auth_required(self, mock_server):
        """GET /api/policies/appcontrol without auth returns 401."""
        response = httpx.get(f"{mock_server}/api/policies/appcontrol")
        assert response.status_code == 401

    def test_machine_vulnerabilities_auth_required(self, mock_server):
        """GET /api/vulnerabilities/machinesVulnerabilities without auth returns 401."""
        response = httpx.get(f"{mock_server}/api/vulnerabilities/machinesVulnerabilities")
        assert response.status_code == 401


class TestDefenderGreenfield:
    """Test Defender endpoints in greenfield scenario (no Defender deployment)."""

    def test_greenfield_alerts_empty(self, mock_server, auth_headers):
        """Greenfield: /api/alerts returns empty value array."""
        response = httpx.get(f"{mock_server}/api/alerts", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_greenfield_apps_empty(self, mock_server, auth_headers):
        """Greenfield: /api/apps returns empty value array."""
        response = httpx.get(f"{mock_server}/api/apps", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_greenfield_deviceavinfo_empty(self, mock_server, auth_headers):
        """Greenfield: /api/deviceavinfo returns empty value array."""
        response = httpx.get(f"{mock_server}/api/deviceavinfo", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_greenfield_recommendations_empty(self, mock_server, auth_headers):
        """Greenfield: /api/machines/{id}/recommendations returns empty."""
        response = httpx.get(
            f"{mock_server}/api/machines/test-id/recommendations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_greenfield_vulnerabilities_empty(self, mock_server, auth_headers):
        """Greenfield: /api/machines/{id}/vulnerabilities returns empty."""
        response = httpx.get(
            f"{mock_server}/api/machines/test-id/vulnerabilities",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_greenfield_appcontrol_empty(self, mock_server, auth_headers):
        """Greenfield: /api/policies/appcontrol returns empty."""
        response = httpx.get(f"{mock_server}/api/policies/appcontrol", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_greenfield_machine_vulnerabilities_empty(self, mock_server, auth_headers):
        """Greenfield: /api/vulnerabilities/machinesVulnerabilities returns empty."""
        response = httpx.get(
            f"{mock_server}/api/vulnerabilities/machinesVulnerabilities",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []


class TestDefenderHardened:
    """Test Defender endpoints in hardened scenario."""

    def test_hardened_alerts_resolved(self, mock_server_hardened, auth_headers):
        """Hardened: /api/alerts returns resolved historical alerts."""
        response = httpx.get(
            f"{mock_server_hardened}/api/alerts", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 3
        # All alerts should be resolved
        for alert in data["value"]:
            assert alert["status"] == "Resolved"
            assert alert["resolvedTime"] is not None

    def test_hardened_apps_populated(self, mock_server_hardened, auth_headers):
        """Hardened: /api/apps returns 10 discovered applications."""
        response = httpx.get(
            f"{mock_server_hardened}/api/apps", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 10
        # Verify expected apps are present
        app_names = [app["name"] for app in data["value"]]
        assert "Windows Defender" in app_names
        assert "Microsoft 365 Apps for enterprise" in app_names

    def test_hardened_deviceavinfo_enabled(self, mock_server_hardened, auth_headers):
        """Hardened: /api/deviceavinfo returns 3 devices with AV enabled."""
        response = httpx.get(
            f"{mock_server_hardened}/api/deviceavinfo", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 3
        # All devices should have AV enabled with current definitions
        for device in data["value"]:
            assert device["avIsRunning"] is True
            assert device["avSignatureVersion"] is not None
            assert device["avEngineVersion"] is not None

    def test_hardened_recommendations_completed(self, mock_server_hardened, auth_headers):
        """Hardened: /api/machines/{id}/recommendations returns 5 completed recommendations."""
        response = httpx.get(
            f"{mock_server_hardened}/api/machines/test-id/recommendations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 5
        # All recommendations should be completed
        for rec in data["value"]:
            assert rec["status"] == "Completed"
            assert rec["affectedMachineCount"] == 0

    def test_hardened_vulnerabilities_empty(self, mock_server_hardened, auth_headers):
        """Hardened: /api/machines/{id}/vulnerabilities returns empty (all patched)."""
        response = httpx.get(
            f"{mock_server_hardened}/api/machines/test-id/vulnerabilities",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_hardened_appcontrol_enforced(self, mock_server_hardened, auth_headers):
        """Hardened: /api/policies/appcontrol returns 2 WDAC policies (audit + enforced)."""
        response = httpx.get(
            f"{mock_server_hardened}/api/policies/appcontrol", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 2
        # One in audit, one in enforce mode
        modes = [policy["mode"] for policy in data["value"]]
        assert "Audit" in modes
        assert "Enforce" in modes

    def test_hardened_machine_vulnerabilities_empty(self, mock_server_hardened, auth_headers):
        """Hardened: /api/vulnerabilities/machinesVulnerabilities returns empty."""
        response = httpx.get(
            f"{mock_server_hardened}/api/vulnerabilities/machinesVulnerabilities",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []


class TestDefenderPartial:
    """Test Defender endpoints in partial scenario (mid-deployment)."""

    def test_partial_alerts_active(self, mock_server_partial, auth_headers):
        """Partial: /api/alerts returns 3 active alerts (not resolved)."""
        response = httpx.get(
            f"{mock_server_partial}/api/alerts", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 3
        # All alerts should be active/in-progress
        for alert in data["value"]:
            assert alert["status"] == "InProgress"
            assert alert["resolvedTime"] is None

    def test_partial_deviceavinfo_one_device(self, mock_server_partial, auth_headers):
        """Partial: /api/deviceavinfo returns 1 device with stale definitions."""
        response = httpx.get(
            f"{mock_server_partial}/api/deviceavinfo", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 1
        device = data["value"][0]
        assert device["avIsRunning"] is True
        # Stale signature version (older than hardened)
        assert device["avSignatureVersion"] == "1.338.1234.0"

    def test_partial_appcontrol_empty(self, mock_server_partial, auth_headers):
        """Partial: /api/policies/appcontrol returns empty (WDAC not deployed)."""
        response = httpx.get(
            f"{mock_server_partial}/api/policies/appcontrol", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []


class TestDefenderQueryParameters:
    """Test query parameter support on Defender endpoints."""

    def test_alerts_top_parameter(self, mock_server_hardened, auth_headers):
        """GET /api/alerts?$top=1 returns 1 alert."""
        response = httpx.get(
            f"{mock_server_hardened}/api/alerts?$top=1", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 1

    def test_apps_top_parameter(self, mock_server_hardened, auth_headers):
        """GET /api/apps?$top=5 returns 5 apps (max 10 available)."""
        response = httpx.get(
            f"{mock_server_hardened}/api/apps?$top=5", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 5

    def test_deviceavinfo_top_parameter(self, mock_server_hardened, auth_headers):
        """GET /api/deviceavinfo?$top=2 returns 2 devices."""
        response = httpx.get(
            f"{mock_server_hardened}/api/deviceavinfo?$top=2", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 2

    def test_alerts_filter_parameter(self, mock_server_hardened, auth_headers):
        """GET /api/alerts?$filter=... applies filter gracefully."""
        response = httpx.get(
            f"{mock_server_hardened}/api/alerts?$filter=severity eq 'Medium'",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Filter may be ignored or applied; we just verify 200 response
        assert "value" in data


class TestDefenderParameterizedEndpoints:
    """Test parameterized machine endpoints with different IDs."""

    def test_recommendations_different_machine_ids(self, mock_server, auth_headers):
        """GET /api/machines/{machine_id}/recommendations works with any ID."""
        for machine_id in ["machine-1", "uuid-abcdef", "12345"]:
            response = httpx.get(
                f"{mock_server}/api/machines/{machine_id}/recommendations",
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert "value" in data

    def test_vulnerabilities_different_machine_ids(self, mock_server, auth_headers):
        """GET /api/machines/{machine_id}/vulnerabilities works with any ID."""
        for machine_id in ["machine-1", "uuid-abcdef", "12345"]:
            response = httpx.get(
                f"{mock_server}/api/machines/{machine_id}/vulnerabilities",
                headers=auth_headers,
            )
            assert response.status_code == 200
            data = response.json()
            assert "value" in data


class TestDefenderErrorHandling:
    """Test error cases and 404 handling."""

    def test_unmapped_api_endpoint_404(self, mock_server, auth_headers):
        """GET /api/unknown returns 404."""
        response = httpx.get(f"{mock_server}/api/unknown", headers=auth_headers)
        assert response.status_code == 404
        data = response.json()
        assert "error" in data

    def test_malformed_api_path_404(self, mock_server, auth_headers):
        """GET /api/nonexistent/path returns 404."""
        response = httpx.get(f"{mock_server}/api/nonexistent/path", headers=auth_headers)
        assert response.status_code == 404


@pytest.fixture(scope="session")
def mock_server_partial():
    """Session-scoped fixture for partial scenario."""
    import subprocess
    import time
    import socket
    from pathlib import Path

    def get_free_port():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port

    port = get_free_port()
    url = f"http://localhost:{port}"

    git_root = Path(__file__).parent.parent
    while git_root != git_root.parent and not (git_root / ".git").exists():
        git_root = git_root.parent

    process = subprocess.Popen(
        ["python3", "server.py", "--scenario", "partial", "--port", str(port)],
        cwd=str(git_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

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

    yield url

    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
