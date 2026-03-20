#!/usr/bin/env python3
"""
OSCAL Component Definition Generator for m365-sim.

Generates NIST OSCAL 1.1.2 Component Definition JSON that maps m365-sim
Graph API endpoints to CMMC L2 / NIST 800-171 Rev 2 controls.
"""

import argparse
import json
from datetime import datetime, timezone
from uuid import uuid5, NAMESPACE_DNS


# Fixed namespace UUID for deterministic control UUIDs
COMPONENT_NAMESPACE = uuid5(NAMESPACE_DNS, "m365-sim.example.com")


def generate_component_uuid() -> str:
    """Generate deterministic component UUID."""
    return str(uuid5(COMPONENT_NAMESPACE, "m365-sim-component"))


def generate_control_implementation_uuid() -> str:
    """Generate deterministic control implementation UUID."""
    return str(uuid5(COMPONENT_NAMESPACE, "m365-sim-control-implementation"))


def generate_requirement_uuid(control_id: str) -> str:
    """Generate deterministic UUID for a requirement based on control ID."""
    return str(uuid5(COMPONENT_NAMESPACE, f"requirement-{control_id}"))


def build_implemented_requirements() -> list:
    """Build implemented-requirements mapping Graph API endpoints to CMMC L2 controls."""
    requirements = [{"uuid": "5d6c0761-17ff-5646-bd9b-ec7c83183f0a", "control-id": "ac.l2-3.1.1", "description": "Limit system access to authorized users, processes acting on behalf of authorized users, and devices (and other physical objects) \u2014 evidence from /v1.0/users endpoint enumeration of authorized users", "props": [{"name": "graph-endpoint", "value": "/v1.0/users"}, {"name": "fixture-file", "value": "users.json"}, {"name": "assessment-method", "value": "automated"}]}, {"uuid": "c5980e38-45ce-5db1-9e0c-c395837aa4b5", "control-id": "ac.l2-3.1.2", "description": "Employ the principle of least privilege, including for remote access and privileged direct access \u2014 evidence from /v1.0/directoryRoles and /v1.0/roleManagement/directory/roleAssignments for role-based access verification", "props": [{"name": "graph-endpoint", "value": "/v1.0/directoryRoles"}, {"name": "graph-endpoint", "value": "/v1.0/roleManagement/directory/roleAssignments"}, {"name": "fixture-file", "value": "directory_roles.json"}, {"name": "fixture-file", "value": "role_assignments.json"}, {"name": "assessment-method", "value": "automated"}]}, {"uuid": "619d5184-2d37-5b1e-9a39-e6a5b65bcd4b", "control-id": "ac.l2-3.1.3", "description": "Prevent non-privileged users from executing privileged functions \u2014 evidence from /v1.0/identity/conditionalAccess/policies for access control enforcement", "props": [{"name": "graph-endpoint", "value": "/v1.0/identity/conditionalAccess/policies"}, {"name": "fixture-file", "value": "conditional_access_policies.json"}, {"name": "assessment-method", "value": "automated"}]}, {"uuid": "d89aa63f-80cc-5740-9021-100f7aad8af0", "control-id": "ia.l2-3.5.3", "description": "Employ multi-factor authentication for local and network access \u2014 evidence from /v1.0/policies/authenticationMethodsPolicy and /v1.0/me/authentication/methods for authentication configuration verification", "props": [{"name": "graph-endpoint", "value": "/v1.0/policies/authenticationMethodsPolicy"}, {"name": "graph-endpoint", "value": "/v1.0/me/authentication/methods"}, {"name": "fixture-file", "value": "auth_methods_policy.json"}, {"name": "fixture-file", "value": "me_auth_methods.json"}, {"name": "assessment-method", "value": "automated"}]}, {"uuid": "e17eb7a3-f647-5aa2-b441-5e65c63c3f1b", "control-id": "mp.l2-3.8.1", "description": "Prevent unauthorized information disclosure and removal \u2014 evidence from /v1.0/deviceManagement/managedDevices and /v1.0/deviceManagement/deviceCompliancePolicies for device management policy enforcement", "props": [{"name": "graph-endpoint", "value": "/v1.0/deviceManagement/managedDevices"}, {"name": "graph-endpoint", "value": "/v1.0/deviceManagement/deviceCompliancePolicies"}, {"name": "fixture-file", "value": "managed_devices.json"}, {"name": "fixture-file", "value": "compliance_policies.json"}, {"name": "assessment-method", "value": "automated"}]}, {"uuid": "95350b1e-3886-5c66-b048-ac5c7f68061e", "control-id": "mp.l2-3.8.2", "description": "Address data sensitivity through labeling and handling restrictions \u2014 evidence from /v1.0/informationProtection/policy/labels for information protection classification", "props": [{"name": "graph-endpoint", "value": "/v1.0/informationProtection/policy/labels"}, {"name": "fixture-file", "value": "information_protection_labels.json"}, {"name": "assessment-method", "value": "automated"}]}, {"uuid": "4fbf1f52-b533-537a-a5d1-10d6e40fa39a", "control-id": "cm.l2-3.4.1", "description": "Establish and maintain baseline configurations and inventories \u2014 evidence from /v1.0/deviceManagement/deviceConfigurations for configuration baseline verification", "props": [{"name": "graph-endpoint", "value": "/v1.0/deviceManagement/deviceConfigurations"}, {"name": "fixture-file", "value": "device_configurations.json"}, {"name": "assessment-method", "value": "automated"}]}, {"uuid": "ec9b10bb-a035-588a-8292-4162b27f5a4e", "control-id": "sc.l2-3.13.1", "description": "Establish secure communication channels \u2014 evidence from /v1.0/security/secureScores for security posture assessment", "props": [{"name": "graph-endpoint", "value": "/v1.0/security/secureScores"}, {"name": "fixture-file", "value": "secure_scores.json"}, {"name": "assessment-method", "value": "automated"}]}, {"uuid": "052a8f23-9e4c-5ae7-a7a7-10ebad1df620", "control-id": "au.l2-3.3.1", "description": "Create, protect, and retain system audit logs \u2014 evidence from /v1.0/auditLogs/signIns for sign-in audit trail", "props": [{"name": "graph-endpoint", "value": "/v1.0/auditLogs/signIns"}, {"name": "fixture-file", "value": "audit_sign_ins.json"}, {"name": "assessment-method", "value": "automated"}]}, {"uuid": "372d489a-30a8-5dc4-a700-7fdcba4ecc54", "control-id": "au.l2-3.3.2", "description": "Audit and review system events for effectiveness of safeguards \u2014 evidence from /v1.0/auditLogs/directoryAudits for directory activity audit trail", "props": [{"name": "graph-endpoint", "value": "/v1.0/auditLogs/directoryAudits"}, {"name": "fixture-file", "value": "audit_directory.json"}, {"name": "assessment-method", "value": "automated"}]}, {"uuid": "f8310a2f-27e2-5fec-bdf6-ac9e091d29db", "control-id": "ac.l2-3.1.4", "description": "Use session lockout to protect against unauthorized access \u2014 evidence from /v1.0/me endpoint for current user context", "props": [{"name": "graph-endpoint", "value": "/v1.0/me"}, {"name": "fixture-file", "value": "me.json"}, {"name": "assessment-method", "value": "automated"}]}, {"uuid": "b494539f-336e-5948-8adc-e0b76ea09b94", "control-id": "ia.l2-3.5.1", "description": "Enforce authentication of organizational users, non-organizational users, and processes \u2014 evidence from /v1.0/users endpoint authentication status verification", "props": [{"name": "graph-endpoint", "value": "/v1.0/users"}, {"name": "fixture-file", "value": "users.json"}, {"name": "assessment-method", "value": "automated"}]}]
    return requirements


def build_component_definition() -> dict:
    """Build NIST OSCAL 1.1.2 Component Definition for m365-sim."""
    now = datetime.now(timezone.utc).isoformat()

    component_def = {
        "component-definition": {
            "uuid": generate_component_uuid(),
            "metadata": {
                "title": "m365-sim Graph API Simulation Platform",
                "last-modified": now,
                "version": "1.0.0",
                "oscal-version": "1.1.2"
            },
            "components": [
                {
                    "uuid": generate_component_uuid(),
                    "type": "software",
                    "title": "m365-sim",
                    "description": "Microsoft Graph API simulation platform for CMMC 2.0 L2 compliance testing",
                    "control-implementations": [
                        {
                            "uuid": generate_control_implementation_uuid(),
                            "source": "https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-171/rev2/json/NIST_SP-800-171_rev2_catalog.json",
                            "description": "NIST SP 800-171 Rev 2 control implementations via Microsoft Graph API",
                            "implemented-requirements": build_implemented_requirements()
                        }
                    ]
                }
            ]
        }
    }

    return component_def


def main():
    """Generate OSCAL component definition and write to output file."""
    parser = argparse.ArgumentParser(
        description="Generate OSCAL Component Definition for m365-sim"
    )
    parser.add_argument(
        "--output",
        default="oscal/component-definition.json",
        help="Output path for generated component definition (default: oscal/component-definition.json)"
    )

    args = parser.parse_args()

    component_def = build_component_definition()

    with open(args.output, "w") as f:
        json.dump(component_def, f, indent=2)

    print(f"Generated OSCAL component definition: {args.output}")


if __name__ == "__main__":
    main()
