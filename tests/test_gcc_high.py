"""
Tests for GCC High greenfield fixtures.

Tests:
- Health endpoint returns gcc-high cloud
- Organization has correct Federal name
- Users have contoso-defense.us domain
- Me endpoint is singleton (no value key)
- All endpoints use graph.microsoft.us URLs
- Secure scores have expected values
- Directory roles present
- Service principals include Microsoft Graph
- No placeholders (_TODO fields) in responses
- Auth methods policy is singleton
"""

import subprocess
import time
import socket
from pathlib import Path
import pytest
import httpx


def get_free_port():
    """Get a free port by creating a socket and letting the OS assign one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture(scope="session")
def mock_server_gcc_high():
    """
    Session-scoped fixture that starts m365-sim server for GCC High.

    - Starts: python server.py --cloud gcc-high --port {port}
    - Waits for /health to respond
    - Yields f"http://localhost:{port}"
    - Kills subprocess on teardown
    """
    port = get_free_port()
    url = f"http://localhost:{port}"

    # Find git root
    git_root = Path(__file__).parent.parent
    while git_root != git_root.parent and not (git_root / ".git").exists():
        git_root = git_root.parent

    # Start subprocess with gcc-high cloud
    process = subprocess.Popen(
        ["python3", "server.py", "--cloud", "gcc-high", "--port", str(port)],
        cwd=str(git_root),
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
        raise RuntimeError(f"GCC High server failed to start on port {port} within {timeout}s")

    yield url

    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture
def auth_headers():
    """Return Bearer token headers for authenticated requests."""
    return {"Authorization": "Bearer test-token"}


class TestGccHighHealth:
    """Health endpoint tests for GCC High."""

    def test_gcc_high_health(self, mock_server_gcc_high):
        """GET /health returns 200 with cloud: gcc-high."""
        response = httpx.get(f"{mock_server_gcc_high}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["scenario"] == "greenfield"
        assert data["cloud"] == "gcc-high"


class TestGccHighIdentity:
    """Identity and organization tests for GCC High."""

    def test_gcc_high_organization_name(self, mock_server_gcc_high, auth_headers):
        """Organization displayName is 'Contoso Defense Federal LLC'."""
        response = httpx.get(f"{mock_server_gcc_high}/v1.0/organization", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) > 0
        assert data["value"][0]["displayName"] == "Contoso Defense Federal LLC"

    def test_gcc_high_organization_domains(self, mock_server_gcc_high, auth_headers):
        """Organization includes contoso-defense.us domain."""
        response = httpx.get(f"{mock_server_gcc_high}/v1.0/organization", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        verified_domains = data["value"][0]["verifiedDomains"]
        domain_names = [d["name"] for d in verified_domains]
        assert "contoso-defense.us" in domain_names

    def test_gcc_high_users_count(self, mock_server_gcc_high, auth_headers):
        """GET /v1.0/users returns exactly 2 users."""
        response = httpx.get(f"{mock_server_gcc_high}/v1.0/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) == 2

    def test_gcc_high_users_domain(self, mock_server_gcc_high, auth_headers):
        """Both users have contoso-defense.us domain in UPN."""
        response = httpx.get(f"{mock_server_gcc_high}/v1.0/users", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        for user in data["value"]:
            assert user["userPrincipalName"].endswith("@contoso-defense.us")

    def test_gcc_high_me_singleton(self, mock_server_gcc_high, auth_headers):
        """GET /v1.0/me returns singleton (no value key)."""
        response = httpx.get(f"{mock_server_gcc_high}/v1.0/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "value" not in data
        assert "displayName" in data
        assert data["displayName"] == "Federal Admin"


class TestGccHighContext:
    """@odata.context URL tests for GCC High."""

    def test_gcc_high_odata_context_url(self, mock_server_gcc_high, auth_headers):
        """All endpoints use graph.microsoft.us in @odata.context."""
        endpoints = [
            "/v1.0/users",
            "/v1.0/organization",
            "/v1.0/domains",
            "/v1.0/groups",
        ]
        for endpoint in endpoints:
            response = httpx.get(f"{mock_server_gcc_high}{endpoint}", headers=auth_headers)
            assert response.status_code == 200
            data = response.json()
            assert "@odata.context" in data
            assert "graph.microsoft.us" in data["@odata.context"]


class TestGccHighSecurity:
    """Security and compliance tests for GCC High."""

    def test_gcc_high_secure_scores(self, mock_server_gcc_high, auth_headers):
        """Secure scores have currentScore 12.0 and maxScore 198.0."""
        response = httpx.get(f"{mock_server_gcc_high}/v1.0/security/secureScores", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) > 0
        score = data["value"][0]
        assert score["currentScore"] == 12.0
        assert score["maxScore"] == 198.0

    def test_gcc_high_directory_roles(self, mock_server_gcc_high, auth_headers):
        """Directory roles has at least 10 roles."""
        response = httpx.get(f"{mock_server_gcc_high}/v1.0/directoryRoles", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        assert len(data["value"]) >= 10

    def test_gcc_high_service_principals(self, mock_server_gcc_high, auth_headers):
        """Service principals includes Microsoft Graph SP."""
        response = httpx.get(f"{mock_server_gcc_high}/v1.0/servicePrincipals", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "value" in data
        sp_names = [sp["displayName"] for sp in data["value"]]
        assert "Microsoft Graph" in sp_names

    def test_gcc_high_no_placeholders(self, mock_server_gcc_high, auth_headers):
        """No _TODO fields in any response body."""
        endpoints = [
            "/v1.0/users",
            "/v1.0/organization",
            "/v1.0/domains",
            "/v1.0/groups",
            "/v1.0/security/secureScores",
            "/v1.0/directoryRoles",
            "/v1.0/servicePrincipals",
            "/v1.0/policies/authenticationMethodsPolicy",
        ]
        for endpoint in endpoints:
            response = httpx.get(f"{mock_server_gcc_high}{endpoint}", headers=auth_headers)
            assert response.status_code == 200
            body_text = response.text
            assert "_TODO" not in body_text

    def test_gcc_high_auth_methods_policy(self, mock_server_gcc_high, auth_headers):
        """Auth methods policy is singleton with authenticationMethodConfigurations array."""
        response = httpx.get(
            f"{mock_server_gcc_high}/v1.0/policies/authenticationMethodsPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "authenticationMethodConfigurations" in data
        assert isinstance(data["authenticationMethodConfigurations"], list)
        assert len(data["authenticationMethodConfigurations"]) == 4
