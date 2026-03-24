# m365-sim User Guide

Microsoft Graph API simulation platform for testing M365 compliance tools against realistic tenant state without a live tenant.

## Quick Start

```bash
pip install -r requirements.txt
python server.py --port 8888
```

Or with Docker:

```bash
docker build -t m365-sim .
docker run -d --name m365-sim -p 8888:8888 m365-sim
```

## Scenarios

3 scenarios per cloud target, representing different stages of CMMC 2.0 deployment:

| Scenario | Description | CA Policies | Devices | Auth Methods |
|----------|-------------|-------------|---------|--------------|
| `greenfield` | Fresh tenant, no controls deployed | 0 | 0 | All disabled |
| `partial` | Mid-deployment, some controls in place | 3 | 1 | 1 enabled |
| `hardened` | Post-remediation, full CMMC posture | 8 (report-only) | 3 compliant | FIDO2 + Authenticator + TAP |

```bash
python server.py --scenario greenfield   # default
python server.py --scenario hardened
python server.py --scenario partial
```

## Cloud Targets

| Cloud | Graph API URL | Domain | Org Name |
|-------|---------------|--------|----------|
| `gcc-moderate` | `graph.microsoft.com` | `contoso-defense.com` | Contoso Defense LLC |
| `gcc-high` | `graph.microsoft.us` | `contoso-defense.us` | Contoso Defense Federal LLC |
| `commercial-e5` | `graph.microsoft.com` | `contoso.com` | Contoso Corp |

```bash
python server.py --cloud gcc-moderate    # default
python server.py --cloud gcc-high
python server.py --cloud commercial-e5
```

All combinations work: `--cloud gcc-high --scenario hardened`

## Endpoints

50+ GET endpoints mirroring the Microsoft Graph v1.0 API, plus `/beta/` mirrors with context URL rewriting, and Defender for Endpoint API routes.

### Identity & Access
- `GET /v1.0/users`
- `GET /v1.0/me`
- `GET /v1.0/me/authentication/methods`
- `GET /v1.0/users/{id}/authentication/methods`
- `GET /v1.0/organization`
- `GET /v1.0/domains`
- `GET /v1.0/groups`
- `GET /v1.0/applications`
- `GET /v1.0/servicePrincipals`

### Conditional Access
- `GET /v1.0/identity/conditionalAccess/policies`
- `GET /v1.0/identity/conditionalAccess/namedLocations`

### Policies
- `GET /v1.0/policies/authenticationMethodsPolicy`
- `GET /v1.0/policies/.../authenticationMethodConfigurations/{methodId}`
- `GET /v1.0/policies/authorizationPolicy`
- `GET /v1.0/policies/identitySecurityDefaultsEnforcementPolicy`

### Device Management
- `GET /v1.0/devices`
- `GET /v1.0/deviceManagement/managedDevices`
- `GET /v1.0/deviceManagement/deviceCompliancePolicies`
- `GET /v1.0/deviceManagement/deviceConfigurations`
- `GET /v1.0/deviceManagement/deviceEnrollmentConfigurations`
- `GET /v1.0/deviceManagement/detectedApps`
- `GET /v1.0/deviceAppManagement/managedAppPolicies`
- `GET /v1.0/deviceAppManagement/mobileApps`

### Directory Roles & RBAC
- `GET /v1.0/directoryRoles`
- `GET /v1.0/directoryRoles/{id}/members`
- `GET /v1.0/roleManagement/directory/roleAssignments`
- `GET /v1.0/roleManagement/directory/roleDefinitions`
- `GET /v1.0/roleManagement/directory/roleEligibilitySchedules`
- `GET /v1.0/roleManagement/directory/roleAssignmentSchedules`

### Security & Audit
- `GET /v1.0/auditLogs/signIns`
- `GET /v1.0/auditLogs/directoryAudits`
- `GET /v1.0/auditLogs/provisioning`
- `GET /v1.0/security/incidents`
- `GET /v1.0/security/alerts`
- `GET /v1.0/security/alerts_v2`
- `GET /v1.0/security/secureScores`
- `GET /v1.0/security/secureScoreControlProfiles`

### Information Protection & Compliance
- `GET /v1.0/informationProtection/policy/labels`
- `GET /v1.0/security/informationProtection/sensitivityLabels`

### Licensing & Governance
- `GET /v1.0/subscribedSkus`
- `GET /v1.0/reports/authenticationMethods/usersRegisteredByMethod`
- `GET /v1.0/identityGovernance/accessReviews/definitions`

### SharePoint & Admin
- `GET /v1.0/admin/sharepoint/settings`

### Defender for Endpoint (`/api/`)
- `GET /api/alerts`
- `GET /api/apps`
- `GET /api/deviceavinfo`
- `GET /api/machines/{id}/recommendations`
- `GET /api/machines/{id}/vulnerabilities`
- `GET /api/policies/appcontrol`
- `GET /api/vulnerabilities/machinesVulnerabilities`

### Write Operations
- `POST /v1.0/identity/conditionalAccess/policies` → 201
- `PATCH /v1.0/policies/.../authenticationMethodConfigurations/{methodId}` → 200
- `POST /v1.0/deviceManagement/deviceCompliancePolicies` → 201
- `POST /v1.0/deviceManagement/deviceConfigurations` → 201

### Beta API
All v1.0 endpoints above are also available under `/beta/` with `@odata.context` URLs rewritten from `v1.0` to `beta`. Some endpoints have beta-specific fixtures with additional data (e.g., `attackSimulation/simulations`, `attackSimulation/simulationAutomations`).

## Query Parameters

| Parameter | Behavior |
|-----------|----------|
| `$top=N` | Truncates `value` array to N items |
| `$filter=expr` | Filters collections. Supports: `eq`, `ne`, `gt`, `lt`, `ge`, `le`, `startswith()`, `contains()`, `in`, `and`, `or` |
| `$expand=field` | Inlines related resources. Supports: `memberOf`, `authentication` (on users/me), `members` (on directoryRoles), `*` wildcard |
| `$select` | Logged but ignored (full objects always returned) |

## Authentication

The server accepts any `Authorization: Bearer <token>` header. The token value is not validated. Requests without a Bearer header return 401.

```bash
curl -H "Authorization: Bearer anything" http://localhost:8888/v1.0/users
```

## Error Simulation

Append `?mock_status=<code>` to any endpoint to simulate Graph API errors:

```bash
curl -H "Authorization: Bearer x" "http://localhost:8888/v1.0/users?mock_status=429"
# Returns 429 with Retry-After: 1 header

curl -H "Authorization: Bearer x" "http://localhost:8888/v1.0/users?mock_status=403"
# Returns 403 with Graph-style error body
```

## Stateful Mode

By default, writes are stateless (POST/PATCH return success but don't mutate fixtures). For deploy-then-verify flows:

```bash
python server.py --stateful --port 8888
```

In stateful mode:
- POST creates resources visible on subsequent GET
- PATCH mutates fixture state in memory
- `POST /v1.0/_reset` restores the original fixture state

## Runtime Overrides

- **X-Mock-Cloud header**: Switch cloud target per-request without restarting: `X-Mock-Cloud: gcc-high`
- **Hot reload**: `POST /v1.0/_reload` reloads fixtures from disk
- **Watch mode**: `--watch` flag auto-reloads fixtures when files change on disk

## Docker Compose

```bash
# Greenfield on :8888
docker compose up -d

# Also hardened on :8889
M365_SIM_SCENARIO=hardened docker compose --profile hardened up -d
```

## Health Check

```bash
curl http://localhost:8888/health
# {"status":"healthy","scenario":"greenfield","cloud":"gcc-moderate","watch":false}
```
