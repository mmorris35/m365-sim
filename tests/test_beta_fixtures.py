"""
Tests for beta-specific fixtures with extended properties.

Beta fixtures add extended properties not available in v1.0:
- managed_devices: bitLockerStatus, tpmVersion, windowsMalwareProtection, wdagEnabled
- compliance_policies: assignments, scheduledActionsForRule
- device_configurations: omaSettings array
- conditional_access_policies: sessionControls.cloudAppSecurity, grantControls.authenticationStrength
- risk_detections: identity protection events (empty greenfield, populated hardened)
- attack_simulations: phishing results (empty greenfield, populated hardened)
- attack_trainings: training completion (empty greenfield, populated hardened)
- device_health_scripts: proactive remediations (empty greenfield, populated hardened)
- intents: security baselines (empty greenfield, populated hardened)
"""

import pytest
import httpx


class TestBetaManagedDevices:
    """Test beta-specific extended properties on managed devices."""

    def test_beta_managed_devices_greenfield_empty(self, mock_server, auth_headers):
        """Beta managed devices returns empty in greenfield."""
        response = httpx.get(
            f"{mock_server}/beta/deviceManagement/managedDevices",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []
        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]

    def test_beta_managed_devices_hardened_has_extended_fields(self, mock_server_hardened, auth_headers):
        """Beta managed devices in hardened have bitLockerStatus, tpmVersion, etc."""
        response = httpx.get(
            f"{mock_server_hardened}/beta/deviceManagement/managedDevices",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 3

        # Check first device has extended properties
        device = data["value"][0]
        assert "bitLockerStatus" in device
        assert "tpmVersion" in device
        assert "windowsMalwareProtection" in device
        assert "wdagEnabled" in device

        # Verify values for first Windows device
        assert device["bitLockerStatus"] == "encrypted"
        assert device["tpmVersion"] == "2.0"
        assert device["windowsMalwareProtection"]["realTimeProtectionEnabled"] is True
        assert device["wdagEnabled"] is True

        # Check iOS device (should have N/A for Windows-only fields)
        ios_device = data["value"][2]
        assert ios_device["bitLockerStatus"] == "notEncryptable"
        assert ios_device["tpmVersion"] == "N/A"


class TestBetaCompliancePolicies:
    """Test beta compliance policies with assignments and scheduledActionsForRule."""

    def test_beta_compliance_policies_greenfield_empty(self, mock_server, auth_headers):
        """Beta compliance policies returns empty in greenfield."""
        response = httpx.get(
            f"{mock_server}/beta/deviceManagement/deviceCompliancePolicies",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_beta_compliance_policies_hardened_has_assignments(self, mock_server_hardened, auth_headers):
        """Beta compliance policies in hardened have assignments and scheduledActionsForRule."""
        response = httpx.get(
            f"{mock_server_hardened}/beta/deviceManagement/deviceCompliancePolicies",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 3

        # Check first policy has assignments
        policy = data["value"][0]
        assert "assignments" in policy
        assert len(policy["assignments"]) > 0
        assert policy["assignments"][0]["target"]["@odata.type"] == "#microsoft.graph.allDevicesAssignmentTarget"

        # Check if policy has scheduledActionsForRule
        assert "scheduledActionsForRule" in policy
        if policy["scheduledActionsForRule"]:
            action_rule = policy["scheduledActionsForRule"][0]
            assert "ruleName" in action_rule
            assert "scheduledActionConfigurations" in action_rule


class TestBetaDeviceConfigurations:
    """Test beta device configurations with OMA-URI settings."""

    def test_beta_device_configurations_greenfield_empty(self, mock_server, auth_headers):
        """Beta device configurations returns empty in greenfield."""
        response = httpx.get(
            f"{mock_server}/beta/deviceManagement/deviceConfigurations",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_beta_device_configurations_hardened_has_oma_settings(self, mock_server_hardened, auth_headers):
        """Beta device configurations in hardened have omaSettings array."""
        response = httpx.get(
            f"{mock_server_hardened}/beta/deviceManagement/deviceConfigurations",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 1

        config = data["value"][0]
        assert "omaSettings" in config
        assert isinstance(config["omaSettings"], list)
        assert len(config["omaSettings"]) > 0

        # Check OMA setting structure
        oma_setting = config["omaSettings"][0]
        assert "omaUri" in oma_setting
        assert "displayName" in oma_setting
        assert "value" in oma_setting
        assert "dataType" in oma_setting


class TestBetaConditionalAccessPolicies:
    """Test beta CA policies with authenticationStrength and cloudAppSecurity."""

    def test_beta_ca_policies_greenfield_empty(self, mock_server, auth_headers):
        """Beta CA policies returns empty in greenfield."""
        response = httpx.get(
            f"{mock_server}/beta/identity/conditionalAccess/policies",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_beta_ca_policies_hardened_has_authentication_strength(self, mock_server_hardened, auth_headers):
        """Beta CA policies in hardened have authenticationStrength."""
        response = httpx.get(
            f"{mock_server_hardened}/beta/identity/conditionalAccess/policies",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 2

        # Check first policy has authenticationStrength
        policy = data["value"][0]
        assert "grantControls" in policy
        assert "authenticationStrength" in policy["grantControls"]
        assert "displayName" in policy["grantControls"]["authenticationStrength"]
        assert "allowedCombinations" in policy["grantControls"]["authenticationStrength"]

    def test_beta_ca_policies_hardened_has_cloud_app_security(self, mock_server_hardened, auth_headers):
        """Beta CA policies in hardened have cloudAppSecurity in sessionControls."""
        response = httpx.get(
            f"{mock_server_hardened}/beta/identity/conditionalAccess/policies",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()

        policy = data["value"][0]
        assert "sessionControls" in policy
        assert "cloudAppSecurity" in policy["sessionControls"]
        assert "isEnabled" in policy["sessionControls"]["cloudAppSecurity"]
        assert "cloudAppSecurityType" in policy["sessionControls"]["cloudAppSecurity"]


class TestBetaRiskDetections:
    """Test beta risk detection endpoint (identity protection)."""

    def test_beta_risk_detections_greenfield_empty(self, mock_server, auth_headers):
        """Beta risk detections returns empty in greenfield."""
        response = httpx.get(
            f"{mock_server}/beta/identityProtection/riskDetections",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []
        assert "@odata.context" in data
        assert "/beta/" in data["@odata.context"]

    def test_beta_risk_detections_hardened_populated(self, mock_server_hardened, auth_headers):
        """Beta risk detections in hardened have resolved risk events."""
        response = httpx.get(
            f"{mock_server_hardened}/beta/identityProtection/riskDetections",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 2

        # Check risk event structure
        risk_event = data["value"][0]
        assert "id" in risk_event
        assert "riskType" in risk_event
        assert "riskLevel" in risk_event
        assert "riskState" in risk_event
        assert risk_event["riskState"] == "resolved"  # Hardened shows resolved events
        assert "detectedDateTime" in risk_event
        assert "location" in risk_event


class TestBetaAttackSimulations:
    """Test beta attack simulation endpoint."""

    def test_beta_attack_simulations_greenfield_empty(self, mock_server, auth_headers):
        """Beta attack simulations returns empty in greenfield."""
        response = httpx.get(
            f"{mock_server}/beta/security/attackSimulation/simulations",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_beta_attack_simulations_hardened_populated(self, mock_server_hardened, auth_headers):
        """Beta attack simulations in hardened have completed simulation."""
        response = httpx.get(
            f"{mock_server_hardened}/beta/security/attackSimulation/simulations",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 1

        sim = data["value"][0]
        assert "displayName" in sim
        assert "status" in sim
        assert sim["status"] == "completed"
        assert "totalSubmission" in sim
        assert "successfulUserCount" in sim


class TestBetaAttackTrainings:
    """Test beta attack training endpoint."""

    def test_beta_attack_trainings_greenfield_empty(self, mock_server, auth_headers):
        """Beta attack trainings returns empty in greenfield."""
        response = httpx.get(
            f"{mock_server}/beta/security/attackSimulation/trainings",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_beta_attack_trainings_hardened_populated(self, mock_server_hardened, auth_headers):
        """Beta attack trainings in hardened have training completion records."""
        response = httpx.get(
            f"{mock_server_hardened}/beta/security/attackSimulation/trainings",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 2

        training = data["value"][0]
        assert "displayName" in training
        assert "completionUsers" in training
        assert "totalUsers" in training
        assert "percentageCompleted" in training


class TestBetaDeviceHealthScripts:
    """Test beta device health scripts endpoint (proactive remediations)."""

    def test_beta_device_health_scripts_greenfield_empty(self, mock_server, auth_headers):
        """Beta device health scripts returns empty in greenfield."""
        response = httpx.get(
            f"{mock_server}/beta/deviceManagement/deviceHealthScripts",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_beta_device_health_scripts_hardened_populated(self, mock_server_hardened, auth_headers):
        """Beta device health scripts in hardened have proactive remediation scripts."""
        response = httpx.get(
            f"{mock_server_hardened}/beta/deviceManagement/deviceHealthScripts",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 2

        script = data["value"][0]
        assert "displayName" in script
        assert "runSchedule" in script
        assert "detectionScriptContent" in script
        assert "remediationScriptContent" in script


class TestBetaSecurityIntents:
    """Test beta security intents endpoint."""

    def test_beta_security_intents_greenfield_empty(self, mock_server, auth_headers):
        """Beta security intents returns empty in greenfield."""
        response = httpx.get(
            f"{mock_server}/beta/security/securityIntents",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["value"] == []

    def test_beta_security_intents_hardened_populated(self, mock_server_hardened, auth_headers):
        """Beta security intents in hardened have applied baseline."""
        response = httpx.get(
            f"{mock_server_hardened}/beta/security/securityIntents",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["value"]) == 1

        intent = data["value"][0]
        assert "displayName" in intent
        assert "status" in intent
        assert intent["status"] == "completed"
        assert "completionPercentage" in intent
        assert "deploymentPackages" in intent


class TestV1NotAffectedByBeta:
    """Verify that v1.0 endpoints are NOT affected by beta-specific extended properties."""

    def test_v1_managed_devices_no_extended_fields_hardened(self, mock_server_hardened, auth_headers):
        """v1.0 managed devices do not have extended fields even in hardened."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/deviceManagement/managedDevices",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        device = data["value"][0] if data["value"] else {}

        # v1.0 should have standard fields but not beta extended fields
        if device:
            assert "id" in device
            assert "deviceName" in device
            # These should NOT be in v1.0 (beta-only)
            assert "bitLockerStatus" not in device
            assert "tpmVersion" not in device

    def test_v1_compliance_policies_no_assignments_hardened(self, mock_server_hardened, auth_headers):
        """v1.0 compliance policies do not have assignments field (beta-only)."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/deviceManagement/deviceCompliancePolicies",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()

        # v1.0 should not have beta-specific fields
        for policy in data["value"]:
            # These are standard v1.0 fields
            assert "@odata.type" in policy
            assert "displayName" in policy
            # These should NOT be in v1.0 (beta-only)
            assert "assignments" not in policy

    def test_v1_context_uses_v1_not_beta(self, mock_server_hardened, auth_headers):
        """v1.0 @odata.context contains /v1.0/ not /beta/."""
        response = httpx.get(
            f"{mock_server_hardened}/v1.0/users",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "@odata.context" in data
        assert "/v1.0/" in data["@odata.context"]
        assert "/beta/" not in data["@odata.context"]


class TestBetaPathMapping:
    """Test that beta-only paths are correctly mapped."""

    def test_beta_risk_detections_path_mapping(self, mock_server, auth_headers):
        """identityProtection/riskDetections path maps correctly."""
        response = httpx.get(
            f"{mock_server}/beta/identityProtection/riskDetections",
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_beta_attack_simulation_simulations_path(self, mock_server, auth_headers):
        """security/attackSimulation/simulations path maps correctly."""
        response = httpx.get(
            f"{mock_server}/beta/security/attackSimulation/simulations",
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_beta_device_health_scripts_path(self, mock_server, auth_headers):
        """deviceManagement/deviceHealthScripts path maps correctly."""
        response = httpx.get(
            f"{mock_server}/beta/deviceManagement/deviceHealthScripts",
            headers=auth_headers
        )
        assert response.status_code == 200

    def test_beta_security_intents_path(self, mock_server, auth_headers):
        """security/securityIntents path maps correctly."""
        response = httpx.get(
            f"{mock_server}/beta/security/securityIntents",
            headers=auth_headers
        )
        assert response.status_code == 200
