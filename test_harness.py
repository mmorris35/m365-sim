#!/usr/bin/env python3
"""
m365-sim Test Harness — Graph API Client Simulator

Simulates a CMMC compliance assessment tool making real Microsoft Graph API
calls against the mock server. Tests nine workflows:

1.  ASSESS             — greenfield + hardened tenant posture
2.  DEPLOY             — stateless write operations + error sim
3.  STATEFUL           — deploy-then-assess with _reset
4.  FILTER             — OData $filter engine (eq, compound, etc.)
5.  CLOUD              — GCC High + Commercial E5 cloud targets
6.  MOCK-CLOUD         — X-Mock-Cloud header override
7.  EXTENDED-FILTER    — ne, gt, lt, ge, le, startswith, contains, or
8.  PARTIAL            — mid-deployment scenario posture
9.  AUTH               — Bearer-only enforcement + error sim edge cases
10. EXPAND             — $expand inline resource expansion
11. GCC-HIGH-SCENARIOS — GCC High hardened + partial posture
12. BETA               — /beta/ route mirror with context URL rewriting
13. E5-SCENARIOS       — Commercial E5 hardened + partial posture
14. ENFORCED           — hardened-enforced with CA policies state=enabled
15. PRIORITY-ENDPOINTS — 9 priority-1 Graph API endpoints (Phase 23)
16. DEFENDER           — Defender for Endpoint /api/* endpoints

Usage:
    python test_harness.py                             # run all workflows
    python test_harness.py --workflow assess            # assess both scenarios
    python test_harness.py --workflow cloud             # cloud targets only
    python test_harness.py --workflow extended-filter   # extended filters only
    python test_harness.py --port 9999                 # custom port
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


def start_server(port: int, scenario: str = "greenfield", stateful: bool = False,
                  cloud: str = "gcc-moderate") -> subprocess.Popen:
    cmd = [sys.executable, "server.py", "--port", str(port), "--scenario", scenario,
           "--cloud", cloud]
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


# ---------------------------------------------------------------------------
# Cloud target tests — GCC High + Commercial E5
# ---------------------------------------------------------------------------

def test_cloud_targets() -> list[tuple[str, bool, str]]:
    """Test GCC High and Commercial E5 cloud targets."""
    results = []
    ports = [get_free_port(), get_free_port()]

    # --- GCC High ---
    proc_gcc = start_server(ports[0], "greenfield", cloud="gcc-high")
    try:
        client = GraphClient(f"http://localhost:{ports[0]}")

        # Health check
        r = client.get("/health")
        health = r.json()
        results.append(("GCC High: health endpoint", r.status_code == 200 and health.get("cloud") == "gcc-high",
                         f"cloud={health.get('cloud')}"))

        # Organization identity
        org = client.get_organization()
        org_name = org[0].get("displayName", "") if org else ""
        results.append(("GCC High: org is Contoso Defense Federal LLC",
                         org_name == "Contoso Defense Federal LLC",
                         f"displayName={org_name}"))

        # Graph API URL uses .us
        r = client.get("/v1.0/users")
        context = r.json().get("@odata.context", "")
        results.append(("GCC High: @odata.context uses graph.microsoft.us",
                         "graph.microsoft.us" in context,
                         f"context={context[:60]}"))

        # Domain is .us
        domains = client.get_domains()
        has_us = any("contoso-defense.us" in d.get("id", "") for d in domains)
        results.append(("GCC High: domain is contoso-defense.us", has_us,
                         f"domains={[d.get('id') for d in domains]}"))
    finally:
        stop_server(proc_gcc)

    # --- Commercial E5 ---
    proc_e5 = start_server(ports[1], "greenfield", cloud="commercial-e5")
    try:
        client = GraphClient(f"http://localhost:{ports[1]}")

        # Health check
        r = client.get("/health")
        health = r.json()
        results.append(("Commercial E5: health endpoint",
                         r.status_code == 200 and health.get("cloud") == "commercial-e5",
                         f"cloud={health.get('cloud')}"))

        # Organization identity
        org = client.get_organization()
        org_name = org[0].get("displayName", "") if org else ""
        results.append(("Commercial E5: org is Contoso Corp",
                         org_name == "Contoso Corp",
                         f"displayName={org_name}"))

        # Graph API URL uses .com
        r = client.get("/v1.0/users")
        context = r.json().get("@odata.context", "")
        results.append(("Commercial E5: @odata.context uses graph.microsoft.com",
                         "graph.microsoft.com" in context,
                         f"context={context[:60]}"))
    finally:
        stop_server(proc_e5)

    return results


# ---------------------------------------------------------------------------
# X-Mock-Cloud header override tests
# ---------------------------------------------------------------------------

def test_mock_cloud_header() -> list[tuple[str, bool, str]]:
    """Test X-Mock-Cloud header switches fixture context at runtime."""
    results = []
    port = get_free_port()

    # Start a GCC Moderate server
    proc = start_server(port, "greenfield", cloud="gcc-moderate")
    try:
        base = f"http://localhost:{port}"
        headers = {"Authorization": "Bearer test", "X-Mock-Cloud": "gcc-high"}

        # Default request should use gcc-moderate
        r = httpx.get(f"{base}/v1.0/organization",
                       headers={"Authorization": "Bearer test"})
        ctx_default = r.json().get("@odata.context", "")
        results.append(("Default: gcc-moderate context",
                         "graph.microsoft.com" in ctx_default,
                         f"context={ctx_default[:60]}"))

        # Override to gcc-high
        r = httpx.get(f"{base}/v1.0/organization", headers=headers)
        ctx_override = r.json().get("@odata.context", "")
        results.append(("X-Mock-Cloud: gcc-high overrides to .us",
                         "graph.microsoft.us" in ctx_override,
                         f"context={ctx_override[:60]}"))

        org = r.json().get("value", [])
        org_name = org[0].get("displayName", "") if org else ""
        results.append(("X-Mock-Cloud: org switches to Federal LLC",
                         org_name == "Contoso Defense Federal LLC",
                         f"displayName={org_name}"))
    finally:
        stop_server(proc)

    return results


# ---------------------------------------------------------------------------
# Extended $filter operator tests
# ---------------------------------------------------------------------------

def test_extended_filters(client: GraphClient) -> list[tuple[str, bool, str]]:
    """Test extended OData $filter operators: ne, gt, lt, startswith, contains, in."""
    results = []

    # ne operator
    r = client.get("/v1.0/users", params={"$filter": "userType ne 'Guest'"})
    ne_result = r.json().get("value", [])
    results.append(("$filter ne: userType ne Guest", len(ne_result) == 2,
                     f"{len(ne_result)} results"))

    # startswith
    r = client.get("/v1.0/users", params={"$filter": "startswith(displayName,'Mike')"})
    sw_result = r.json().get("value", [])
    results.append(("$filter startswith: displayName starts with Mike", len(sw_result) == 1,
                     f"{len(sw_result)} results, name={sw_result[0].get('displayName') if sw_result else '?'}"))

    # contains
    r = client.get("/v1.0/users", params={"$filter": "contains(displayName,'Morris')"})
    ct_result = r.json().get("value", [])
    results.append(("$filter contains: displayName contains Morris", len(ct_result) == 1,
                     f"{len(ct_result)} results"))

    # gt on secure scores
    r = client.get("/v1.0/security/secureScores", params={"$filter": "currentScore gt 10"})
    gt_result = r.json().get("value", [])
    results.append(("$filter gt: currentScore gt 10", len(gt_result) == 1,
                     f"{len(gt_result)} results"))

    # lt on secure scores
    r = client.get("/v1.0/security/secureScores", params={"$filter": "currentScore lt 10"})
    lt_result = r.json().get("value", [])
    results.append(("$filter lt: currentScore lt 10", len(lt_result) == 0,
                     f"{len(lt_result)} results"))

    # ge on secure scores
    r = client.get("/v1.0/security/secureScores", params={"$filter": "currentScore ge 12"})
    ge_result = r.json().get("value", [])
    results.append(("$filter ge: currentScore ge 12", len(ge_result) == 1,
                     f"{len(ge_result)} results"))

    # le on secure scores
    r = client.get("/v1.0/security/secureScores", params={"$filter": "currentScore le 12"})
    le_result = r.json().get("value", [])
    results.append(("$filter le: currentScore le 12", len(le_result) == 1,
                     f"{len(le_result)} results"))

    # or combinator
    r = client.get("/v1.0/users",
                    params={"$filter": "displayName eq 'Mike Morris' or displayName eq 'BreakGlass Admin'"})
    or_result = r.json().get("value", [])
    results.append(("$filter or: two display names", len(or_result) == 2,
                     f"{len(or_result)} results"))

    return results


# ---------------------------------------------------------------------------
# Partial scenario tests — mid-deployment posture
# ---------------------------------------------------------------------------

def test_partial_scenario() -> list[tuple[str, bool, str]]:
    """Test the partial (mid-deployment) scenario."""
    results = []
    port = get_free_port()

    proc = start_server(port, "partial", cloud="gcc-moderate")
    try:
        client = GraphClient(f"http://localhost:{port}")

        # Health check
        r = client.get("/health")
        health = r.json()
        results.append(("Partial: health endpoint",
                         r.status_code == 200 and health.get("scenario") == "partial",
                         f"scenario={health.get('scenario')}"))

        # Should have SOME CA policies (not 0 like greenfield, not 8 like hardened)
        policies = client.get_ca_policies()
        results.append(("Partial: has some CA policies (1-7)",
                         0 < len(policies) < 8,
                         f"{len(policies)} policies"))

        # Policies should still exclude break-glass
        if policies:
            first = policies[0]
            excluded = (first.get("conditions") or {}).get("users", {}).get("excludeUsers", [])
            results.append(("Partial: break-glass excluded from CA",
                             BREAKGLASS_ID in excluded,
                             f"excludeUsers={excluded}"))

        # Should have some auth methods enabled but not all
        auth = client.get_auth_methods_policy()
        configs = auth.get("authenticationMethodConfigurations", [])
        enabled = [c for c in configs if c.get("state") == "enabled"]
        results.append(("Partial: some auth methods enabled",
                         0 < len(enabled) < len(configs),
                         f"{len(enabled)}/{len(configs)} enabled"))

        # Organization should still be the same tenant
        org = client.get_organization()
        org_name = org[0].get("displayName", "") if org else ""
        results.append(("Partial: same tenant identity",
                         org_name == "Contoso Defense LLC",
                         f"displayName={org_name}"))
    finally:
        stop_server(proc)

    return results


# ---------------------------------------------------------------------------
# Auth edge cases — Bearer-only enforcement
# ---------------------------------------------------------------------------

def test_auth_edge_cases() -> list[tuple[str, bool, str]]:
    """Test auth enforcement edge cases."""
    results = []
    port = get_free_port()

    proc = start_server(port, "greenfield")
    try:
        base = f"http://localhost:{port}"

        # No header -> 401
        r = httpx.get(f"{base}/v1.0/users")
        results.append(("Auth: missing header -> 401", r.status_code == 401,
                         f"status={r.status_code}"))

        # Bearer token -> 200
        r = httpx.get(f"{base}/v1.0/users",
                       headers={"Authorization": "Bearer test-token"})
        results.append(("Auth: Bearer token -> 200", r.status_code == 200,
                         f"status={r.status_code}"))

        # Basic auth -> 401 (Bearer-only)
        r = httpx.get(f"{base}/v1.0/users",
                       headers={"Authorization": "Basic dXNlcjpwYXNz"})
        results.append(("Auth: Basic scheme -> 401 (Bearer-only)", r.status_code == 401,
                         f"status={r.status_code}"))

        # Empty Bearer -> 401
        r = httpx.get(f"{base}/v1.0/users",
                       headers={"Authorization": "Bearer"})
        results.append(("Auth: empty Bearer -> 401", r.status_code == 401,
                         f"status={r.status_code}"))

        # Health endpoint skips auth
        r = httpx.get(f"{base}/health")
        results.append(("Auth: /health no auth required", r.status_code == 200,
                         f"status={r.status_code}"))

        # Error sim: Retry-After value
        r = httpx.get(f"{base}/v1.0/users",
                       headers={"Authorization": "Bearer t"},
                       params={"mock_status": "429"})
        retry_after = r.headers.get("retry-after", "")
        results.append(("Error sim: Retry-After is 1", retry_after == "1",
                         f"Retry-After={retry_after}"))
    finally:
        stop_server(proc)

    return results


# ---------------------------------------------------------------------------
# $expand tests — inline related resource expansion
# ---------------------------------------------------------------------------

def test_expand(client: GraphClient) -> list[tuple[str, bool, str]]:
    """Test $expand query parameter for inline resource expansion."""
    results = []

    # Expand memberOf on users (groups fixture is empty in greenfield)
    r = client.get("/v1.0/users", params={"$expand": "memberOf"})
    users = r.json().get("value", [])
    has_member_of = all("memberOf" in u for u in users)
    results.append(("$expand: users memberOf", has_member_of and len(users) == 2,
                     f"{len(users)} users, all have memberOf={has_member_of}"))

    # Expand authentication on users
    r = client.get("/v1.0/users", params={"$expand": "authentication"})
    users = r.json().get("value", [])
    has_auth = all("authentication" in u for u in users)
    results.append(("$expand: users authentication", has_auth,
                     f"all have authentication={has_auth}"))

    # Expand on /me singleton
    r = client.get("/v1.0/me", params={"$expand": "authentication"})
    me = r.json()
    results.append(("$expand: /me authentication", "authentication" in me,
                     f"has authentication={'authentication' in me}, methods={len(me.get('authentication', []))}"))

    # Expand members on directoryRoles
    r = client.get("/v1.0/directoryRoles", params={"$expand": "members"})
    roles = r.json().get("value", [])
    has_members = all("members" in role for role in roles)
    results.append(("$expand: directoryRoles members", has_members and len(roles) > 0,
                     f"{len(roles)} roles, all have members={has_members}"))

    # Wildcard expand on users
    r = client.get("/v1.0/users", params={"$expand": "*"})
    users = r.json().get("value", [])
    has_both = all("memberOf" in u and "authentication" in u for u in users)
    results.append(("$expand=*: users wildcard", has_both,
                     f"all have memberOf+authentication={has_both}"))

    # Unknown expand field — graceful
    r = client.get("/v1.0/users", params={"$expand": "nonexistent"})
    users = r.json().get("value", [])
    no_extra = all("nonexistent" not in u for u in users)
    results.append(("$expand: unknown field graceful", r.status_code == 200 and no_extra,
                     f"status={r.status_code}, no extra key={no_extra}"))

    # Combine $expand + $filter + $top
    r = client.get("/v1.0/users", params={
        "$expand": "memberOf",
        "$filter": "userType eq 'Member'",
        "$top": "1",
    })
    combo = r.json().get("value", [])
    results.append(("$expand + $filter + $top combo",
                     len(combo) == 1 and "memberOf" in combo[0],
                     f"{len(combo)} user(s), memberOf={'memberOf' in combo[0] if combo else '?'}"))

    return results


# ---------------------------------------------------------------------------
# GCC High scenarios — hardened + partial posture assessment
# ---------------------------------------------------------------------------

def test_gcc_high_scenarios() -> list[tuple[str, bool, str]]:
    """Test GCC High hardened and partial scenarios."""
    results = []

    # --- Hardened ---
    port_h = get_free_port()
    proc_h = start_server(port_h, "hardened", cloud="gcc-high")
    try:
        client = GraphClient(f"http://localhost:{port_h}")

        # Health check
        r = client.get("/health")
        health = r.json()
        results.append(("GCC High hardened: health",
                         health.get("cloud") == "gcc-high" and health.get("scenario") == "hardened",
                         f"cloud={health.get('cloud')}, scenario={health.get('scenario')}"))

        # 8 CA policies, all report-only
        policies = client.get_ca_policies()
        all_report_only = all(p.get("state") == "enabledForReportingButNotEnforced" for p in policies)
        results.append(("GCC High hardened: 8 report-only CA policies",
                         len(policies) == 8 and all_report_only,
                         f"{len(policies)} policies, all report-only={all_report_only}"))

        # Break-glass excluded
        all_excluded = all(
            BREAKGLASS_ID in (p.get("conditions") or {}).get("users", {}).get("excludeUsers", [])
            for p in policies
        )
        results.append(("GCC High hardened: break-glass excluded",
                         all_excluded,
                         f"all exclude {BREAKGLASS_ID}={all_excluded}"))

        # FIDO2 registered
        auth_methods = client.get_me_auth_methods()
        fido2 = [m for m in auth_methods if "fido2" in m.get("@odata.type", "").lower()]
        results.append(("GCC High hardened: FIDO2 registered",
                         len(fido2) == 1,
                         f"{len(fido2)} FIDO2 key(s)"))

        # All devices compliant
        devices = client.get_managed_devices()
        all_compliant = all(d.get("complianceState") == "compliant" for d in devices)
        results.append(("GCC High hardened: 3 compliant devices",
                         len(devices) == 3 and all_compliant,
                         f"{len(devices)} devices, all compliant={all_compliant}"))

        # URLs use graph.microsoft.us
        r = client.get("/v1.0/users")
        context = r.json().get("@odata.context", "")
        results.append(("GCC High hardened: graph.microsoft.us URL",
                         "graph.microsoft.us" in context,
                         f"context={context[:60]}"))
    finally:
        stop_server(proc_h)

    # --- Partial ---
    port_p = get_free_port()
    proc_p = start_server(port_p, "partial", cloud="gcc-high")
    try:
        client = GraphClient(f"http://localhost:{port_p}")

        # 3 CA policies (subset)
        policies = client.get_ca_policies()
        results.append(("GCC High partial: 3 CA policies",
                         len(policies) == 3,
                         f"{len(policies)} policies"))

        # Only 1 auth method enabled
        auth = client.get_auth_methods_policy()
        configs = auth.get("authenticationMethodConfigurations", [])
        enabled = [c for c in configs if c.get("state") == "enabled"]
        results.append(("GCC High partial: 1 auth method enabled",
                         len(enabled) == 1,
                         f"{len(enabled)} enabled: {[c.get('id') for c in enabled]}"))

        # 1 managed device
        devices = client.get_managed_devices()
        results.append(("GCC High partial: 1 device",
                         len(devices) == 1,
                         f"{len(devices)} device(s)"))

        # No FIDO2 in partial
        auth_methods = client.get_me_auth_methods()
        fido2 = [m for m in auth_methods if "fido2" in m.get("@odata.type", "").lower()]
        results.append(("GCC High partial: no FIDO2",
                         len(fido2) == 0,
                         f"{len(fido2)} FIDO2 key(s)"))

        # URLs use graph.microsoft.us
        r = client.get("/v1.0/users")
        context = r.json().get("@odata.context", "")
        results.append(("GCC High partial: graph.microsoft.us URL",
                         "graph.microsoft.us" in context,
                         f"context={context[:60]}"))
    finally:
        stop_server(proc_p)

    return results


# ---------------------------------------------------------------------------
# Beta API endpoint tests — /beta/ route mirror with context rewriting
# ---------------------------------------------------------------------------

def test_beta_endpoints(client: GraphClient) -> list[tuple[str, bool, str]]:
    """Test /beta/ route mirror with @odata.context URL rewriting."""
    results = []

    # GET /beta/users — context rewritten to beta
    r = client.get("/beta/users")
    data = r.json()
    context = data.get("@odata.context", "")
    results.append(("/beta/users returns 200", r.status_code == 200,
                     f"status={r.status_code}"))
    results.append(("/beta/users context uses /beta/", "/beta/" in context and "/v1.0/" not in context,
                     f"context={context[:65]}"))

    # GET /beta/me — singleton with beta context
    r = client.get("/beta/me")
    me = r.json()
    me_ctx = me.get("@odata.context", "")
    results.append(("/beta/me singleton with beta context",
                     r.status_code == 200 and "/beta/" in me_ctx,
                     f"displayName={me.get('displayName')}, context={me_ctx[:65]}"))

    # POST /beta/identity/conditionalAccess/policies — write works
    r = client.post("/beta/identity/conditionalAccess/policies", {
        "displayName": "Beta-Test-Policy",
        "state": "enabledForReportingButNotEnforced",
    })
    results.append(("/beta/ POST CA policy -> 201", r.status_code == 201,
                     f"status={r.status_code}, id={r.json().get('id', '?')[:8]}..."))

    # PATCH /beta/ auth method
    r = client.patch(
        "/beta/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/fido2",
        {"state": "enabled"})
    results.append(("/beta/ PATCH auth method -> 200", r.status_code == 200,
                     f"status={r.status_code}"))

    # $filter on /beta/
    r = client.get("/beta/users", params={"$filter": "userType eq 'Member'"})
    filtered = r.json().get("value", [])
    results.append(("/beta/ $filter works", len(filtered) == 2,
                     f"{len(filtered)} results"))

    # $top on /beta/
    r = client.get("/beta/users", params={"$top": "1"})
    topped = r.json().get("value", [])
    results.append(("/beta/ $top works", len(topped) == 1,
                     f"{len(topped)} result"))

    # $expand on /beta/
    r = client.get("/beta/users", params={"$expand": "memberOf"})
    expanded = r.json().get("value", [])
    has_expand = all("memberOf" in u for u in expanded)
    results.append(("/beta/ $expand works", has_expand,
                     f"all have memberOf={has_expand}"))

    # Error sim on /beta/
    r = client.get("/beta/users", params={"mock_status": "429"})
    results.append(("/beta/ error sim 429", r.status_code == 429,
                     f"status={r.status_code}, Retry-After={r.headers.get('retry-after')}"))

    # Unmapped /beta/ path -> 404
    r = client.get("/beta/nonexistent/path")
    results.append(("/beta/ unmapped path -> 404", r.status_code == 404,
                     f"status={r.status_code}"))

    return results


# ---------------------------------------------------------------------------
# Commercial E5 scenarios — hardened + partial posture
# ---------------------------------------------------------------------------

def test_e5_scenarios() -> list[tuple[str, bool, str]]:
    """Test Commercial E5 hardened and partial scenarios."""
    results = []

    # --- Hardened ---
    port_h = get_free_port()
    proc_h = start_server(port_h, "hardened", cloud="commercial-e5")
    try:
        client = GraphClient(f"http://localhost:{port_h}")

        # Health check
        r = client.get("/health")
        health = r.json()
        results.append(("E5 hardened: health",
                         health.get("cloud") == "commercial-e5" and health.get("scenario") == "hardened",
                         f"cloud={health.get('cloud')}, scenario={health.get('scenario')}"))

        # 8 CA policies, all report-only
        policies = client.get_ca_policies()
        all_report_only = all(p.get("state") == "enabledForReportingButNotEnforced" for p in policies)
        results.append(("E5 hardened: 8 report-only CA policies",
                         len(policies) == 8 and all_report_only,
                         f"{len(policies)} policies, all report-only={all_report_only}"))

        # Break-glass excluded
        all_excluded = all(
            BREAKGLASS_ID in (p.get("conditions") or {}).get("users", {}).get("excludeUsers", [])
            for p in policies
        )
        results.append(("E5 hardened: break-glass excluded", all_excluded,
                         f"all exclude break-glass={all_excluded}"))

        # Org is Contoso Corp (not Defense LLC)
        org = client.get_organization()
        org_name = org[0].get("displayName", "") if org else ""
        results.append(("E5 hardened: org is Contoso Corp",
                         org_name == "Contoso Corp",
                         f"displayName={org_name}"))

        # 3 compliant devices
        devices = client.get_managed_devices()
        all_compliant = all(d.get("complianceState") == "compliant" for d in devices)
        results.append(("E5 hardened: 3 compliant devices",
                         len(devices) == 3 and all_compliant,
                         f"{len(devices)} devices, all compliant={all_compliant}"))

        # Uses graph.microsoft.com
        r = client.get("/v1.0/users")
        context = r.json().get("@odata.context", "")
        results.append(("E5 hardened: graph.microsoft.com URL",
                         "graph.microsoft.com" in context,
                         f"context={context[:60]}"))
    finally:
        stop_server(proc_h)

    # --- Partial ---
    port_p = get_free_port()
    proc_p = start_server(port_p, "partial", cloud="commercial-e5")
    try:
        client = GraphClient(f"http://localhost:{port_p}")

        # 3 CA policies
        policies = client.get_ca_policies()
        results.append(("E5 partial: 3 CA policies",
                         len(policies) == 3,
                         f"{len(policies)} policies"))

        # 1 auth method enabled
        auth = client.get_auth_methods_policy()
        configs = auth.get("authenticationMethodConfigurations", [])
        enabled = [c for c in configs if c.get("state") == "enabled"]
        results.append(("E5 partial: 1 auth method enabled",
                         len(enabled) == 1,
                         f"{len(enabled)} enabled: {[c.get('id') for c in enabled]}"))

        # 1 device
        devices = client.get_managed_devices()
        results.append(("E5 partial: 1 device",
                         len(devices) == 1,
                         f"{len(devices)} device(s)"))

        # Org is still Contoso Corp
        org = client.get_organization()
        org_name = org[0].get("displayName", "") if org else ""
        results.append(("E5 partial: org is Contoso Corp",
                         org_name == "Contoso Corp",
                         f"displayName={org_name}"))
    finally:
        stop_server(proc_p)

    return results


# ---------------------------------------------------------------------------
# Enforced scenario — CA policies with state: "enabled"
# ---------------------------------------------------------------------------

def test_enforced_scenario() -> list[tuple[str, bool, str]]:
    """Test hardened-enforced scenario where CA policies are fully enabled."""
    results = []
    port = get_free_port()

    proc = start_server(port, "hardened-enforced")
    try:
        client = GraphClient(f"http://localhost:{port}")

        # 8 CA policies, all state: "enabled" (not report-only)
        policies = client.get_ca_policies()
        all_enabled = all(p.get("state") == "enabled" for p in policies)
        results.append(("Enforced: 8 CA policies with state=enabled",
                         len(policies) == 8 and all_enabled,
                         f"{len(policies)} policies, all enabled={all_enabled}"))

        # Break-glass still excluded
        all_excluded = all(
            BREAKGLASS_ID in (p.get("conditions") or {}).get("users", {}).get("excludeUsers", [])
            for p in policies
        )
        results.append(("Enforced: break-glass excluded",
                         all_excluded, f"all exclude break-glass={all_excluded}"))

        # FIDO2 registered (same as hardened)
        auth_methods = client.get_me_auth_methods()
        fido2 = [m for m in auth_methods if "fido2" in m.get("@odata.type", "").lower()]
        results.append(("Enforced: FIDO2 registered",
                         len(fido2) == 1, f"{len(fido2)} FIDO2 key(s)"))

        # 3 compliant devices (same as hardened)
        devices = client.get_managed_devices()
        results.append(("Enforced: 3 compliant devices",
                         len(devices) == 3, f"{len(devices)} devices"))

        # Org identity unchanged
        org = client.get_organization()
        org_name = org[0].get("displayName", "") if org else ""
        results.append(("Enforced: org is Contoso Defense LLC",
                         org_name == "Contoso Defense LLC",
                         f"displayName={org_name}"))
    finally:
        stop_server(proc)

    return results


# ---------------------------------------------------------------------------
# Priority-1 endpoints — Phase 23 new Graph API endpoints
# ---------------------------------------------------------------------------

def test_priority_endpoints(client: GraphClient, hardened_client: GraphClient) -> list[tuple[str, bool, str]]:
    """Test the 9 priority-1 Graph API endpoints added in Phase 23."""
    results = []

    # Authorization policy (singleton)
    r = client.get("/v1.0/policies/authorizationPolicy")
    results.append(("authorizationPolicy: 200 singleton",
                     r.status_code == 200 and "id" in r.json(),
                     f"status={r.status_code}"))

    # Subscribed SKUs (collection)
    r = client.get("/v1.0/subscribedSkus")
    skus = r.json().get("value", [])
    results.append(("subscribedSkus: has SKUs",
                     r.status_code == 200 and len(skus) > 0,
                     f"{len(skus)} SKUs"))

    # MFA registration report (singleton)
    r = client.get("/v1.0/reports/authenticationMethods/usersRegisteredByMethod")
    results.append(("usersRegisteredByMethod: 200 singleton",
                     r.status_code == 200,
                     f"status={r.status_code}"))

    # Access reviews (empty greenfield, populated hardened)
    r_g = client.get("/v1.0/identityGovernance/accessReviews/definitions")
    r_h = hardened_client.get("/v1.0/identityGovernance/accessReviews/definitions")
    g_count = len(r_g.json().get("value", []))
    h_count = len(r_h.json().get("value", []))
    results.append(("accessReviews: greenfield 0, hardened 2+",
                     g_count == 0 and h_count >= 2,
                     f"greenfield={g_count}, hardened={h_count}"))

    # Managed app policies (empty greenfield, populated hardened)
    r_g = client.get("/v1.0/deviceAppManagement/managedAppPolicies")
    r_h = hardened_client.get("/v1.0/deviceAppManagement/managedAppPolicies")
    g_count = len(r_g.json().get("value", []))
    h_count = len(r_h.json().get("value", []))
    results.append(("managedAppPolicies: greenfield 0, hardened 3+",
                     g_count == 0 and h_count >= 3,
                     f"greenfield={g_count}, hardened={h_count}"))

    # Mobile apps (empty greenfield, populated hardened)
    r_h = hardened_client.get("/v1.0/deviceAppManagement/mobileApps")
    h_count = len(r_h.json().get("value", []))
    results.append(("mobileApps: hardened has 5+ apps",
                     h_count >= 5,
                     f"hardened={h_count} apps"))

    # Detected apps (empty greenfield, populated hardened)
    r_h = hardened_client.get("/v1.0/deviceManagement/detectedApps")
    h_count = len(r_h.json().get("value", []))
    results.append(("detectedApps: hardened has 10+ apps",
                     h_count >= 10,
                     f"hardened={h_count} apps"))

    # Provisioning logs (collection)
    r = client.get("/v1.0/auditLogs/provisioning")
    results.append(("provisioningLogs: 200 collection",
                     r.status_code == 200 and "value" in r.json(),
                     f"status={r.status_code}"))

    # Security alerts v1 (collection)
    r = client.get("/v1.0/security/alerts")
    results.append(("securityAlerts v1: 200 collection",
                     r.status_code == 200 and "value" in r.json(),
                     f"status={r.status_code}"))

    return results


# ---------------------------------------------------------------------------
# Defender for Endpoint API — /api/* endpoints
# ---------------------------------------------------------------------------

def test_defender_api() -> list[tuple[str, bool, str]]:
    """Test Defender for Endpoint /api/* endpoints across scenarios."""
    results = []

    # --- Greenfield (all empty) ---
    port_g = get_free_port()
    proc_g = start_server(port_g, "greenfield")
    try:
        client = GraphClient(f"http://localhost:{port_g}")

        endpoints = [
            ("/api/alerts", "defender alerts"),
            ("/api/apps", "defender apps"),
            ("/api/deviceavinfo", "device AV info"),
            ("/api/policies/appcontrol", "app control policies"),
            ("/api/vulnerabilities/machinesVulnerabilities", "machine vulns"),
        ]
        for path, name in endpoints:
            r = client.get(path)
            count = len(r.json().get("value", []))
            results.append((f"Greenfield {name}: empty",
                             r.status_code == 200 and count == 0,
                             f"status={r.status_code}, count={count}"))

        # Parameterized endpoint
        r = client.get("/api/machines/device-001/recommendations")
        results.append(("Greenfield machine recommendations: 200",
                         r.status_code == 200,
                         f"status={r.status_code}"))
    finally:
        stop_server(proc_g)

    # --- Hardened (populated) ---
    port_h = get_free_port()
    proc_h = start_server(port_h, "hardened")
    try:
        client = GraphClient(f"http://localhost:{port_h}")

        # Alerts — resolved
        r = client.get("/api/alerts")
        alerts = r.json().get("value", [])
        all_resolved = all(a.get("status") == "Resolved" for a in alerts) if alerts else False
        results.append(("Hardened defender alerts: resolved",
                         len(alerts) > 0 and all_resolved,
                         f"{len(alerts)} alerts, all resolved={all_resolved}"))

        # Device AV info — AV enabled
        r = client.get("/api/deviceavinfo")
        av = r.json().get("value", [])
        results.append(("Hardened device AV: 3 devices with AV",
                         len(av) == 3,
                         f"{len(av)} devices"))

        # App control — WDAC policies
        r = client.get("/api/policies/appcontrol")
        policies = r.json().get("value", [])
        results.append(("Hardened app control: WDAC policies",
                         len(policies) >= 2,
                         f"{len(policies)} policies"))

        # Context URL uses securitycenter
        r = client.get("/api/alerts")
        ctx = r.json().get("@odata.context", "")
        results.append(("Defender context: api.securitycenter.microsoft.com",
                         "api.securitycenter.microsoft.com" in ctx,
                         f"context={ctx[:60]}"))
    finally:
        stop_server(proc_h)

    # --- Auth enforcement ---
    port_a = get_free_port()
    proc_a = start_server(port_a, "greenfield")
    try:
        r = httpx.get(f"http://localhost:{port_a}/api/alerts")
        results.append(("Defender auth: no header -> 401",
                         r.status_code == 401,
                         f"status={r.status_code}"))
    finally:
        stop_server(proc_a)

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
                        choices=["assess", "deploy", "stateful", "filter",
                                 "cloud", "mock-cloud", "extended-filter",
                                 "partial", "auth", "expand",
                                 "gcc-high-scenarios", "beta",
                                 "e5-scenarios", "enforced",
                                 "priority-endpoints", "defender", "all"],
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

        # ---- CLOUD TARGETS workflow ----
        if args.workflow in ("cloud", "all"):
            print("\nTesting cloud targets (GCC High, Commercial E5)...")
            cloud_results = test_cloud_targets()
            print_results("Cloud Targets — GCC High + Commercial E5", cloud_results)
            if not all(ok for _, ok, _ in cloud_results):
                all_ok = False

        # ---- X-MOCK-CLOUD workflow ----
        if args.workflow in ("mock-cloud", "all"):
            print("\nTesting X-Mock-Cloud header override...")
            mock_cloud_results = test_mock_cloud_header()
            print_results("X-Mock-Cloud Header Override", mock_cloud_results)
            if not all(ok for _, ok, _ in mock_cloud_results):
                all_ok = False

        # ---- EXTENDED FILTER workflow ----
        if args.workflow in ("extended-filter", "all"):
            print("\nStarting greenfield server for extended filter tests...")
            proc = start_server(ports[0], "greenfield")
            procs.append(proc)
            client = GraphClient(f"http://localhost:{ports[0]}")
            ext_filter_results = test_extended_filters(client)
            print_results("Extended $filter Operators (ne, gt, lt, startswith, contains)", ext_filter_results)
            stop_server(proc); procs.remove(proc)
            if not all(ok for _, ok, _ in ext_filter_results):
                all_ok = False

        # ---- PARTIAL SCENARIO workflow ----
        if args.workflow in ("partial", "all"):
            print("\nTesting partial (mid-deployment) scenario...")
            partial_results = test_partial_scenario()
            print_results("Partial Scenario — Mid-Deployment Posture", partial_results)
            if not all(ok for _, ok, _ in partial_results):
                all_ok = False

        # ---- AUTH EDGE CASES workflow ----
        if args.workflow in ("auth", "all"):
            print("\nTesting auth enforcement edge cases...")
            auth_results = test_auth_edge_cases()
            print_results("Auth Enforcement + Error Simulation", auth_results)
            if not all(ok for _, ok, _ in auth_results):
                all_ok = False

        # ---- EXPAND workflow ----
        if args.workflow in ("expand", "all"):
            print("\nStarting greenfield server for $expand tests...")
            proc = start_server(ports[0], "greenfield")
            procs.append(proc)
            client = GraphClient(f"http://localhost:{ports[0]}")
            expand_results = test_expand(client)
            print_results("OData $expand Inline Expansion", expand_results)
            stop_server(proc); procs.remove(proc)
            if not all(ok for _, ok, _ in expand_results):
                all_ok = False

        # ---- GCC HIGH SCENARIOS workflow ----
        if args.workflow in ("gcc-high-scenarios", "all"):
            print("\nTesting GCC High hardened and partial scenarios...")
            gcc_high_results = test_gcc_high_scenarios()
            print_results("GCC High Scenarios — Hardened + Partial", gcc_high_results)
            if not all(ok for _, ok, _ in gcc_high_results):
                all_ok = False

        # ---- BETA ENDPOINTS workflow ----
        if args.workflow in ("beta", "all"):
            print("\nStarting greenfield server for /beta/ tests...")
            proc = start_server(ports[0], "greenfield")
            procs.append(proc)
            client = GraphClient(f"http://localhost:{ports[0]}")
            beta_results = test_beta_endpoints(client)
            print_results("/beta/ Route Mirror + Context Rewriting", beta_results)
            stop_server(proc); procs.remove(proc)
            if not all(ok for _, ok, _ in beta_results):
                all_ok = False

        # ---- COMMERCIAL E5 SCENARIOS workflow ----
        if args.workflow in ("e5-scenarios", "all"):
            print("\nTesting Commercial E5 hardened and partial scenarios...")
            e5_results = test_e5_scenarios()
            print_results("Commercial E5 Scenarios — Hardened + Partial", e5_results)
            if not all(ok for _, ok, _ in e5_results):
                all_ok = False

        # ---- ENFORCED SCENARIO workflow ----
        if args.workflow in ("enforced", "all"):
            print("\nTesting hardened-enforced scenario...")
            enforced_results = test_enforced_scenario()
            print_results("Enforced Scenario — CA Policies state=enabled", enforced_results)
            if not all(ok for _, ok, _ in enforced_results):
                all_ok = False

        # ---- PRIORITY ENDPOINTS workflow ----
        if args.workflow in ("priority-endpoints", "all"):
            print("\nStarting servers for priority-1 endpoint tests...")
            proc_g = start_server(ports[0], "greenfield")
            procs.append(proc_g)
            proc_h = start_server(ports[1], "hardened")
            procs.append(proc_h)
            g_client = GraphClient(f"http://localhost:{ports[0]}")
            h_client = GraphClient(f"http://localhost:{ports[1]}")
            priority_results = test_priority_endpoints(g_client, h_client)
            print_results("Priority-1 Endpoints (Phase 23)", priority_results)
            stop_server(proc_g); procs.remove(proc_g)
            stop_server(proc_h); procs.remove(proc_h)
            if not all(ok for _, ok, _ in priority_results):
                all_ok = False

        # ---- DEFENDER API workflow ----
        if args.workflow in ("defender", "all"):
            print("\nTesting Defender for Endpoint /api/ endpoints...")
            defender_results = test_defender_api()
            print_results("Defender for Endpoint API (/api/*)", defender_results)
            if not all(ok for _, ok, _ in defender_results):
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
