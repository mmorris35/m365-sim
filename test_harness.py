#!/usr/bin/env python3
"""
m365-sim Test Harness — Graph API Client Simulator

Simulates a CMMC compliance assessment tool making real Microsoft Graph API
calls against the mock server. Tests three workflows:

1. ASSESS greenfield — fresh tenant, expect bad posture
2. ASSESS hardened   — post-remediation, expect good posture
3. DEPLOY            — write operations (POST CA policies, PATCH auth methods)

Usage:
    python test_harness.py                    # run all workflows
    python test_harness.py --workflow assess   # assess both scenarios
    python test_harness.py --workflow deploy   # deploy operations only
    python test_harness.py --port 9999        # custom port
"""

import argparse
import json
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class Finding:
    control: str
    description: str
    status: str  # "PASS", "FAIL", "NOT_ASSESSED"
    detail: str = ""


@dataclass
class AssessmentResult:
    scenario: str
    findings: list[Finding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def pass_count(self) -> int:
        return sum(1 for f in self.findings if f.status == "PASS")

    @property
    def fail_count(self) -> int:
        return sum(1 for f in self.findings if f.status == "FAIL")


def get_free_port() -> int:
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def start_server(port: int, scenario: str = "greenfield", stateful: bool = False) -> subprocess.Popen:
    cmd = [sys.executable, "server.py", "--port", str(port), "--scenario", scenario]
    if stateful:
        cmd.append("--stateful")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://localhost:{port}/health", timeout=1)
            if r.status_code == 200:
                return proc
        except httpx.ConnectError:
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError(f"Server failed to start on port {port}")


def stop_server(proc: subprocess.Popen):
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ---------------------------------------------------------------------------
# Graph API client helpers — mirrors what a real compliance tool would call
# ---------------------------------------------------------------------------

class GraphClient:
    """Minimal Microsoft Graph API client for assessment."""

    def __init__(self, base_url: str, token: str = "assessment-token"):
        self.base = base_url
        self.headers = {"Authorization": f"Bearer {token}"}

    def get(self, path: str, params: dict | None = None) -> httpx.Response:
        return httpx.get(f"{self.base}{path}", headers=self.headers, params=params)

    def post(self, path: str, body: dict) -> httpx.Response:
        return httpx.post(f"{self.base}{path}", headers=self.headers, json=body)

    def patch(self, path: str, body: dict) -> httpx.Response:
        return httpx.patch(f"{self.base}{path}", headers=self.headers, json=body)

    # Convenience methods matching real Graph SDK patterns
    def get_users(self) -> list[dict]:
        return self.get("/v1.0/users").json().get("value", [])

    def get_me(self) -> dict:
        return self.get("/v1.0/me").json()

    def get_organization(self) -> list[dict]:
        return self.get("/v1.0/organization").json().get("value", [])

    def get_ca_policies(self) -> list[dict]:
        return self.get("/v1.0/identity/conditionalAccess/policies").json().get("value", [])

    def get_auth_methods_policy(self) -> dict:
        return self.get("/v1.0/policies/authenticationMethodsPolicy").json()

    def get_auth_method_config(self, method_id: str) -> dict:
        return self.get(f"/v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id}").json()

    def get_me_auth_methods(self) -> list[dict]:
        return self.get("/v1.0/me/authentication/methods").json().get("value", [])

    def get_directory_roles(self) -> list[dict]:
        return self.get("/v1.0/directoryRoles").json().get("value", [])

    def get_role_assignments(self) -> list[dict]:
        return self.get("/v1.0/roleManagement/directory/roleAssignments").json().get("value", [])

    def get_managed_devices(self) -> list[dict]:
        return self.get("/v1.0/deviceManagement/managedDevices").json().get("value", [])

    def get_compliance_policies(self) -> list[dict]:
        return self.get("/v1.0/deviceManagement/deviceCompliancePolicies").json().get("value", [])

    def get_secure_scores(self) -> list[dict]:
        return self.get("/v1.0/security/secureScores").json().get("value", [])

    def get_service_principals(self) -> list[dict]:
        return self.get("/v1.0/servicePrincipals").json().get("value", [])

    def get_domains(self) -> list[dict]:
        return self.get("/v1.0/domains").json().get("value", [])

    def get_groups(self) -> list[dict]:
        return self.get("/v1.0/groups").json().get("value", [])

    def get_named_locations(self) -> list[dict]:
        return self.get("/v1.0/identity/conditionalAccess/namedLocations").json().get("value", [])

    def get_info_protection_labels(self) -> list[dict]:
        return self.get("/v1.0/informationProtection/policy/labels").json().get("value", [])


# ---------------------------------------------------------------------------
# CMMC Assessment Logic — evaluates tenant posture like a real tool
# ---------------------------------------------------------------------------

BREAKGLASS_ID = "00000000-0000-0000-0000-000000000011"


def assess_tenant(client: GraphClient, scenario: str) -> AssessmentResult:
    """Run a CMMC L2 assessment against the tenant."""
    result = AssessmentResult(scenario=scenario)

    # --- AC.L2-3.1.1: Limit system access to authorized users ---
    try:
        users = client.get_users()
        guest_users = [u for u in users if u.get("userType") == "Guest"]
        if len(guest_users) == 0:
            result.findings.append(Finding("AC.L2-3.1.1", "No guest accounts present", "PASS",
                                           f"{len(users)} users, 0 guests"))
        else:
            result.findings.append(Finding("AC.L2-3.1.1", "Guest accounts found", "FAIL",
                                           f"{len(guest_users)} guest accounts"))
    except Exception as e:
        result.errors.append(f"AC.L2-3.1.1: {e}")

    # --- AC.L2-3.1.3: Control CUI flow (Conditional Access) ---
    try:
        policies = client.get_ca_policies()
        active_policies = [p for p in policies if p.get("state") != "disabled"]
        if len(active_policies) >= 5:
            result.findings.append(Finding("AC.L2-3.1.3", "Adequate CA policies deployed", "PASS",
                                           f"{len(active_policies)} active policies"))
        elif len(active_policies) > 0:
            result.findings.append(Finding("AC.L2-3.1.3", "Some CA policies but insufficient", "FAIL",
                                           f"Only {len(active_policies)} active policies (need >= 5)"))
        else:
            result.findings.append(Finding("AC.L2-3.1.3", "No CA policies deployed", "FAIL",
                                           "0 active policies"))
    except Exception as e:
        result.errors.append(f"AC.L2-3.1.3: {e}")

    # --- AC.L2-3.1.3: CA policies exclude break-glass ---
    try:
        policies = client.get_ca_policies()
        if policies:
            missing_exclusion = []
            for p in policies:
                excluded = (p.get("conditions") or {}).get("users", {}).get("excludeUsers", [])
                if BREAKGLASS_ID not in excluded:
                    missing_exclusion.append(p.get("displayName"))
            if not missing_exclusion:
                result.findings.append(Finding("AC.L2-3.1.3.BG", "Break-glass excluded from all CA policies", "PASS",
                                               f"All {len(policies)} policies exclude {BREAKGLASS_ID}"))
            else:
                result.findings.append(Finding("AC.L2-3.1.3.BG", "Break-glass NOT excluded from some policies", "FAIL",
                                               f"Missing: {missing_exclusion}"))
        else:
            result.findings.append(Finding("AC.L2-3.1.3.BG", "No CA policies to evaluate", "NOT_ASSESSED"))
    except Exception as e:
        result.errors.append(f"AC.L2-3.1.3.BG: {e}")

    # --- AC.L2-3.1.3: Block legacy auth ---
    try:
        policies = client.get_ca_policies()
        legacy_block = [p for p in policies if "legacy" in p.get("displayName", "").lower()]
        if legacy_block:
            result.findings.append(Finding("AC.L2-3.1.3.LA", "Legacy auth blocking policy exists", "PASS",
                                           f"Policy: {legacy_block[0].get('displayName')}"))
        else:
            result.findings.append(Finding("AC.L2-3.1.3.LA", "No legacy auth blocking policy", "FAIL"))
    except Exception as e:
        result.errors.append(f"AC.L2-3.1.3.LA: {e}")

    # --- IA.L2-3.5.3: MFA for all users ---
    try:
        policies = client.get_ca_policies()
        mfa_policies = [p for p in policies
                        if "mfa" in p.get("displayName", "").lower()
                        and p.get("state") != "disabled"]
        if mfa_policies:
            result.findings.append(Finding("IA.L2-3.5.3", "MFA policy deployed", "PASS",
                                           f"{len(mfa_policies)} MFA policies active"))
        else:
            result.findings.append(Finding("IA.L2-3.5.3", "No MFA policy deployed", "FAIL"))
    except Exception as e:
        result.errors.append(f"IA.L2-3.5.3: {e}")

    # --- IA.L2-3.5.3: Phishing-resistant MFA (FIDO2) ---
    try:
        auth_methods = client.get_me_auth_methods()
        fido2 = [m for m in auth_methods if "fido2" in m.get("@odata.type", "").lower()]
        if fido2:
            result.findings.append(Finding("IA.L2-3.5.3.PR", "Phishing-resistant MFA (FIDO2) registered", "PASS",
                                           f"{len(fido2)} FIDO2 key(s)"))
        else:
            result.findings.append(Finding("IA.L2-3.5.3.PR", "No phishing-resistant MFA registered", "FAIL",
                                           f"Auth methods: {[m.get('@odata.type','?').split('.')[-1] for m in auth_methods]}"))
    except Exception as e:
        result.errors.append(f"IA.L2-3.5.3.PR: {e}")

    # --- IA.L2-3.5.3: Auth methods policy ---
    try:
        policy = client.get_auth_methods_policy()
        configs = policy.get("authenticationMethodConfigurations", [])
        enabled = [c for c in configs if c.get("state") == "enabled"]
        strong_methods = {"fido2", "microsoftAuthenticator"}
        enabled_strong = [c for c in enabled if c.get("id") in strong_methods]
        if len(enabled_strong) >= 2:
            result.findings.append(Finding("IA.L2-3.5.3.AM", "Strong auth methods enabled", "PASS",
                                           f"Enabled: {[c['id'] for c in enabled]}"))
        elif len(enabled_strong) == 1:
            result.findings.append(Finding("IA.L2-3.5.3.AM", "Only one strong auth method enabled", "FAIL",
                                           f"Enabled: {[c['id'] for c in enabled]}"))
        else:
            result.findings.append(Finding("IA.L2-3.5.3.AM", "No strong auth methods enabled", "FAIL",
                                           f"All methods disabled or weak-only"))
    except Exception as e:
        result.errors.append(f"IA.L2-3.5.3.AM: {e}")

    # --- MP.L2-3.8.1: Managed devices ---
    try:
        devices = client.get_managed_devices()
        compliant = [d for d in devices if d.get("complianceState") == "compliant"]
        if devices and len(compliant) == len(devices):
            result.findings.append(Finding("MP.L2-3.8.1", "All devices compliant", "PASS",
                                           f"{len(compliant)}/{len(devices)} compliant"))
        elif devices:
            result.findings.append(Finding("MP.L2-3.8.1", "Non-compliant devices found", "FAIL",
                                           f"{len(compliant)}/{len(devices)} compliant"))
        else:
            result.findings.append(Finding("MP.L2-3.8.1", "No managed devices enrolled", "FAIL",
                                           "0 devices in Intune"))
    except Exception as e:
        result.errors.append(f"MP.L2-3.8.1: {e}")

    # --- MP.L2-3.8.1: Compliance policies ---
    try:
        policies = client.get_compliance_policies()
        if len(policies) >= 2:
            result.findings.append(Finding("MP.L2-3.8.1.CP", "Device compliance policies deployed", "PASS",
                                           f"{len(policies)} policies"))
        elif len(policies) > 0:
            result.findings.append(Finding("MP.L2-3.8.1.CP", "Insufficient compliance policies", "FAIL",
                                           f"Only {len(policies)} policy (need >= 2)"))
        else:
            result.findings.append(Finding("MP.L2-3.8.1.CP", "No compliance policies deployed", "FAIL"))
    except Exception as e:
        result.errors.append(f"MP.L2-3.8.1.CP: {e}")

    # --- AU.L2-3.3.1: Audit logging ---
    try:
        r = client.get("/v1.0/auditLogs/signIns")
        if r.status_code == 200:
            result.findings.append(Finding("AU.L2-3.3.1", "Audit logging accessible", "PASS",
                                           f"Sign-in logs: {len(r.json().get('value', []))} entries"))
        else:
            result.findings.append(Finding("AU.L2-3.3.1", "Cannot access audit logs", "FAIL"))
    except Exception as e:
        result.errors.append(f"AU.L2-3.3.1: {e}")

    # --- SC.L2-3.13.1: Secure score ---
    try:
        scores = client.get_secure_scores()
        if scores:
            current = scores[0].get("currentScore", 0)
            maximum = scores[0].get("maxScore", 1)
            pct = (current / maximum * 100) if maximum > 0 else 0
            if pct >= 50:
                result.findings.append(Finding("SC.L2-3.13.1", "Secure score above threshold", "PASS",
                                               f"{current}/{maximum} ({pct:.0f}%)"))
            else:
                result.findings.append(Finding("SC.L2-3.13.1", "Secure score below threshold", "FAIL",
                                               f"{current}/{maximum} ({pct:.0f}%) — need >= 50%"))
        else:
            result.findings.append(Finding("SC.L2-3.13.1", "No secure score data", "FAIL"))
    except Exception as e:
        result.errors.append(f"SC.L2-3.13.1: {e}")

    # --- AC.L2-3.1.2: Least privilege (role assignments) ---
    try:
        assignments = client.get_role_assignments()
        ga_template = "62e90394-69f5-4237-9190-012177145e10"
        ga_assignments = [a for a in assignments
                          if a.get("roleDefinitionId") == ga_template]
        if len(ga_assignments) <= 2:
            result.findings.append(Finding("AC.L2-3.1.2", "Global Admin assignments within limit", "PASS",
                                           f"{len(ga_assignments)} GA assignments (max 2 recommended)"))
        else:
            result.findings.append(Finding("AC.L2-3.1.2", "Too many Global Admin assignments", "FAIL",
                                           f"{len(ga_assignments)} GA assignments"))
    except Exception as e:
        result.errors.append(f"AC.L2-3.1.2: {e}")

    # --- IA.L2-3.5.1: Identify system users (organization identity) ---
    try:
        org = client.get_organization()
        if org:
            name = org[0].get("displayName", "")
            result.findings.append(Finding("IA.L2-3.5.1", "Organization identity configured", "PASS",
                                           f"Tenant: {name}"))
        else:
            result.findings.append(Finding("IA.L2-3.5.1", "No organization data", "FAIL"))
    except Exception as e:
        result.errors.append(f"IA.L2-3.5.1: {e}")

    return result


# ---------------------------------------------------------------------------
# Deploy workflow — simulates remediation tool writing to Graph API
# ---------------------------------------------------------------------------

def deploy_remediation(client: GraphClient) -> list[tuple[str, bool, str]]:
    """Simulate a CMMC remediation deployment via Graph API writes."""
    results = []

    # Deploy CA policy: MFA for all users
    r = client.post("/v1.0/identity/conditionalAccess/policies", {
        "displayName": "CMMC-MFA-AllUsers",
        "state": "enabledForReportingButNotEnforced",
        "conditions": {
            "users": {"includeUsers": ["All"], "excludeUsers": [BREAKGLASS_ID]},
            "applications": {"includeApplications": ["All"]}
        },
        "grantControls": {
            "operator": "OR",
            "builtInControls": ["mfa"]
        }
    })
    results.append(("POST CA Policy: CMMC-MFA-AllUsers", r.status_code == 201,
                     f"{r.status_code} — id={r.json().get('id', '?')[:8]}..."))

    # Deploy CA policy: Block legacy auth
    r = client.post("/v1.0/identity/conditionalAccess/policies", {
        "displayName": "CMMC-Block-Legacy-Auth",
        "state": "enabledForReportingButNotEnforced",
        "conditions": {
            "users": {"includeUsers": ["All"], "excludeUsers": [BREAKGLASS_ID]},
            "clientAppTypes": ["exchangeActiveSync", "other"]
        },
        "grantControls": {
            "operator": "OR",
            "builtInControls": ["block"]
        }
    })
    results.append(("POST CA Policy: CMMC-Block-Legacy-Auth", r.status_code == 201,
                     f"{r.status_code} — id={r.json().get('id', '?')[:8]}..."))

    # Enable FIDO2
    r = client.patch("/v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/fido2", {
        "state": "enabled"
    })
    results.append(("PATCH Auth Method: fido2 -> enabled", r.status_code == 200,
                     f"{r.status_code}"))

    # Enable Microsoft Authenticator
    r = client.patch("/v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/microsoftAuthenticator", {
        "state": "enabled"
    })
    results.append(("PATCH Auth Method: microsoftAuthenticator -> enabled", r.status_code == 200,
                     f"{r.status_code}"))

    # Deploy compliance policy
    r = client.post("/v1.0/deviceManagement/deviceCompliancePolicies", {
        "displayName": "CMMC-Windows-Compliance",
        "@odata.type": "#microsoft.graph.windows10CompliancePolicy",
        "bitLockerEnabled": True,
        "secureBootEnabled": True
    })
    results.append(("POST Compliance Policy: CMMC-Windows-Compliance", r.status_code == 201,
                     f"{r.status_code} — id={r.json().get('id', '?')[:8]}..."))

    # Deploy device configuration
    r = client.post("/v1.0/deviceManagement/deviceConfigurations", {
        "displayName": "CMMC-Defender-AV",
        "@odata.type": "#microsoft.graph.windows10EndpointProtectionConfiguration",
        "defenderCloudBlockLevel": "high"
    })
    results.append(("POST Device Config: CMMC-Defender-AV", r.status_code == 201,
                     f"{r.status_code} — id={r.json().get('id', '?')[:8]}..."))

    # Verify stateless: GET CA policies should still be empty
    r = client.get("/v1.0/identity/conditionalAccess/policies")
    ca_count = len(r.json().get("value", []))
    results.append(("GET CA Policies (verify stateless)", ca_count == 0,
                     f"Found {ca_count} policies (expected 0 — stateless mock)"))

    # Test error simulation
    r = client.get("/v1.0/users", params={"mock_status": "429"})
    results.append(("Error sim: mock_status=429", r.status_code == 429,
                     f"{r.status_code}, Retry-After={r.headers.get('retry-after', 'missing')}"))

    r = client.get("/v1.0/users", params={"mock_status": "403"})
    results.append(("Error sim: mock_status=403", r.status_code == 403,
                     f"{r.status_code}, code={r.json().get('error', {}).get('code', '?')}"))

    return results


# ---------------------------------------------------------------------------
# Stateful deploy-then-assess — the full remediation loop in one server
# ---------------------------------------------------------------------------

def deploy_then_assess(client: GraphClient) -> list[tuple[str, bool, str]]:
    """Deploy remediation to a stateful server, then assess the result."""
    results = []

    # --- Pre-assess: greenfield should be empty ---
    policies_before = client.get_ca_policies()
    results.append(("PRE: CA policies empty", len(policies_before) == 0,
                     f"{len(policies_before)} policies"))

    policy_before = client.get_auth_methods_policy()
    fido2_before = next((c for c in policy_before.get("authenticationMethodConfigurations", [])
                         if c.get("id") == "fido2"), {})
    results.append(("PRE: FIDO2 disabled", fido2_before.get("state") == "disabled",
                     f"fido2 state={fido2_before.get('state')}"))

    # --- Deploy: POST CA policies ---
    for name in ["CMMC-MFA-AllUsers", "CMMC-Block-Legacy-Auth", "CMMC-Compliant-Device",
                  "CMMC-Approved-Apps", "CMMC-Session-Timeout"]:
        r = client.post("/v1.0/identity/conditionalAccess/policies", {
            "displayName": name,
            "state": "enabledForReportingButNotEnforced",
            "conditions": {
                "users": {"includeUsers": ["All"], "excludeUsers": [BREAKGLASS_ID]},
                "applications": {"includeApplications": ["All"]}
            },
            "grantControls": {"operator": "OR", "builtInControls": ["mfa"]}
        })
        results.append((f"DEPLOY: POST {name}", r.status_code == 201,
                         f"{r.status_code}"))

    # --- Deploy: PATCH auth methods ---
    for method in ["fido2", "microsoftAuthenticator"]:
        r = client.patch(
            f"/v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method}",
            {"state": "enabled"})
        results.append((f"DEPLOY: PATCH {method} -> enabled", r.status_code == 200,
                         f"{r.status_code}"))

    # --- Post-assess: verify mutations are visible ---
    policies_after = client.get_ca_policies()
    results.append(("POST-ASSESS: 5 CA policies now exist", len(policies_after) == 5,
                     f"{len(policies_after)} policies"))

    policy_after = client.get_auth_methods_policy()
    fido2_after = next((c for c in policy_after.get("authenticationMethodConfigurations", [])
                        if c.get("id") == "fido2"), {})
    results.append(("POST-ASSESS: FIDO2 now enabled", fido2_after.get("state") == "enabled",
                     f"fido2 state={fido2_after.get('state')}"))

    msauth_after = next((c for c in policy_after.get("authenticationMethodConfigurations", [])
                         if c.get("id") == "microsoftAuthenticator"), {})
    results.append(("POST-ASSESS: Authenticator now enabled", msauth_after.get("state") == "enabled",
                     f"microsoftAuthenticator state={msauth_after.get('state')}"))

    # --- Reset and verify clean state ---
    r = client.post("/v1.0/_reset", {})
    results.append(("RESET: restore baseline", r.status_code == 200,
                     f"{r.status_code}, fixtures={r.json().get('fixtures_loaded')}"))

    policies_reset = client.get_ca_policies()
    results.append(("POST-RESET: CA policies empty again", len(policies_reset) == 0,
                     f"{len(policies_reset)} policies"))

    policy_reset = client.get_auth_methods_policy()
    fido2_reset = next((c for c in policy_reset.get("authenticationMethodConfigurations", [])
                        if c.get("id") == "fido2"), {})
    results.append(("POST-RESET: FIDO2 disabled again", fido2_reset.get("state") == "disabled",
                     f"fido2 state={fido2_reset.get('state')}"))

    return results


# ---------------------------------------------------------------------------
# $filter tests — verify the OData filter engine works via real HTTP
# ---------------------------------------------------------------------------

def test_filters(client: GraphClient, hardened_client: GraphClient | None = None) -> list[tuple[str, bool, str]]:
    """Test OData $filter engine via real HTTP requests."""
    results = []

    # Filter users by type
    r = client.get("/v1.0/users", params={"$filter": "userType eq 'Member'"})
    members = r.json().get("value", [])
    results.append(("$filter: users where Member", len(members) == 2,
                     f"{len(members)} members"))

    r = client.get("/v1.0/users", params={"$filter": "userType eq 'Guest'"})
    guests = r.json().get("value", [])
    results.append(("$filter: users where Guest", len(guests) == 0,
                     f"{len(guests)} guests"))

    # Filter service principals by appId
    r = client.get("/v1.0/servicePrincipals",
                    params={"$filter": "appId eq '00000003-0000-0000-c000-000000000000'"})
    sps = r.json().get("value", [])
    results.append(("$filter: SP by Graph appId", len(sps) == 1,
                     f"{len(sps)} matches, name={sps[0].get('displayName') if sps else '?'}"))

    # Filter + $top combo
    r = client.get("/v1.0/users", params={"$filter": "userType eq 'Member'", "$top": "1"})
    combo = r.json().get("value", [])
    results.append(("$filter + $top=1", len(combo) == 1,
                     f"{len(combo)} result"))

    # Compound filter
    r = client.get("/v1.0/users",
                    params={"$filter": "userType eq 'Member' and accountEnabled eq true"})
    compound = r.json().get("value", [])
    results.append(("$filter: compound (Member AND enabled)", len(compound) == 2,
                     f"{len(compound)} matches"))

    # Graceful degradation on bad syntax
    r = client.get("/v1.0/users", params={"$filter": "this is not valid OData!!!"})
    bad = r.json().get("value", [])
    results.append(("$filter: bad syntax -> full result", len(bad) == 2,
                     f"{len(bad)} (graceful degradation)"))

    # Hardened scenario filters
    if hardened_client:
        r = hardened_client.get("/v1.0/identity/conditionalAccess/policies",
                                 params={"$filter": "state eq 'enabledForReportingButNotEnforced'"})
        ca = r.json().get("value", [])
        results.append(("$filter: hardened CA by report-only state", len(ca) == 8,
                         f"{len(ca)} policies"))

        r = hardened_client.get("/v1.0/deviceManagement/managedDevices",
                                 params={"$filter": "complianceState eq 'compliant'"})
        devices = r.json().get("value", [])
        results.append(("$filter: hardened compliant devices", len(devices) == 3,
                         f"{len(devices)} compliant devices"))

    return results


def print_results(title: str, results: list[tuple[str, bool, str]]):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")

    for name, ok, detail in results:
        icon = "\033[32mOK\033[0m  " if ok else "\033[31mFAIL\033[0m"
        print(f"  {icon}  {name}")
        print(f"        \033[90m{detail}\033[0m")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n  Result: {passed}/{len(results)} checks passed")
    print(f"{'=' * 70}")


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def print_assessment(result: AssessmentResult):
    print(f"\n{'=' * 70}")
    print(f"  CMMC L2 Assessment — {result.scenario.upper()} scenario")
    print(f"{'=' * 70}")
    print(f"  {'Control':<20} {'Status':<6} {'Description'}")
    print(f"  {'-' * 18}   {'-' * 4}   {'-' * 40}")

    for f in result.findings:
        icon = "\033[32mPASS\033[0m" if f.status == "PASS" else (
            "\033[31mFAIL\033[0m" if f.status == "FAIL" else "\033[33m N/A\033[0m")
        print(f"  {f.control:<20} {icon}   {f.description}")
        if f.detail:
            print(f"  {'':20}        \033[90m{f.detail}\033[0m")

    if result.errors:
        print(f"\n  \033[31mErrors:\033[0m")
        for e in result.errors:
            print(f"    {e}")

    print(f"\n  Score: {result.pass_count}/{len(result.findings)} controls passing "
          f"({result.fail_count} failing)")
    print(f"{'=' * 70}")


def print_deploy(results: list[tuple[str, bool, str]]):
    print(f"\n{'=' * 70}")
    print(f"  CMMC Remediation Deploy — GREENFIELD scenario")
    print(f"{'=' * 70}")

    for name, ok, detail in results:
        icon = "\033[32mOK\033[0m  " if ok else "\033[31mFAIL\033[0m"
        print(f"  {icon}  {name}")
        print(f"        \033[90m{detail}\033[0m")

    passed = sum(1 for _, ok, _ in results if ok)
    print(f"\n  Result: {passed}/{len(results)} operations succeeded")
    print(f"{'=' * 70}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="m365-sim Test Harness")
    parser.add_argument("--workflow",
                        choices=["assess", "deploy", "stateful", "filter", "all"],
                        default="all")
    parser.add_argument("--port", type=int, default=0, help="Port (0 = auto)")
    args = parser.parse_args()

    all_ok = True
    ports = [args.port or get_free_port(), get_free_port(), get_free_port(), get_free_port()]
    procs: list[subprocess.Popen | None] = []

    def cleanup():
        for p in procs:
            if p:
                stop_server(p)

    try:
        # ---- ASSESS workflow ----
        if args.workflow in ("assess", "all"):
            print("\nStarting greenfield server...")
            proc = start_server(ports[0], "greenfield")
            procs.append(proc)
            client = GraphClient(f"http://localhost:{ports[0]}")
            greenfield_result = assess_tenant(client, "greenfield")
            print_assessment(greenfield_result)
            stop_server(proc); procs.remove(proc)

            print("\nStarting hardened server...")
            proc = start_server(ports[1], "hardened")
            procs.append(proc)
            client = GraphClient(f"http://localhost:{ports[1]}")
            hardened_result = assess_tenant(client, "hardened")
            print_assessment(hardened_result)
            stop_server(proc); procs.remove(proc)

            print(f"\n{'=' * 70}")
            print(f"  COMPARISON")
            print(f"{'=' * 70}")
            print(f"  Greenfield: {greenfield_result.pass_count}/{len(greenfield_result.findings)} PASS")
            print(f"  Hardened:   {hardened_result.pass_count}/{len(hardened_result.findings)} PASS")
            delta = hardened_result.pass_count - greenfield_result.pass_count
            print(f"  Delta:      +{delta} controls remediated")
            print(f"{'=' * 70}")

            if greenfield_result.errors or hardened_result.errors:
                all_ok = False

        # ---- DEPLOY workflow (stateless) ----
        if args.workflow in ("deploy", "all"):
            print("\nStarting greenfield server for deploy test...")
            proc = start_server(ports[0], "greenfield")
            procs.append(proc)
            client = GraphClient(f"http://localhost:{ports[0]}")
            deploy_results = deploy_remediation(client)
            print_deploy(deploy_results)
            stop_server(proc); procs.remove(proc)

            if not all(ok for _, ok, _ in deploy_results):
                all_ok = False

        # ---- STATEFUL deploy-then-assess workflow ----
        if args.workflow in ("stateful", "all"):
            print("\nStarting STATEFUL greenfield server...")
            proc = start_server(ports[0], "greenfield", stateful=True)
            procs.append(proc)
            client = GraphClient(f"http://localhost:{ports[0]}")
            stateful_results = deploy_then_assess(client)
            print_results("Stateful Deploy-Then-Assess — GREENFIELD", stateful_results)
            stop_server(proc); procs.remove(proc)

            if not all(ok for _, ok, _ in stateful_results):
                all_ok = False

        # ---- FILTER workflow ----
        if args.workflow in ("filter", "all"):
            print("\nStarting greenfield server for filter tests...")
            proc_g = start_server(ports[0], "greenfield")
            procs.append(proc_g)
            greenfield_client = GraphClient(f"http://localhost:{ports[0]}")

            print("Starting hardened server for filter tests...")
            proc_h = start_server(ports[1], "hardened")
            procs.append(proc_h)
            hardened_client = GraphClient(f"http://localhost:{ports[1]}")

            filter_results = test_filters(greenfield_client, hardened_client)
            print_results("OData $filter Engine Tests", filter_results)

            stop_server(proc_g); procs.remove(proc_g)
            stop_server(proc_h); procs.remove(proc_h)

            if not all(ok for _, ok, _ in filter_results):
                all_ok = False

    finally:
        cleanup()

    if all_ok:
        print("\nAll workflows completed successfully.")
    else:
        print("\nSome checks failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
