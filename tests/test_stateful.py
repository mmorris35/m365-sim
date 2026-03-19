"""
Stateful write operation tests for m365-sim.

Tests:
- POST operations mutating fixture state
- PATCH operations merging config state
- POST /_reset clearing mutations
- Deploy-then-verify workflow
- Stateless mode remains unchanged

Uses mock_server_stateful fixture (subprocess with --stateful flag).
"""

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


@pytest.fixture(scope="function")
def mock_server_stateful():
    """
    Function-scoped fixture that starts m365-sim server with --stateful flag.

    - Picks a random available port
    - Starts: python server.py --port {port} --stateful
    - Waits for /health to respond (retry loop, 5s timeout)
    - Yields f"http://localhost:{port}"
    - Kills subprocess on teardown
    """
    port = get_free_port()
    url = f"http://localhost:{port}"

    # Start subprocess with --stateful flag
    process = subprocess.Popen(
        ["python3", "server.py", "--port", str(port), "--stateful"],
        cwd="/home/mmn/github/m365-sim",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready (retry loop, 5s timeout)
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
        # Timeout reached
        process.kill()
        raise RuntimeError(f"Server failed to start on port {port} within {timeout}s")

    yield url

    # Cleanup: kill subprocess
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture
def auth_headers():
    """Return Bearer token headers for authenticated requests."""
    return {"Authorization": "Bearer test-token"}


class TestStatefulPostOperations:
    """Tests for POST operations that mutate fixture state."""

    def test_post_ca_policy_then_get(self, mock_server_stateful, auth_headers):
        """POST a CA policy, then GET policies returns it."""
        # GET policies before POST
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        initial_count = len(response.json()["value"])

        # POST new policy
        policy_payload = {
            "displayName": "Test CA Policy",
            "state": "enabledForReportingButNotEnforced",
            "conditions": {"users": {"includeUsers": ["all"]}},
        }
        post_response = httpx.post(
            f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
            json=policy_payload,
        )
        assert post_response.status_code == 201
        posted_policy = post_response.json()
        assert "id" in posted_policy
        assert "createdDateTime" in posted_policy
        policy_id = posted_policy["id"]

        # GET policies after POST
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == initial_count + 1

        # Verify the policy is in the response
        policy_ids = [p["id"] for p in data["value"]]
        assert policy_id in policy_ids

    def test_post_multiple_ca_policies(self, mock_server_stateful, auth_headers):
        """POST 3 policies, GET returns all 3 (plus any originals)."""
        # GET initial policies
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        initial_count = len(response.json()["value"])

        # POST 3 policies
        policy_ids = []
        for i in range(3):
            policy_payload = {
                "displayName": f"Test Policy {i+1}",
                "state": "enabledForReportingButNotEnforced",
                "conditions": {"users": {"includeUsers": ["all"]}},
            }
            post_response = httpx.post(
                f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
                headers=auth_headers,
                json=policy_payload,
            )
            assert post_response.status_code == 201
            policy_ids.append(post_response.json()["id"])

        # GET policies after POST
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == initial_count + 3

        # Verify all 3 are in the response
        response_ids = [p["id"] for p in data["value"]]
        for policy_id in policy_ids:
            assert policy_id in response_ids

    def test_post_compliance_policy_then_get(self, mock_server_stateful, auth_headers):
        """POST compliance policy, GET returns it."""
        # GET policies before POST
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/deviceManagement/deviceCompliancePolicies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        initial_count = len(response.json()["value"])

        # POST compliance policy
        policy_payload = {
            "displayName": "Test Compliance Policy",
            "description": "A test policy",
            "platform": "ios",
        }
        post_response = httpx.post(
            f"{mock_server_stateful}/v1.0/deviceManagement/deviceCompliancePolicies",
            headers=auth_headers,
            json=policy_payload,
        )
        assert post_response.status_code == 201
        policy_id = post_response.json()["id"]

        # GET policies after POST
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/deviceManagement/deviceCompliancePolicies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == initial_count + 1

        # Verify the policy is in the response
        policy_ids = [p["id"] for p in data["value"]]
        assert policy_id in policy_ids

    def test_post_device_config_then_get(self, mock_server_stateful, auth_headers):
        """POST device config, GET returns it."""
        # GET configs before POST
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/deviceManagement/deviceConfigurations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        initial_count = len(response.json()["value"])

        # POST device config
        config_payload = {
            "displayName": "Test Device Config",
            "description": "A test config",
        }
        post_response = httpx.post(
            f"{mock_server_stateful}/v1.0/deviceManagement/deviceConfigurations",
            headers=auth_headers,
            json=config_payload,
        )
        assert post_response.status_code == 201
        config_id = post_response.json()["id"]

        # GET configs after POST
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/deviceManagement/deviceConfigurations",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == initial_count + 1

        # Verify the config is in the response
        config_ids = [c["id"] for c in data["value"]]
        assert config_id in config_ids


class TestStatefulPatchOperations:
    """Tests for PATCH operations that mutate fixture state."""

    def test_patch_auth_method_then_get(self, mock_server_stateful, auth_headers):
        """PATCH fido2 to enabled, GET auth methods policy shows fido2 enabled."""
        # GET auth methods before PATCH
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/policies/authenticationMethodsPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        configs_before = response.json().get("authenticationMethodConfigurations", [])

        # Find fido2 config and note its initial state
        fido2_config = None
        for config in configs_before:
            if config.get("id") == "fido2":
                fido2_config = config
                break
        assert fido2_config is not None, "fido2 config not found in auth methods"

        # PATCH fido2 to enabled
        patch_payload = {"state": "enabled"}
        patch_response = httpx.patch(
            f"{mock_server_stateful}/v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/fido2",
            headers=auth_headers,
            json=patch_payload,
        )
        assert patch_response.status_code == 200

        # GET auth methods after PATCH
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/policies/authenticationMethodsPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        configs_after = response.json().get("authenticationMethodConfigurations", [])

        # Verify fido2 is now enabled
        fido2_after = None
        for config in configs_after:
            if config.get("id") == "fido2":
                fido2_after = config
                break
        assert fido2_after is not None
        assert fido2_after.get("state") == "enabled"

    def test_patch_auth_method_preserves_others(
        self, mock_server_stateful, auth_headers
    ):
        """PATCH fido2, verify other methods unchanged."""
        # GET auth methods before PATCH
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/policies/authenticationMethodsPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        configs_before = {
            c["id"]: c for c in response.json().get("authenticationMethodConfigurations", [])
        }

        # PATCH fido2
        patch_response = httpx.patch(
            f"{mock_server_stateful}/v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/Fido2",
            headers=auth_headers,
            json={"state": "enabled"},
        )
        assert patch_response.status_code == 200

        # GET auth methods after PATCH
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/policies/authenticationMethodsPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        configs_after = {
            c["id"]: c for c in response.json().get("authenticationMethodConfigurations", [])
        }

        # Verify all other methods unchanged
        for method_id in configs_before:
            if method_id == "Fido2":
                continue  # Skip the one we patched
            assert configs_after[method_id] == configs_before[method_id], (
                f"Method {method_id} was changed unexpectedly"
            )


class TestReset:
    """Tests for POST /_reset endpoint."""

    def test_reset_clears_mutations(self, mock_server_stateful, auth_headers):
        """POST policies, POST /_reset, GET returns original state."""
        # GET initial policies count
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        initial_count = len(response.json()["value"])

        # POST a policy
        policy_payload = {
            "displayName": "Test Policy",
            "state": "enabledForReportingButNotEnforced",
            "conditions": {"users": {"includeUsers": ["all"]}},
        }
        post_response = httpx.post(
            f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
            json=policy_payload,
        )
        assert post_response.status_code == 201

        # Verify policy was added
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert len(response.json()["value"]) == initial_count + 1

        # POST /_reset
        reset_response = httpx.post(
            f"{mock_server_stateful}/v1.0/_reset",
            headers=auth_headers,
        )
        assert reset_response.status_code == 200
        reset_data = reset_response.json()
        assert reset_data["status"] == "reset"
        assert reset_data["fixtures_loaded"] > 0

        # Verify policies returned to original count
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert len(response.json()["value"]) == initial_count

    def test_reset_returns_fixture_count(self, mock_server_stateful, auth_headers):
        """POST /_reset returns fixture count in response."""
        reset_response = httpx.post(
            f"{mock_server_stateful}/v1.0/_reset",
            headers=auth_headers,
        )
        assert reset_response.status_code == 200
        data = reset_response.json()
        assert "status" in data
        assert data["status"] == "reset"
        assert "fixtures_loaded" in data
        assert isinstance(data["fixtures_loaded"], int)
        assert data["fixtures_loaded"] > 0


class TestStatelessModeUnchanged:
    """Tests to verify stateless mode (existing mock_server) still works."""

    def test_stateless_mode_post_does_not_mutate(self, mock_server, auth_headers):
        """Existing mock_server (no --stateful) POST doesn't mutate state."""
        # POST a policy on stateless server
        policy_payload = {
            "displayName": "Test Policy",
            "state": "enabledForReportingButNotEnforced",
            "conditions": {"users": {"includeUsers": ["all"]}},
        }
        post_response = httpx.post(
            f"{mock_server}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
            json=policy_payload,
        )
        assert post_response.status_code == 201

        # GET policies should NOT include the posted policy
        response = httpx.get(
            f"{mock_server}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        # Verify posted policy is NOT in the response
        posted_id = post_response.json()["id"]
        response_ids = [p["id"] for p in data["value"]]
        assert posted_id not in response_ids


class TestDeployThenAssessFlow:
    """End-to-end deploy-then-verify workflow tests."""

    def test_deploy_then_assess_flow(self, mock_server_stateful, auth_headers):
        """Full workflow: POST policies + PATCH auth methods, then verify all mutations visible."""
        # Phase 1: Deploy (POST CA policies and PATCH auth methods)

        # POST 3 CA policies
        policy_ids = []
        for i in range(3):
            policy_payload = {
                "displayName": f"Policy {i+1}",
                "state": "enabledForReportingButNotEnforced",
                "conditions": {"users": {"includeUsers": ["all"]}},
            }
            post_response = httpx.post(
                f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
                headers=auth_headers,
                json=policy_payload,
            )
            assert post_response.status_code == 201
            policy_ids.append(post_response.json()["id"])

        # PATCH 2 auth methods
        for method_id in ["fido2", "microsoftAuthenticator"]:
            patch_response = httpx.patch(
                f"{mock_server_stateful}/v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id}",
                headers=auth_headers,
                json={"state": "enabled"},
            )
            assert patch_response.status_code == 200

        # Phase 2: Assess (GET endpoints and verify mutations)

        # Get CA policies and verify all 3 are present
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        response_ids = [p["id"] for p in response.json()["value"]]
        for policy_id in policy_ids:
            assert policy_id in response_ids, f"Policy {policy_id} not found in GET response"

        # Get auth methods and verify both are enabled
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/policies/authenticationMethodsPolicy",
            headers=auth_headers,
        )
        assert response.status_code == 200
        configs = {
            c["id"]: c for c in response.json().get("authenticationMethodConfigurations", [])
        }
        assert configs["fido2"]["state"] == "enabled", "fido2 not enabled"
        assert (
            configs["microsoftAuthenticator"]["state"] == "enabled"
        ), "microsoftAuthenticator not enabled"

    def test_deploy_reset_assess_flow(self, mock_server_stateful, auth_headers):
        """Deploy, reset, then verify clean state."""
        # Get initial policies count
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        initial_count = len(response.json()["value"])

        # POST a policy
        policy_payload = {
            "displayName": "Test Policy",
            "state": "enabledForReportingButNotEnforced",
            "conditions": {"users": {"includeUsers": ["all"]}},
        }
        post_response = httpx.post(
            f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
            json=policy_payload,
        )
        assert post_response.status_code == 201

        # Reset
        reset_response = httpx.post(
            f"{mock_server_stateful}/v1.0/_reset",
            headers=auth_headers,
        )
        assert reset_response.status_code == 200

        # Verify clean state
        response = httpx.get(
            f"{mock_server_stateful}/v1.0/identity/conditionalAccess/policies",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert len(response.json()["value"]) == initial_count
