#!/usr/bin/env python3
"""
TenantBuilder: Fluent API for programmatic M365 tenant fixture generation.

Provides a fluent builder pattern to construct realistic tenant state fixtures
that match Microsoft Graph API response shapes. Includes preset builders for
greenfield and hardened scenarios.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID


class TenantBuilder:
    """Fluent builder for constructing M365 tenant fixtures.

    All .with_*() methods return self for method chaining.
    Call .build(output_dir) to write all fixture files.
    """

    def __init__(self, seed: int = 42):
        """Initialize builder with optional seed for deterministic UUID generation."""
        self._seed = seed
        self._rng = _SeededRNG(seed)

        # Tenant identity
        self._org_name = "Contoso Defense LLC"
        self._org_domain = "contoso-defense.com"
        self._org_id = UUID("00000000-0000-0000-0000-000000000001")

        # Collections
        self._users: list[dict[str, Any]] = []
        self._ca_policies: list[dict[str, Any]] = []
        self._managed_devices: list[dict[str, Any]] = []
        self._compliance_policies: list[dict[str, Any]] = []
        self._device_configurations: list[dict[str, Any]] = []
        self._auth_methods_enabled: dict[str, bool] = {
            "fido2": False,
            "microsoftAuthenticator": False,
            "temporaryAccessPass": False,
            "sms": False,
        }
        self._directory_roles: list[dict[str, Any]] = []
        self._role_assignments: list[dict[str, Any]] = []
        self._service_principals: list[dict[str, Any]] = []
        self._secure_score: dict[str, Any] = {
            "id": "00000000-0000-0000-0000-000000000001_2026-03-19",
            "createdDateTime": "2026-03-19T00:00:00Z",
            "currentScore": 12.0,
            "maxScore": 198.0,
            "licensedUserCount": 2,
            "activeUserCount": 1,
            "enabledServices": ["HasLicense_AAD_P2", "HasLicense_MCAS", "HasLicense_MDE"],
            "averageComparativeScores": [
                {"basis": "AllTenants", "averageScore": 37.42},
                {"basis": "TotalSeats", "averageScore": 35.18},
            ],
            "controlScores": [],
        }

    def with_organization(
        self,
        display_name: str = "Contoso Defense LLC",
        domain: str = "contoso-defense.com",
        org_id: Optional[str] = None,
    ) -> "TenantBuilder":
        """Set organization identity."""
        self._org_name = display_name
        self._org_domain = domain
        if org_id:
            try:
                self._org_id = UUID(org_id)
            except ValueError:
                self._org_id = UUID(org_id)
        return self

    def with_user(
        self,
        display_name: str,
        upn: str,
        user_type: str = "Member",
        account_enabled: bool = True,
        job_title: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> "TenantBuilder":
        """Add a user to the tenant."""
        if user_id is None:
            # Generate deterministic UUID based on UPN
            user_id = str(uuid.uuid5(self._org_id, upn))

        user = {
            "id": user_id,
            "displayName": display_name,
            "userPrincipalName": upn,
            "userType": user_type,
            "accountEnabled": account_enabled,
            "jobTitle": job_title,
            "assignedLicenses": (
                [{"skuId": "c7df2760-2c81-4ef7-b578-5b5392b571df"}]
                if user_type == "Member"
                else []
            ),
        }
        self._users.append(user)
        return self

    def with_ca_policy(
        self,
        display_name: str,
        state: str = "enabledForReportingButNotEnforced",
        grant_controls: Optional[dict[str, Any]] = None,
        conditions: Optional[dict[str, Any]] = None,
        policy_id: Optional[str] = None,
    ) -> "TenantBuilder":
        """Add a Conditional Access policy."""
        if policy_id is None:
            policy_id = str(self._rng.next_uuid())

        policy = {
            "id": policy_id,
            "displayName": display_name,
            "state": state,
            "conditions": conditions or {
                "applications": {"includeApplications": ["All"]},
                "users": {
                    "includeUsers": ["All"],
                    "excludeUsers": ["00000000-0000-0000-0000-000000000011"],
                },
            },
            "grantControls": grant_controls,
            "sessionControls": None,
        }
        self._ca_policies.append(policy)
        return self

    def with_device(
        self,
        display_name: str,
        os: str = "Windows",
        compliance_state: str = "compliant",
        device_type: str = "windowsPC",
        device_id: Optional[str] = None,
    ) -> "TenantBuilder":
        """Add a managed device."""
        if device_id is None:
            device_id = str(self._rng.next_uuid())

        # Map OS to actual OS version strings
        os_versions = {
            "Windows": "Windows 11 Pro",
            "iOS": "17.4.1",
            "Android": "14.0",
        }
        os_version = os_versions.get(os, "Windows 11 Pro")

        device_types_map = {
            "Windows": "windowsPC",
            "iOS": "iosPhone",
            "Android": "androidMobileDevice",
        }
        device_type = device_types_map.get(os, "windowsPC")

        device = {
            "id": device_id,
            "deviceName": display_name,
            "osVersion": os_version,
            "complianceState": compliance_state,
            "deviceType": device_type,
            "operatingSystem": os,
            "ownerType": "company",
            "enrollmentDateTime": "2024-01-10T09:15:00Z",
            "lastSyncDateTime": "2025-03-19T14:22:00Z",
            "isEncrypted": True,
            "manufacturer": "Dell",
            "model": "Test Device",
            "imei": "",
            "serialNumber": f"SN-{display_name.upper()}",
            "udid": "",
        }
        self._managed_devices.append(device)
        return self

    def with_compliance_policy(
        self,
        display_name: str,
        platform: str = "windows",
        policy_id: Optional[str] = None,
    ) -> "TenantBuilder":
        """Add a device compliance policy."""
        if policy_id is None:
            policy_id = str(self._rng.next_uuid())

        policy_templates = {
            "windows": {
                "@odata.type": "#microsoft.graph.windowsCompliancePolicy",
                "displayName": display_name,
                "description": f"CMMC 2.0 Level 2 compliance policy for {platform.capitalize()} devices",
                "createdDateTime": "2024-01-05T08:00:00Z",
                "lastModifiedDateTime": "2024-01-05T08:00:00Z",
                "passwordRequired": True,
                "passwordMinimumLength": 14,
                "passwordRequiredType": "alphanumeric",
                "passwordMinutesOfInactivityBeforeLock": 15,
                "passwordExpirationDays": 90,
                "passwordPreviousPasswordBlockCount": 24,
                "requireHealthyDeviceReport": True,
                "osMinimumVersion": "10.0.19041.0",
                "encryptionRequired": True,
                "storageRequireEncryption": True,
                "firewallRequired": True,
            },
            "ios": {
                "@odata.type": "#microsoft.graph.iosCompliancePolicy",
                "displayName": display_name,
                "description": f"CMMC 2.0 Level 2 compliance policy for {platform.capitalize()} devices",
                "createdDateTime": "2024-01-08T08:00:00Z",
                "lastModifiedDateTime": "2024-01-08T08:00:00Z",
                "passwordRequired": True,
                "passwordMinimumLength": 6,
                "passwordRequiredType": "numericComplex",
                "passwordMinutesOfInactivityBeforeLock": 15,
                "passwordExpirationDays": 365,
                "passwordPreviousPasswordBlockCount": 5,
                "osMinimumVersion": "15.1",
                "systemIntegrityProtectionEnabled": True,
                "restrictedApps": [],
                "deviceCompliancePolicyScheduledActionForRule": [],
            },
            "android": {
                "@odata.type": "#microsoft.graph.androidCompliancePolicy",
                "displayName": display_name,
                "description": f"CMMC 2.0 Level 2 compliance policy for {platform.capitalize()} devices",
                "createdDateTime": "2024-01-08T08:00:00Z",
                "lastModifiedDateTime": "2024-01-08T08:00:00Z",
                "passwordRequired": True,
                "passwordMinimumLength": 8,
                "passwordRequiredType": "alphanumeric",
                "passwordMinutesOfInactivityBeforeLock": 15,
                "passwordExpirationDays": 180,
                "passwordPreviousPasswordBlockCount": 6,
                "osMinimumVersion": "12.0",
                "storageEncryptionRequired": True,
                "securityPatchLevel": "2024-01-01",
                "googlePlayProtectEnabled": True,
            },
        }

        policy = policy_templates.get(platform.lower(), policy_templates["windows"]).copy()
        policy["id"] = policy_id
        self._compliance_policies.append(policy)
        return self

    def with_device_configuration(
        self,
        display_name: str,
        config_type: str = "windows10EndpointProtectionConfiguration",
        config_id: Optional[str] = None,
    ) -> "TenantBuilder":
        """Add a device configuration."""
        if config_id is None:
            config_id = str(self._rng.next_uuid())

        config_templates = {
            "windows10EndpointProtectionConfiguration": {
                "@odata.type": "#microsoft.graph.windows10EndpointProtectionConfiguration",
                "displayName": display_name,
                "description": "CMMC compliance configuration",
                "createdDateTime": "2024-01-06T08:00:00Z",
                "lastModifiedDateTime": "2024-01-06T08:00:00Z",
                "defenderAllowOnAccessProtection": True,
                "defenderAllowBehaviorMonitoring": True,
                "defenderAllowCloudProtection": True,
            },
            "iosDeviceConfiguration": {
                "@odata.type": "#microsoft.graph.iosDeviceConfiguration",
                "displayName": display_name,
                "description": "CMMC compliance configuration",
                "createdDateTime": "2024-01-06T08:00:00Z",
                "lastModifiedDateTime": "2024-01-06T08:00:00Z",
            },
        }

        config = config_templates.get(
            config_type, config_templates["windows10EndpointProtectionConfiguration"]
        ).copy()
        config["id"] = config_id
        self._device_configurations.append(config)
        return self

    def with_auth_method_enabled(self, method_id: str, enabled: bool = True) -> "TenantBuilder":
        """Enable or disable an authentication method."""
        valid_methods = {"fido2", "microsoftAuthenticator", "temporaryAccessPass", "sms"}
        if method_id in valid_methods:
            self._auth_methods_enabled[method_id] = enabled
        return self

    def with_directory_role(
        self,
        display_name: str,
        role_template_id: str,
        role_id: Optional[str] = None,
    ) -> "TenantBuilder":
        """Add a directory role."""
        if role_id is None:
            role_id = str(self._rng.next_uuid())

        role = {
            "id": role_id,
            "displayName": display_name,
            "roleTemplateId": role_template_id,
        }
        self._directory_roles.append(role)
        return self

    def with_role_assignment(
        self,
        principal_id: str,
        role_definition_id: str,
        assignment_id: Optional[str] = None,
    ) -> "TenantBuilder":
        """Assign a role to a principal."""
        if assignment_id is None:
            assignment_id = str(self._rng.next_uuid())

        assignment = {
            "id": assignment_id,
            "principalId": principal_id,
            "roleDefinitionId": role_definition_id,
            "directoryScopeId": "/",
        }
        self._role_assignments.append(assignment)
        return self

    def with_service_principal(
        self,
        display_name: str,
        app_id: str,
        sp_id: Optional[str] = None,
    ) -> "TenantBuilder":
        """Add a service principal."""
        if sp_id is None:
            sp_id = str(self._rng.next_uuid())

        sp = {
            "id": sp_id,
            "appId": app_id,
            "displayName": display_name,
            "servicePrincipalType": "Application",
        }
        self._service_principals.append(sp)
        return self

    def with_secure_score(
        self,
        current_score: float = 12.0,
        max_score: float = 198.0,
    ) -> "TenantBuilder":
        """Set the secure score."""
        self._secure_score["currentScore"] = current_score
        self._secure_score["maxScore"] = max_score
        return self

    def build(self, output_dir: Path) -> None:
        """Write all fixture JSON files to output directory."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write users.json
        self._write_fixture(
            output_dir,
            "users.json",
            "https://graph.microsoft.com/v1.0/$metadata#users",
            self._users,
        )

        # Write organization.json
        self._write_fixture(
            output_dir,
            "organization.json",
            "https://graph.microsoft.com/v1.0/$metadata#organization",
            [
                {
                    "id": str(self._org_id),
                    "displayName": self._org_name,
                    "tenantType": "AAD",
                    "verifiedDomains": [
                        {
                            "name": self._org_domain,
                            "isDefault": True,
                            "isInitial": False,
                            "capabilities": "Email, OfficeCommunicationsOnline",
                        },
                        {
                            "name": f"{self._org_domain.split('.')[0]}.onmicrosoft.com",
                            "isInitial": True,
                            "isDefault": False,
                            "capabilities": "Email, OfficeCommunicationsOnline",
                        },
                    ],
                    "assignedPlans": [
                        {
                            "service": "exchange",
                            "capabilityStatus": "Enabled",
                            "servicePlanId": "efb87545-963c-4e0d-99df-69c6916d9eb0",
                            "assignedTimestamp": "2026-03-01T00:00:00Z",
                        },
                        {
                            "service": "MicrosoftDefenderATP",
                            "capabilityStatus": "Enabled",
                            "servicePlanId": "871d91ec-ec1a-452b-a83f-bd76c7d770ef",
                            "assignedTimestamp": "2026-03-01T00:00:00Z",
                        },
                        {
                            "service": "SCO",
                            "capabilityStatus": "Enabled",
                            "servicePlanId": "c1ec4a95-1f05-45b3-a911-aa3fa01094f5",
                            "assignedTimestamp": "2026-03-01T00:00:00Z",
                        },
                        {
                            "service": "AADPremiumService",
                            "capabilityStatus": "Enabled",
                            "servicePlanId": "41781fb2-bc02-4b7c-bd55-b576c07bb09d",
                            "assignedTimestamp": "2026-03-01T00:00:00Z",
                        },
                    ],
                }
            ],
        )

        # Write me.json (current user)
        if self._users:
            me_user = self._users[0].copy()
            me_context = "https://graph.microsoft.com/v1.0/$metadata#users/$entity"
            with open(output_dir / "me.json", "w") as f:
                json.dump(
                    {
                        "@odata.context": me_context,
                        "id": me_user["id"],
                        "displayName": me_user["displayName"],
                        "userPrincipalName": me_user["userPrincipalName"],
                        "userType": me_user["userType"],
                    },
                    f,
                    indent=2,
                )

        # Write conditional_access_policies.json
        self._write_fixture(
            output_dir,
            "conditional_access_policies.json",
            "https://graph.microsoft.com/v1.0/$metadata#identity/conditionalAccess/policies",
            self._ca_policies,
        )

        # Write managed_devices.json
        self._write_fixture(
            output_dir,
            "managed_devices.json",
            "https://graph.microsoft.com/v1.0/$metadata#deviceManagement/managedDevices",
            self._managed_devices,
        )

        # Write compliance_policies.json
        self._write_fixture(
            output_dir,
            "compliance_policies.json",
            "https://graph.microsoft.com/v1.0/$metadata#deviceManagement/deviceCompliancePolicies",
            self._compliance_policies,
        )

        # Write device_configurations.json
        self._write_fixture(
            output_dir,
            "device_configurations.json",
            "https://graph.microsoft.com/v1.0/$metadata#deviceManagement/deviceConfigurations",
            self._device_configurations,
        )

        # Write auth_methods_policy.json
        auth_methods_config = [
            {
                "@odata.type": "#microsoft.graph.fido2AuthenticationMethodConfiguration",
                "id": "fido2",
                "state": "enabled" if self._auth_methods_enabled["fido2"] else "disabled",
            },
            {
                "@odata.type": "#microsoft.graph.microsoftAuthenticatorAuthenticationMethodConfiguration",
                "id": "microsoftAuthenticator",
                "state": "enabled" if self._auth_methods_enabled["microsoftAuthenticator"] else "disabled",
            },
            {
                "@odata.type": "#microsoft.graph.temporaryAccessPassAuthenticationMethodConfiguration",
                "id": "temporaryAccessPass",
                "state": "enabled" if self._auth_methods_enabled["temporaryAccessPass"] else "disabled",
            },
            {
                "@odata.type": "#microsoft.graph.smsAuthenticationMethodConfiguration",
                "id": "sms",
                "state": "enabled" if self._auth_methods_enabled["sms"] else "disabled",
            },
        ]
        with open(output_dir / "auth_methods_policy.json", "w") as f:
            json.dump(
                {
                    "@odata.context": "https://graph.microsoft.com/v1.0/$metadata#policies/authenticationMethodsPolicy",
                    "id": "authenticationMethodsPolicy",
                    "policyVersion": "1.5",
                    "authenticationMethodConfigurations": auth_methods_config,
                },
                f,
                indent=2,
            )

        # Write directory_roles.json
        self._write_fixture(
            output_dir,
            "directory_roles.json",
            "https://graph.microsoft.com/v1.0/$metadata#directoryRoles",
            self._directory_roles,
        )

        # Write role_assignments.json
        self._write_fixture(
            output_dir,
            "role_assignments.json",
            "https://graph.microsoft.com/v1.0/$metadata#roleManagement/directory/roleAssignments",
            self._role_assignments,
        )

        # Write service_principals.json
        self._write_fixture(
            output_dir,
            "service_principals.json",
            "https://graph.microsoft.com/v1.0/$metadata#servicePrincipals",
            self._service_principals,
        )

        # Write secure_scores.json
        self._write_fixture(
            output_dir,
            "secure_scores.json",
            "https://graph.microsoft.com/v1.0/$metadata#security/secureScores",
            [self._secure_score],
        )

        # Write empty/minimal fixtures
        self._write_fixture(
            output_dir,
            "me_auth_methods.json",
            "https://graph.microsoft.com/v1.0/$metadata#users('operator-id')/authentication/methods",
            [
                {
                    "@odata.type": "#microsoft.graph.microsoftAuthenticatorAuthenticationMethod",
                    "id": "00000000-0000-0000-0000-000000000020",
                    "displayName": "Mike's iPhone",
                    "deviceTag": "SoftwareTokenActivated",
                    "phoneAppVersion": "6.2208.7949",
                },
                {
                    "@odata.type": "#microsoft.graph.passwordAuthenticationMethod",
                    "id": "00000000-0000-0000-0000-000000000021",
                },
            ],
        )

        self._write_fixture(
            output_dir, "devices.json", "https://graph.microsoft.com/v1.0/$metadata#devices", []
        )
        self._write_fixture(
            output_dir,
            "audit_sign_ins.json",
            "https://graph.microsoft.com/v1.0/$metadata#auditLogs/signIns",
            [
                {
                    "id": "signin-001",
                    "createdDateTime": "2026-03-19T00:00:00Z",
                    "userDisplayName": "Mike Morris",
                    "userPrincipalName": "mike@contoso-defense.com",
                    "userId": "00000000-0000-0000-0000-000000000010",
                    "appId": "de8bc8b5-d9f9-48b1-a8ad-b748da725064",
                    "appDisplayName": "Microsoft Azure Portal",
                    "ipAddress": "192.0.2.1",
                    "clientAppUsed": "Browser",
                    "conditionalAccessStatus": "notApplied",
                    "isInteractive": True,
                    "status": {"errorCode": 0, "failureReason": None},
                }
            ],
        )
        self._write_fixture(
            output_dir,
            "audit_directory.json",
            "https://graph.microsoft.com/v1.0/$metadata#auditLogs/directoryAudits",
            [],
        )
        self._write_fixture(
            output_dir,
            "security_incidents.json",
            "https://graph.microsoft.com/v1.0/$metadata#security/incidents",
            [],
        )
        self._write_fixture(
            output_dir,
            "security_alerts.json",
            "https://graph.microsoft.com/v1.0/$metadata#security/alerts_v2",
            [],
        )
        self._write_fixture(
            output_dir,
            "information_protection_labels.json",
            "https://graph.microsoft.com/v1.0/$metadata#informationProtection/policy/labels",
            [],
        )
        self._write_fixture(
            output_dir,
            "groups.json",
            "https://graph.microsoft.com/v1.0/$metadata#groups",
            [],
        )
        self._write_fixture(
            output_dir,
            "applications.json",
            "https://graph.microsoft.com/v1.0/$metadata#applications",
            [],
        )
        self._write_fixture(
            output_dir,
            "domains.json",
            "https://graph.microsoft.com/v1.0/$metadata#domains",
            [
                {
                    "id": self._org_domain,
                    "authenticationType": "Managed",
                    "availabilityStatus": "Available",
                    "isAdminManaged": True,
                    "isDefault": True,
                    "isInitial": False,
                    "isVerified": True,
                },
                {
                    "id": f"{self._org_domain.split('.')[0]}.onmicrosoft.com",
                    "authenticationType": "Managed",
                    "availabilityStatus": "Available",
                    "isAdminManaged": True,
                    "isDefault": False,
                    "isInitial": True,
                    "isVerified": True,
                },
            ],
        )
        self._write_fixture(
            output_dir,
            "named_locations.json",
            "https://graph.microsoft.com/v1.0/$metadata#identity/conditionalAccess/namedLocations",
            [],
        )
        self._write_fixture(
            output_dir,
            "role_definitions.json",
            "https://graph.microsoft.com/v1.0/$metadata#roleManagement/directory/roleDefinitions",
            [],
        )
        self._write_fixture(
            output_dir,
            "role_eligibility_schedules.json",
            "https://graph.microsoft.com/v1.0/$metadata#roleManagement/directory/roleEligibilitySchedules",
            [],
        )
        self._write_fixture(
            output_dir,
            "role_assignment_schedules.json",
            "https://graph.microsoft.com/v1.0/$metadata#roleManagement/directory/roleAssignmentSchedules",
            [],
        )
        self._write_fixture(
            output_dir,
            "secure_score_control_profiles.json",
            "https://graph.microsoft.com/v1.0/$metadata#security/secureScoreControlProfiles",
            [],
        )
        self._write_fixture(
            output_dir,
            "device_enrollment_configurations.json",
            "https://graph.microsoft.com/v1.0/$metadata#deviceManagement/deviceEnrollmentConfigurations",
            [],
        )

    def _write_fixture(
        self, output_dir: Path, filename: str, context: str, value: list[Any]
    ) -> None:
        """Write a fixture file with @odata.context."""
        fixture = {"@odata.context": context, "value": value}
        with open(output_dir / filename, "w") as f:
            json.dump(fixture, f, indent=2)

    @classmethod
    def greenfield_gcc_moderate(cls) -> "TenantBuilder":
        """Create a builder pre-configured with greenfield GCC Moderate state."""
        builder = cls()

        # Add greenfield users
        builder.with_user(
            "Mike Morris",
            "mike@contoso-defense.com",
            user_type="Member",
            job_title="Global Administrator",
            user_id="00000000-0000-0000-0000-000000000010",
        ).with_user(
            "BreakGlass Admin",
            "breakglass@contoso-defense.com",
            user_type="Member",
            user_id="00000000-0000-0000-0000-000000000011",
        )

        # Add directory roles
        builder.with_directory_role(
            "Global Administrator",
            "62e90394-69f5-4237-9190-012177145e10",
            role_id="role-001",
        ).with_directory_role(
            "Security Administrator",
            "194ae4cb-b126-40b2-bd5b-6091b380977d",
            role_id="role-002",
        ).with_directory_role(
            "Compliance Administrator",
            "17315797-102d-40b4-93e0-432062caca18",
            role_id="role-003",
        ).with_directory_role(
            "Global Reader",
            "f2ef992c-3afb-46b9-b7cf-a126ee74c451",
            role_id="role-004",
        ).with_directory_role(
            "User Administrator",
            "fe930be7-5e63-47ad-bce1-b432255ab137",
            role_id="role-005",
        ).with_directory_role(
            "Exchange Administrator",
            "29232cdf-9323-42fd-ade2-1d097af3e4de",
            role_id="role-006",
        ).with_directory_role(
            "SharePoint Administrator",
            "f28a1f50-f6e7-4571-818b-6a12f2af6b6c",
            role_id="role-007",
        ).with_directory_role(
            "Teams Administrator",
            "69029506-85c7-4619-8921-ddb246393064",
            role_id="role-008",
        ).with_directory_role(
            "Intune Administrator",
            "3a2c62db-5318-420d-8798-34c7694d4793",
            role_id="role-009",
        ).with_directory_role(
            "Cloud Application Administrator",
            "158c047a-c907-4556-b7ef-446551a6b5f7",
            role_id="role-010",
        ).with_directory_role(
            "Privileged Role Administrator",
            "e8611ab8-c189-46e8-94e1-60213ab1f814",
            role_id="role-011",
        ).with_directory_role(
            "Conditional Access Administrator",
            "b1be1c3e-b65d-4f19-8427-f6fa0d97feb9",
            role_id="role-012",
        ).with_directory_role(
            "Security Reader",
            "5d6b6bb7-de71-4623-b4af-eb8670a8e87b",
            role_id="role-013",
        ).with_directory_role(
            "Helpdesk Administrator",
            "729827e3-9c14-49f7-bb1b-9cd0d9d2e564",
            role_id="role-014",
        )

        # Add role assignments
        builder.with_role_assignment(
            "00000000-0000-0000-0000-000000000010",
            "62e90394-69f5-4237-9190-012177145e10",
            assignment_id="assignment-001",
        )

        # Add service principals
        builder.with_service_principal(
            "Microsoft Graph",
            "00000003-0000-0000-c000-000000000000",
            sp_id="sp-001",
        ).with_service_principal(
            "Office 365 Exchange Online",
            "00000002-0000-0ff1-ce00-000000000000",
            sp_id="sp-002",
        ).with_service_principal(
            "Microsoft SharePoint Online",
            "00000003-0000-0fff-c000-000000000000",
            sp_id="sp-003",
        ).with_service_principal(
            "Microsoft Teams",
            "cc15fd57-2c6c-4117-a88c-83b1d56b4bbe",
            sp_id="sp-004",
        ).with_service_principal(
            "Windows Azure Active Directory",
            "00000003-0000-0000-0000-000000000000",
            sp_id="sp-005",
        ).with_service_principal(
            "Microsoft Intune API",
            "9bc3ab49-b65d-410a-85ad-de31c8849e32",
            sp_id="sp-006",
        ).with_service_principal(
            "Microsoft Defender",
            "0365951c-f08f-497d-be1f-578f81470b69",
            sp_id="sp-007",
        ).with_service_principal(
            "Graph Explorer",
            "7f33c9f7-1d34-4350-9afb-2ea859a1a7bd",
            sp_id="sp-008",
        ).with_service_principal(
            "Azure Portal",
            "797f4846-ba00-4fd7-ba43-dac1f8f63013",
            sp_id="sp-009",
        )

        # Greenfield: no CA policies, no managed devices, auth methods disabled
        builder.with_secure_score(12.0, 198.0)

        return builder

    @classmethod
    def hardened_gcc_moderate(cls) -> "TenantBuilder":
        """Create a builder pre-configured with hardened GCC Moderate state."""
        # Start with greenfield and add hardened configurations
        builder = cls.greenfield_gcc_moderate()

        # Add CA policies (all in enabledForReportingButNotEnforced)
        builder.with_ca_policy(
            "CMMC-MFA-AllUsers",
            state="enabledForReportingButNotEnforced",
            grant_controls={
                "operator": "AND",
                "builtInControls": ["mfa"],
            },
            policy_id="00000000-0000-0000-0000-000000000101",
        ).with_ca_policy(
            "CMMC-MFA-Admins",
            state="enabledForReportingButNotEnforced",
            grant_controls={
                "operator": "AND",
                "builtInControls": ["mfa"],
                "customAuthenticationFactors": ["RequirePhishingResistantMFA"],
            },
            conditions={
                "applications": {"includeApplications": ["All"]},
                "users": {
                    "includeRoles": [
                        "62e90394-69f5-4237-9190-012177145e10",
                        "194ae4cb-b126-40b2-bd5b-6091b380977d",
                    ],
                    "excludeUsers": ["00000000-0000-0000-0000-000000000011"],
                },
            },
            policy_id="00000000-0000-0000-0000-000000000102",
        ).with_ca_policy(
            "CMMC-Block-Legacy-Auth",
            state="enabledForReportingButNotEnforced",
            grant_controls={"operator": "OR", "builtInControls": ["block"]},
            conditions={
                "applications": {"includeApplications": ["All"]},
                "users": {
                    "includeUsers": ["All"],
                    "excludeUsers": ["00000000-0000-0000-0000-000000000011"],
                },
                "clientAppTypes": ["exchangeActiveSync", "other"],
            },
            policy_id="00000000-0000-0000-0000-000000000103",
        ).with_ca_policy(
            "CMMC-Compliant-Device",
            state="enabledForReportingButNotEnforced",
            grant_controls={
                "operator": "OR",
                "builtInControls": ["compliantDevice", "domainJoinedDevice"],
            },
            conditions={
                "applications": {"includeApplications": ["All"]},
                "users": {
                    "includeUsers": ["All"],
                    "excludeUsers": ["00000000-0000-0000-0000-000000000011"],
                },
                "platforms": {
                    "includePlatforms": ["android", "iOS", "windows"],
                },
            },
            policy_id="00000000-0000-0000-0000-000000000104",
        ).with_ca_policy(
            "CMMC-Approved-Apps",
            state="enabledForReportingButNotEnforced",
            grant_controls={
                "operator": "AND",
                "builtInControls": ["approvedClientsAppRequired"],
            },
            conditions={
                "applications": {"includeApplications": ["Office365"]},
                "users": {
                    "includeUsers": ["All"],
                    "excludeUsers": ["00000000-0000-0000-0000-000000000011"],
                },
            },
            policy_id="00000000-0000-0000-0000-000000000105",
        ).with_ca_policy(
            "CMMC-Session-Timeout",
            state="enabledForReportingButNotEnforced",
            grant_controls=None,
            conditions={
                "applications": {"includeApplications": ["All"]},
                "users": {
                    "includeUsers": ["All"],
                    "excludeUsers": ["00000000-0000-0000-0000-000000000011"],
                },
            },
            policy_id="00000000-0000-0000-0000-000000000106",
        ).with_ca_policy(
            "CMMC-Risk-Based-Access",
            state="enabledForReportingButNotEnforced",
            grant_controls={
                "operator": "AND",
                "builtInControls": ["mfa"],
            },
            conditions={
                "applications": {"includeApplications": ["All"]},
                "users": {
                    "includeUsers": ["All"],
                    "excludeUsers": ["00000000-0000-0000-0000-000000000011"],
                },
                "signInRiskLevels": ["high", "medium"],
            },
            policy_id="00000000-0000-0000-0000-000000000107",
        ).with_ca_policy(
            "CMMC-Location-Based",
            state="enabledForReportingButNotEnforced",
            grant_controls=None,
            conditions={
                "applications": {"includeApplications": ["All"]},
                "users": {
                    "includeUsers": ["All"],
                    "excludeUsers": ["00000000-0000-0000-0000-000000000011"],
                },
                "locations": {
                    "includeLocations": ["00000000-0000-0000-0000-000000000201"],
                },
            },
            policy_id="00000000-0000-0000-0000-000000000108",
        )

        # Add managed devices
        builder.with_device(
            "CONTOSO-LT001",
            os="Windows",
            compliance_state="compliant",
            device_id="00000000-0000-0000-0000-000000000301",
        ).with_device(
            "CONTOSO-WS001",
            os="Windows",
            compliance_state="compliant",
            device_id="00000000-0000-0000-0000-000000000302",
        ).with_device(
            "CONTOSO-iPhone",
            os="iOS",
            compliance_state="compliant",
            device_id="00000000-0000-0000-0000-000000000303",
        )

        # Add compliance policies
        builder.with_compliance_policy(
            "CMMC-Windows-Compliance",
            platform="windows",
            policy_id="00000000-0000-0000-0000-000000000401",
        ).with_compliance_policy(
            "CMMC-iOS-Compliance",
            platform="ios",
            policy_id="00000000-0000-0000-0000-000000000402",
        ).with_compliance_policy(
            "CMMC-Android-Compliance",
            platform="android",
            policy_id="00000000-0000-0000-0000-000000000403",
        )

        # Add device configurations
        builder.with_device_configuration(
            "CMMC-ASR-Rules",
            config_type="windows10EndpointProtectionConfiguration",
            config_id="00000000-0000-0000-0000-000000000501",
        ).with_device_configuration(
            "CMMC-Defender-AV",
            config_type="windows10EndpointProtectionConfiguration",
            config_id="00000000-0000-0000-0000-000000000502",
        )

        # Enable auth methods
        builder.with_auth_method_enabled("microsoftAuthenticator", True).with_auth_method_enabled(
            "temporaryAccessPass", True
        ).with_auth_method_enabled("fido2", True)

        return builder


class _SeededRNG:
    """Deterministic UUID generator seeded with an integer."""

    def __init__(self, seed: int):
        self._seed = seed
        self._counter = 0

    def next_uuid(self) -> UUID:
        """Generate next deterministic UUID."""
        self._counter += 1
        # Create a hash-like sequence from seed and counter
        hash_input = f"{self._seed:032d}{self._counter:032d}"
        # Use UUID5 with a fixed namespace to generate deterministic UUIDs
        return uuid.uuid5(
            uuid.UUID("00000000-0000-0000-0000-000000000000"),
            hash_input,
        )
