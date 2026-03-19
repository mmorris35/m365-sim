# m365-sim — Development Plan

## How to Use This Plan

**For Claude Code**: Read this plan, find the subtask ID from the prompt, complete ALL checkboxes, update completion notes, commit.

**For You**: Use the executor agent to implement subtasks:
```
Use the m365-sim-executor agent to execute subtask X.Y.Z
```

---

## Project Overview

**Project Name**: m365-sim
**Goal**: A reusable Microsoft Graph API simulation platform for testing M365 compliance tools (primarily CMMC 2.0 L2 assessment workflows) against realistic tenant state without a live tenant.
**Target Users**: Compliance tool integration test suites, M365 compliance tool developers, CI/CD pipelines
**Timeline**: 1 week
**Tech Stack**: Python 3.11+, FastAPI, uvicorn, pytest, httpx

**MVP Scope**:
- [x] Phase 00 — Decision Log
- [ ] Phase 01 — Repo Bootstrap
- [ ] Phase 02 — Server Scaffold
- [ ] Phase 03 — Route Table
- [ ] Phase 04 — Greenfield Fixture Set
- [ ] Phase 05 — Smoke Tests
- [ ] Phase 06 — Hardened Fixture Set
- [ ] Phase 07 — GCC High Scaffold
- [ ] Phase 08 — TenantBuilder Fluent API

**Current**: Phase 01
**Next**: 1.1.1

---

## Lessons Learned Safeguards

### Critical
- **Deprecated FastAPI patterns**: Use `lifespan` async context manager instead of `on_event("startup")`. Use modern FastAPI patterns throughout.
- **Graph API null nested dict access**: Use `(p.get("grantControls") or {}).get("builtInControls")` pattern — `or {}` handles explicit null values that `.get(key, {})` does not.
- **TODO stubs in pipeline code**: Verification must grep for TODO/FIXME and fail if any remain in non-scaffold code.
- **Implicit instructions not repeated per-subtask**: Every subtask includes ALL required commands explicitly.

### Warnings
- **Missing git push**: Include `git push origin main` after squash merges.
- **Graph API unsupported query params**: Document which `$top`/`$filter`/`$select` params each endpoint actually supports.

---

## Phase 00: Decision Log

**Goal**: Resolve 5 open design questions before writing any code. Record decisions in `docs/decisions.md`.
**Duration**: 1 session (interactive with user)

### Task 0.1: Design Decisions

**Git**: No branch needed — this is a documentation-only phase committed directly to main.

**Subtask 0.1.1: Resolve Open Design Questions (Interactive Session)**

**Prerequisites**: None (first subtask)

This subtask requires **interactive discussion with the user**. Present each question, discuss tradeoffs, record the decision.

**Deliverables**:
- [x] Create `docs/decisions.md` with frontmatter and 5 decision records
- [x] Decision 001: Fixture loading strategy — eager vs lazy
- [x] Decision 002: `$filter` implementation depth — ignore all vs minimal engine
- [x] Decision 003: Stateful write operations — fake responses vs mutable state
- [x] Decision 004: Integration test runner — subprocess vs in-process ASGI
- [x] Decision 005: TenantBuilder timing — build in MVP vs defer

**Questions to Present to User**:

**Decision 001 — Fixture Loading: Eager vs Lazy?**
- Context: ~30 JSON files per scenario, total size probably under 500KB
- Option A: **Eager** — load all fixtures into a `dict[str, Any]` at startup. Simple, fast lookups, ~500KB memory.
- Option B: **Lazy** — load fixtures on first request, cache in memory. Slightly lower startup time, more complexity.
- Kickoff doc leans: Eager
- Recommendation: **Eager**. 500KB is negligible. Eliminates race conditions, simplifies code, and startup errors surface immediately rather than on first request.

**Decision 002 — `$filter` Implementation Depth?**
- Context: Consumers use `$filter=userType eq 'Guest'` and `$filter=accountEnabled eq false` on `/users`. Also `$filter=securityEnabled eq true` on `/groups` and `$filter=appId eq '...'` on `/servicePrincipals`.
- Option A: **Ignore all filters** — return full fixture, evaluators handle sparse results. Simplest.
- Option B: **Minimal filter engine** — parse `eq` comparisons on known fields, filter the `value` array. More realistic, catches filter-dependent bugs.
- Recommendation: **Option A for MVP, Option B as Phase 05 enhancement if needed**. Compliance evaluators already handle full result sets. Filters only matter if evaluators assume pre-filtered data.

**Decision 003 — Stateful Write Operations?**
- Context: Deploy mode POSTs CA policies and PATCHes auth method configs.
- Option A: **Stateless** — writes return fake responses, fixture state never changes. A GET after POST still returns the original fixture. Hardened scenario is a separate static fixture set.
- Option B: **Stateful** — writes mutate in-memory state, subsequent GETs reflect changes. Enables deploy-then-verify test flows.
- Kickoff doc says: Stateless for MVP
- Recommendation: **Stateless**. The hardened scenario IS the post-deploy state as a static fixture set. Stateful writes add complexity (merge logic, reset mechanism) for a test flow that isn't needed yet.

**Decision 004 — Integration Test Runner: Subprocess vs In-Process?**
- Context: Smoke tests need to start the mock server and hit endpoints.
- Option A: **Subprocess** — pytest fixture starts `uvicorn server:app` as a subprocess, tests use httpx to hit real HTTP. More realistic, tests actual server startup and HTTP handling.
- Option B: **In-process ASGI** — use `httpx.AsyncClient` with `ASGITransport(app=app)`. Faster, no port conflicts, but skips real HTTP layer.
- Kickoff doc leans: Subprocess
- Recommendation: **Subprocess for integration tests** (tests the real HTTP path consumers will use), but also include a few in-process unit tests for route logic where speed matters.

**Decision 005 — TenantBuilder: MVP or Defer?**
- Context: Fluent builder API generates fixture JSON programmatically as an alternative to hand-editing JSON files.
- Option A: **Include in MVP** — useful for generating scenario variants, enables programmatic test setup.
- Option B: **Defer to after smoke tests pass** — greenfield/hardened fixtures are hand-authored from the kickoff spec, builder adds no value until we need custom scenarios.
- Kickoff doc leans: Defer
- Recommendation: **Defer (Phase 08)**. The kickoff spec provides exact JSON for greenfield and hardened. The builder becomes valuable when we need custom scenarios for specific evaluator edge cases, which comes after the basic test infrastructure works.

**File to Create** — `docs/decisions.md`:

```markdown
# m365-sim Design Decisions

## Decision Log

Each entry records a design question, the options considered, the resolution, and the rationale.

---

### DEC-001: Fixture Loading Strategy

**Date**: 2026-03-19
**Status**: {PENDING|DECIDED}
**Question**: Should fixture JSON files be loaded eagerly at server startup or lazily on first request?

**Options**:
| Option | Pros | Cons |
|--------|------|------|
| A. Eager loading at startup | Simple dict lookup, startup errors surface immediately, no race conditions | Slightly slower startup (negligible for <500KB) |
| B. Lazy loading on first request | Marginally faster startup | Added complexity, first-request latency, potential race conditions |

**Resolution**: {A or B}
**Rationale**: {User's reasoning}

---

### DEC-002: $filter Implementation Depth

**Date**: 2026-03-19
**Status**: {PENDING|DECIDED}
**Question**: Should the mock server ignore OData $filter query parameters or implement a minimal filter engine?

**Options**:
| Option | Pros | Cons |
|--------|------|------|
| A. Ignore all filters, return full fixture | Simplest implementation, evaluators handle full results | Won't catch filter-dependent bugs |
| B. Minimal filter engine for `eq` comparisons | More realistic, catches evaluator assumptions about pre-filtered data | More code to maintain, risk of filter bugs in the mock itself |

**Resolution**: {A or B}
**Rationale**: {User's reasoning}

---

### DEC-003: Stateful Write Operations

**Date**: 2026-03-19
**Status**: {PENDING|DECIDED}
**Question**: Should POST/PATCH operations mutate in-memory fixture state, or return fake responses without changing state?

**Options**:
| Option | Pros | Cons |
|--------|------|------|
| A. Stateless — fake responses only | Simple, hardened scenario is a separate fixture set, no reset mechanism needed | Can't test deploy-then-verify flows in a single test run |
| B. Stateful — writes mutate in-memory state | Enables deploy-then-verify testing, more realistic | Merge logic complexity, needs reset mechanism, harder to reason about test state |

**Resolution**: {A or B}
**Rationale**: {User's reasoning}

---

### DEC-004: Integration Test Runner

**Date**: 2026-03-19
**Status**: {PENDING|DECIDED}
**Question**: Should smoke tests start the mock server as a subprocess (real HTTP) or use in-process ASGI transport?

**Options**:
| Option | Pros | Cons |
|--------|------|------|
| A. Subprocess (real HTTP via httpx) | Tests real server startup, actual HTTP layer consumers use, catches port/process issues | Slower, potential port conflicts, process management in fixtures |
| B. In-process ASGI transport | Fast, no port conflicts, simpler fixture setup | Skips real HTTP layer, doesn't test server startup path |
| C. Both — subprocess for integration, ASGI for unit | Best coverage, fast unit tests + realistic integration tests | Two test patterns to maintain |

**Resolution**: {A, B, or C}
**Rationale**: {User's reasoning}

---

### DEC-005: TenantBuilder Timing

**Date**: 2026-03-19
**Status**: {PENDING|DECIDED}
**Question**: Should the TenantBuilder fluent API be part of the MVP or deferred until after greenfield/hardened fixtures and smoke tests are working?

**Options**:
| Option | Pros | Cons |
|--------|------|------|
| A. Include in MVP (Phase 04-ish) | Available immediately for generating test variants | No value until basic fixtures work, delays core deliverable |
| B. Defer to Phase 08 | Focus on core value first, builder becomes useful when we need custom scenarios | Greenfield/hardened are hand-authored, could be error-prone |

**Resolution**: {A or B}
**Rationale**: {User's reasoning}
```

**Success Criteria**:
- [x] `docs/decisions.md` exists with all 5 decision records
- [x] Each decision has Status: DECIDED (not PENDING)
- [x] Each decision has a non-empty Resolution and Rationale
- [x] User has confirmed all 5 decisions

**Completion Notes**:
- **Implementation**: Interactive session with user to resolve all 5 design decisions
- **Files Created**: docs/decisions.md — 101 lines
- **Notes**: DEC-001: Eager, DEC-002: Ignore filters (curated fixtures), DEC-003: Stateless (hardened = post-deploy), DEC-004: Subprocess, DEC-005: Defer to Phase 08

**Git Commit**:
```bash
git add docs/decisions.md
git commit -m "docs(decisions): record 5 design decisions [0.1.1]"
```

---

### Task 0.1 Complete
- [x] All 5 decisions resolved and recorded
- [x] Git commit:
  ```bash
  git add docs/decisions.md
  git commit -m "docs(decisions): record 5 design decisions for m365-sim MVP [0.1.1]"
  git push origin main
  ```

---

## Phase 01: Repo Bootstrap

**Goal**: Create directory structure, install dependencies, establish project skeleton
**Duration**: 1 session

### Task 1.1: Project Structure and Dependencies

**Git**: Create branch `feature/1-1-repo-bootstrap` when starting first subtask. Commit after each subtask. Squash merge to main when task complete.

**Subtask 1.1.1: Directory Structure and Dependencies (Single Session)**

**Prerequisites**:
- [x] 0.1.1: Resolve Open Design Questions

**Git Start** (first subtask of this task):
```bash
git checkout main && git pull origin main
git checkout -b feature/1-1-repo-bootstrap
```

**Deliverables**:
- [x] Create all directories:
  ```bash
  mkdir -p scenarios/gcc-moderate/{greenfield,hardened,partial}
  mkdir -p scenarios/gcc-high/greenfield
  mkdir -p builder sdk tests docs
  ```
- [x] Create `requirements.txt`:
  ```
  fastapi>=0.115.0
  uvicorn[standard]>=0.34.0
  pytest>=8.0.0
  httpx>=0.28.0
  pytest-asyncio>=0.25.0
  ```
- [x] Create `.gitignore`:
  ```gitignore
  __pycache__/
  *.pyc
  *.pyo
  .venv/
  venv/
  .env
  *.egg-info/
  dist/
  build/
  .pytest_cache/
  .mypy_cache/
  .ruff_cache/
  *.db
  .DS_Store
  ```
- [x] Create `sdk/__init__.py`:
  ```python
  """m365-sim: Microsoft Graph API simulation platform."""
  __version__ = "0.1.0"
  ```
- [x] Create `builder/__init__.py` (empty)
- [x] Create `tests/__init__.py` (empty)
- [x] Create `README.md` stub:
  ```markdown
  # m365-sim

  Microsoft Graph API simulation platform for testing M365 compliance tools against realistic tenant state without a live tenant.

  ## Quick Start

  ```bash
  pip install -r requirements.txt
  uvicorn server:app --port 8888
  ```

  ## Usage

  ```bash
  # Start with greenfield GCC Moderate scenario (default)
  uvicorn server:app --port 8888

  # Start with hardened scenario
  python server.py --scenario hardened --port 8888

  # Start with GCC High cloud target
  python server.py --cloud gcc-high --port 8888
  ```

  ## Scenarios

  | Scenario | Description | Expected SPRS Range |
  |----------|-------------|---------------------|
  | greenfield | Fresh G5 GCC Moderate tenant, no controls | -170 to -210 |
  | hardened | Post-CMMC deploy, report-only CA policies | -40 to -80 |
  | partial | Mid-deployment state (v2) | -100 to -140 |
  ```
- [x] Create virtual environment and install dependencies:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

**Success Criteria**:
- [x] `ls scenarios/gcc-moderate/` shows `greenfield/`, `hardened/`, `partial/`
- [x] `ls scenarios/gcc-high/` shows `greenfield/`
- [x] `ls builder/ sdk/ tests/ docs/` all exist
- [x] `pip install -r requirements.txt` succeeds in venv
- [x] `python -c "import fastapi; print(fastapi.__version__)"` prints version
- [x] `python -c "from sdk import __version__; print(__version__)"` prints `0.1.0`
- [x] `.gitignore` includes `__pycache__/` and `.venv/`

**Completion Notes**:
- **Implementation**: Created complete directory structure for scenarios (gcc-moderate and gcc-high with greenfield, hardened, partial subdirs), builder, sdk, and tests packages. Created requirements.txt with FastAPI, uvicorn, pytest, httpx, and pytest-asyncio dependencies. Updated .gitignore with Python/venv/cache entries. Created sdk/__init__.py with version 0.1.0. Created empty builder/__init__.py and tests/__init__.py. Updated README.md stub with quick start, usage, and scenarios sections. Installed all dependencies in Python 3.11+ virtual environment.
- **Files Created**:
  - `requirements.txt` - 5 lines
  - `sdk/__init__.py` - 2 lines
  - `builder/__init__.py` - 0 lines (empty)
  - `tests/__init__.py` - 0 lines (empty)
  - `README.md` (updated) - 27 lines
  - Directories: `scenarios/gcc-moderate/{greenfield,hardened,partial}`, `scenarios/gcc-high/greenfield`, `builder`, `sdk`, `tests`, `docs`
- **Notes**: All success criteria verified. Virtual environment created and dependencies installed successfully (FastAPI 0.135.1, uvicorn 0.42.0, pytest 9.0.2, httpx 0.28.1, pytest-asyncio 1.3.0). SDK version confirmed as 0.1.0. .gitignore already existed with required entries.

**Git Commit**:
```bash
git add -A && git commit -m "feat(bootstrap): directory structure and dependencies [1.1.1]"
```

---

### Task 1.1 Complete — Squash Merge
- [x] All subtasks complete
- [x] All tests pass: `pytest tests/ -v`
- [x] Push feature branch: `git push -u origin feature/1-1-repo-bootstrap`
- [x] Squash merge to main:
  ```bash
  git checkout main && git pull origin main
  git merge --squash feature/1-1-repo-bootstrap
  git commit -m "feat: bootstrap repo structure, dependencies, and README"
  git push origin main
  ```
- [x] Clean up:
  ```bash
  git branch -d feature/1-1-repo-bootstrap
  git push origin --delete feature/1-1-repo-bootstrap
  ```

---

## Phase 02: Server Scaffold

**Goal**: FastAPI server with CLI args, fixture loading, auth middleware, and 404 handler
**Duration**: 1 session

### Task 2.1: Core Server

**Git**: Create branch `feature/2-1-server-scaffold` when starting first subtask.

**Subtask 2.1.1: FastAPI Server with CLI Args and Fixture Loading (Single Session)**

**Prerequisites**:
- [x] 1.1.1: Directory Structure and Dependencies

**Git Start** (first subtask of this task):
```bash
git checkout main && git pull origin main
git checkout -b feature/2-1-server-scaffold
```

**Deliverables**:
- [x] Create `server.py` with:
  - FastAPI app instance with title "m365-sim" and description
  - `lifespan` async context manager (NOT `on_event("startup")`)
  - CLI argument parsing: `--scenario` (default `greenfield`), `--cloud` (default `gcc-moderate`), `--port` (default `8888`)
  - Fixture loading at startup: glob `scenarios/{cloud}/{scenario}/*.json`, load each into `app.state.fixtures` dict keyed by filename stem
  - `X-Mock-Cloud` header override: middleware that checks for header and swaps fixture set per-request
  - Auth middleware: check for `Authorization: Bearer <token>` header, return 401 with Graph-style error JSON if missing
  - Catch-all 404 handler: return JSON `{"error": {"code": "Request_ResourceNotFound", "message": "Resource not found: {path}"}}` with warning log
  - `/health` endpoint (no auth required) returning `{"status": "healthy", "scenario": "...", "cloud": "..."}`
  - `__main__` block that parses args and starts uvicorn
- [x] Server starts with `python server.py` and `uvicorn server:app`

**Key Implementation Notes**:
- Use `argparse` for CLI args, store in module-level variables that `lifespan` reads
- `app.state.fixtures` is a `dict[str, dict]` — keys are fixture file stems (e.g., `"users"`, `"organization"`)
- Auth middleware must skip `/health` endpoint
- 404 handler logs: `logger.warning(f"Unmapped path requested: {method} {path}")`
- Error simulation query param `mock_status` handled in middleware: if present, return that status code with appropriate Graph-style error body before route matching

**Success Criteria**:
- [x] `python server.py --help` shows `--scenario`, `--cloud`, `--port` flags
- [x] `python server.py` starts uvicorn on port 8888
- [x] `python server.py --port 9999` starts on port 9999
- [x] Server logs show fixture loading count at startup
- [x] `curl http://localhost:8888/health` returns 200 with scenario/cloud info
- [x] `curl http://localhost:8888/v1.0/users` returns 401 (no auth header)
- [x] `curl -H "Authorization: Bearer fake" http://localhost:8888/v1.0/nonexistent` returns 404 with JSON error body
- [x] `curl -H "Authorization: Bearer fake" "http://localhost:8888/v1.0/users?mock_status=429"` returns 429 with Retry-After header
- [x] No TODO/FIXME in server.py: `grep -c "TODO\|FIXME" server.py` returns 0

**Completion Notes**:
- **Implementation**: Created a production-ready FastAPI server with lifespan context manager, CLI arg parsing (--scenario, --cloud, --port), fixture loading from JSON files, auth middleware, mock_status error simulation, and comprehensive error handling.
- **Files Created**: server.py (244 lines)
- **Tests**: All manual verification tests passed:
  - CLI help shows all flags
  - Server starts on custom ports
  - /health endpoint works without auth
  - Auth middleware enforces Authorization header (401 if missing)
  - 404 handler returns proper Graph API error format
  - mock_status=429 includes Retry-After header
  - Scenario and cloud parameters correctly reflected in /health response
- **Notes**: Server is ready for fixture integration and route implementation in Phase 03

**Git Commit**:
```bash
git add -A && git commit -m "feat(server): FastAPI scaffold with CLI args and fixture loading [2.1.1]"
```

---

### Task 2.1 Complete — Squash Merge
- [x] All subtasks complete
- [x] All tests pass: `pytest tests/ -v`
- [x] Push feature branch: `git push -u origin feature/2-1-server-scaffold`
- [x] Squash merge to main:
  ```bash
  git checkout main && git pull origin main
  git merge --squash feature/2-1-server-scaffold
  git commit -m "feat: FastAPI server scaffold with CLI args, auth, and fixture loading"
  git push origin main
  ```
- [x] Clean up:
  ```bash
  git branch -d feature/2-1-server-scaffold
  git push origin --delete feature/2-1-server-scaffold
  ```

---

## Phase 03: Route Table

**Goal**: Map all Graph API endpoints to fixture files, implement query param handling and write stubs
**Duration**: 1-2 sessions

### Task 3.1: GET Endpoint Routes

**Git**: Create branch `feature/3-1-route-table` when starting first subtask.

**Subtask 3.1.1: Identity and User Endpoints (Single Session)**

**Prerequisites**:
- [x] 2.1.1: FastAPI Server with CLI Args and Fixture Loading

**Git Start** (first subtask of this task):
```bash
git checkout main && git pull origin main
git checkout -b feature/3-1-route-table
```

**Deliverables**:
- [ ] Add routes to `server.py` for:
  - `GET /v1.0/users` → `fixtures["users"]`
  - `GET /v1.0/me` → `fixtures["me"]`
  - `GET /v1.0/me/authentication/methods` → `fixtures["me_auth_methods"]`
  - `GET /v1.0/users/{user_id}/authentication/methods` → `fixtures["me_auth_methods"]`
  - `GET /v1.0/organization` → `fixtures["organization"]`
  - `GET /v1.0/domains` → `fixtures["domains"]`
  - `GET /v1.0/groups` → `fixtures["groups"]`
  - `GET /v1.0/applications` → `fixtures["applications"]`
  - `GET /v1.0/servicePrincipals` → `fixtures["service_principals"]`
- [ ] Implement `$top=N` query parameter: if fixture has `value` array, truncate to N items
- [ ] Log `$filter`, `$select`, `$expand` params when present (do not apply them)

**Implementation Pattern**:
```python
def get_fixture(name: str, request: Request, top: int | None = None) -> JSONResponse:
    """Return fixture data with optional $top truncation."""
    cloud = request.headers.get("X-Mock-Cloud") or app.state.default_cloud
    fixtures = app.state.fixtures.get(cloud, app.state.fixtures[app.state.default_cloud])
    data = fixtures.get(name)
    if data is None:
        return JSONResponse(status_code=404, content={"error": {"code": "Request_ResourceNotFound", "message": f"Fixture not found: {name}"}})

    # Log ignored query params
    for param in ("$filter", "$select", "$expand"):
        if param.lstrip("$") in request.query_params or param in request.query_params:
            logger.info(f"Ignoring query param {param}={request.query_params.get(param.lstrip('$'), request.query_params.get(param))}")

    result = dict(data)  # shallow copy
    if top is not None and "value" in result:
        result["value"] = result["value"][:top]
    return JSONResponse(content=result)
```

**Success Criteria**:
- [ ] All 9 endpoints return fixture data with `Authorization: Bearer fake` header
- [ ] `$top=1` on `/v1.0/users` returns only 1 user in `value` array
- [ ] Requests with `$filter` param are logged but return full fixture

**Git Commit**:
```bash
git add -A && git commit -m "feat(routes): identity and user endpoints [3.1.1]"
```

---

**Subtask 3.1.2: Security, Devices, and Conditional Access Endpoints (Single Session)**

**Prerequisites**:
- [x] 3.1.1: Identity and User Endpoints

**Deliverables**:
- [ ] Add routes for:
  - `GET /v1.0/devices` → `fixtures["devices"]`
  - `GET /v1.0/deviceManagement/managedDevices` → `fixtures["managed_devices"]`
  - `GET /v1.0/deviceManagement/deviceCompliancePolicies` → `fixtures["compliance_policies"]`
  - `GET /v1.0/deviceManagement/deviceConfigurations` → `fixtures["device_configurations"]`
  - `GET /v1.0/deviceManagement/deviceEnrollmentConfigurations` → `fixtures["device_enrollment_configurations"]`
  - `GET /v1.0/identity/conditionalAccess/policies` → `fixtures["conditional_access_policies"]`
  - `GET /v1.0/identity/conditionalAccess/namedLocations` → `fixtures["named_locations"]`
  - `GET /v1.0/security/incidents` → `fixtures["security_incidents"]`
  - `GET /v1.0/security/alerts_v2` → `fixtures["security_alerts"]`
  - `GET /v1.0/security/secureScores` → `fixtures["secure_scores"]`
  - `GET /v1.0/security/secureScoreControlProfiles` → `fixtures["secure_score_control_profiles"]`

**Success Criteria**:
- [ ] All 11 endpoints return fixture data
- [ ] `$top=1` works on security/secureScores

**Git Commit**:
```bash
git add -A && git commit -m "feat(routes): security, devices, and CA endpoints [3.1.2]"
```

---

**Subtask 3.1.3: Roles, Auth Methods Policy, Audit Logs, and Info Protection Endpoints (Single Session)**

**Prerequisites**:
- [x] 3.1.2: Security, Devices, and Conditional Access Endpoints

**Deliverables**:
- [ ] Add routes for:
  - `GET /v1.0/directoryRoles` → `fixtures["directory_roles"]`
  - `GET /v1.0/directoryRoles/{role_id}/members` → `fixtures["directory_role_members"]`
  - `GET /v1.0/roleManagement/directory/roleAssignments` → `fixtures["role_assignments"]`
  - `GET /v1.0/roleManagement/directory/roleDefinitions` → `fixtures["role_definitions"]`
  - `GET /v1.0/roleManagement/directory/roleEligibilitySchedules` → `fixtures["role_eligibility_schedules"]`
  - `GET /v1.0/roleManagement/directory/roleAssignmentSchedules` → `fixtures["role_assignment_schedules"]`
  - `GET /v1.0/policies/authenticationMethodsPolicy` → `fixtures["auth_methods_policy"]`
  - `GET /v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id}` → extract from `auth_methods_policy` fixture by matching `id` field
  - `GET /v1.0/auditLogs/signIns` → `fixtures["audit_sign_ins"]`
  - `GET /v1.0/auditLogs/directoryAudits` → `fixtures["audit_directory"]`
  - `GET /v1.0/informationProtection/policy/labels` → `fixtures["information_protection_labels"]`

**Implementation Note for auth method sub-paths**: Consumers query specific auth method configurations like `/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/microsoftAuthenticator`. The route should look up the method by `id` in the `authenticationMethodConfigurations` array within the `auth_methods_policy` fixture and return just that object.

**Success Criteria**:
- [ ] All 11 endpoints return fixture data
- [ ] `/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/fido2` returns only the FIDO2 config object
- [ ] `$top=10` on `/auditLogs/signIns` truncates results

**Git Commit**:
```bash
git add -A && git commit -m "feat(routes): roles, auth policy, audit, and info protection endpoints [3.1.3]"
```

---

### Task 3.2: Write Operation Stubs

**Git**: Continue on `feature/3-1-route-table` branch.

**Subtask 3.2.1: POST and PATCH Stubs (Single Session)**

**Prerequisites**:
- [x] 3.1.3: Roles, Auth Methods Policy, Audit Logs, and Info Protection Endpoints

**Deliverables**:
- [ ] Add write routes to `server.py`:
  - `POST /v1.0/identity/conditionalAccess/policies` → 201, return request body with added `"id": "<uuid>"` and `"createdDateTime": "<now ISO>"`
  - `PATCH /v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id}` → 200, return request body unchanged
  - `POST /v1.0/deviceManagement/deviceCompliancePolicies` → 201, return request body with added `"id": "<uuid>"` and `"createdDateTime": "<now ISO>"`
  - `POST /v1.0/deviceManagement/deviceConfigurations` → 201, return request body with added `"id": "<uuid>"` and `"createdDateTime": "<now ISO>"`
- [ ] Log all write operations: `logger.info(f"WRITE: {method} {path} — {summary}")`
- [ ] Error simulation via `?mock_status=N` applies to write endpoints too

**Success Criteria**:
- [ ] POST to CA policies returns 201 with `id` and `createdDateTime` in response
- [ ] PATCH to auth method config returns 200
- [ ] Write operations are logged with method, path, and body summary
- [ ] `?mock_status=403` on a POST returns 403

**Git Commit**:
```bash
git add -A && git commit -m "feat(routes): POST and PATCH write stubs [3.2.1]"
```

---

### Task 3.2 Complete — Squash Merge
- [ ] All subtasks complete (3.1.1 through 3.2.1)
- [ ] All tests pass: `pytest tests/ -v`
- [ ] Push feature branch: `git push -u origin feature/3-1-route-table`
- [ ] Squash merge to main:
  ```bash
  git checkout main && git pull origin main
  git merge --squash feature/3-1-route-table
  git commit -m "feat: complete route table with all GET endpoints, write stubs, and query param handling"
  git push origin main
  ```
- [ ] Clean up:
  ```bash
  git branch -d feature/3-1-route-table
  git push origin --delete feature/3-1-route-table
  ```

---

## Phase 04: Greenfield Fixture Set

**Goal**: Create all JSON fixture files representing a fresh G5 GCC Moderate tenant
**Duration**: 1-2 sessions

### Task 4.1: Core Fixtures

**Git**: Create branch `feature/4-1-greenfield-fixtures` when starting first subtask.

**Subtask 4.1.1: Organization, Users, and Identity Fixtures (Single Session)**

**Prerequisites**:
- [x] 3.2.1: POST and PATCH Stubs

**Git Start** (first subtask of this task):
```bash
git checkout main && git pull origin main
git checkout -b feature/4-1-greenfield-fixtures
```

**Deliverables**:
- [ ] Create `scenarios/gcc-moderate/greenfield/organization.json` — Contoso Defense LLC with G5 assigned plans (exchange, MDE, SCO, AADPremium), per kickoff spec
- [ ] Create `scenarios/gcc-moderate/greenfield/users.json` — Mike Morris (GA) + BreakGlass Admin, per kickoff spec
- [ ] Create `scenarios/gcc-moderate/greenfield/me.json` — Mike Morris entity, per kickoff spec
- [ ] Create `scenarios/gcc-moderate/greenfield/me_auth_methods.json` — Authenticator + password (no FIDO2), per kickoff spec
- [ ] Create `scenarios/gcc-moderate/greenfield/domains.json` — contoso-defense.com + onmicrosoft.com, per kickoff spec
- [ ] Create `scenarios/gcc-moderate/greenfield/groups.json` — empty value array

All fixtures must include `@odata.context` fields matching real Graph API responses.

**Success Criteria**:
- [ ] Each JSON file is valid JSON: `python -m json.tool < file.json`
- [ ] `organization.json` has `assignedPlans` with 4 service plans
- [ ] `users.json` has exactly 2 users
- [ ] `me_auth_methods.json` has Authenticator + password (no FIDO2)
- [ ] Server starts and serves these fixtures: `python server.py` then `curl -H "Authorization: Bearer x" http://localhost:8888/v1.0/users`

**Git Commit**:
```bash
git add -A && git commit -m "feat(fixtures): organization, users, and identity fixtures [4.1.1]"
```

---

**Subtask 4.1.2: Security, Audit, and Empty Fixtures (Single Session)**

**Prerequisites**:
- [x] 4.1.1: Organization, Users, and Identity Fixtures

**Deliverables**:
- [ ] Create `scenarios/gcc-moderate/greenfield/conditional_access_policies.json` — empty value array
- [ ] Create `scenarios/gcc-moderate/greenfield/auth_methods_policy.json` — all methods disabled (fido2, microsoftAuthenticator, temporaryAccessPass, sms), per kickoff spec
- [ ] Create `scenarios/gcc-moderate/greenfield/managed_devices.json` — empty value array
- [ ] Create `scenarios/gcc-moderate/greenfield/compliance_policies.json` — empty value array
- [ ] Create `scenarios/gcc-moderate/greenfield/device_configurations.json` — empty value array
- [ ] Create `scenarios/gcc-moderate/greenfield/device_enrollment_configurations.json` — empty value array
- [ ] Create `scenarios/gcc-moderate/greenfield/secure_scores.json` — per kickoff spec (currentScore 12.0, maxScore 198.0)
- [ ] Create `scenarios/gcc-moderate/greenfield/audit_sign_ins.json` — one setup sign-in entry, per kickoff spec
- [ ] Create `scenarios/gcc-moderate/greenfield/audit_directory.json` — empty value array
- [ ] Create `scenarios/gcc-moderate/greenfield/security_incidents.json` — empty value array
- [ ] Create `scenarios/gcc-moderate/greenfield/security_alerts.json` — empty value array
- [ ] Create `scenarios/gcc-moderate/greenfield/information_protection_labels.json` — empty value array
- [ ] Create `scenarios/gcc-moderate/greenfield/named_locations.json` — empty value array
- [ ] Create `scenarios/gcc-moderate/greenfield/secure_score_control_profiles.json` — empty value array with proper `@odata.context`

**Success Criteria**:
- [ ] All 14 JSON files are valid JSON
- [ ] `secure_scores.json` shows `currentScore: 12.0` and `maxScore: 198.0`
- [ ] `auth_methods_policy.json` has 4 auth method configurations all with `state: "disabled"`
- [ ] `audit_sign_ins.json` has exactly 1 sign-in entry

**Git Commit**:
```bash
git add -A && git commit -m "feat(fixtures): security, audit, and empty fixtures [4.1.2]"
```

---

**Subtask 4.1.3: Roles, Applications, and Service Principals Fixtures (Single Session)**

**Prerequisites**:
- [x] 4.1.2: Security, Audit, and Empty Fixtures

**Deliverables**:
- [ ] Create `scenarios/gcc-moderate/greenfield/directory_roles.json` — Global Administrator, Security Administrator, Compliance Administrator, Global Reader + other standard built-in roles (User Administrator, Exchange Administrator, SharePoint Administrator, Teams Administrator, Intune Administrator, Cloud Application Administrator, Privileged Role Administrator, Conditional Access Administrator, Security Reader, Helpdesk Administrator)
- [ ] Create `scenarios/gcc-moderate/greenfield/directory_role_members.json` — GA role members: Mike Morris
- [ ] Create `scenarios/gcc-moderate/greenfield/role_assignments.json` — Mike Morris assigned to Global Administrator, per kickoff spec
- [ ] Create `scenarios/gcc-moderate/greenfield/role_definitions.json` — standard built-in role definitions with proper `roleTemplateId` values
- [ ] Create `scenarios/gcc-moderate/greenfield/role_eligibility_schedules.json` — empty value array
- [ ] Create `scenarios/gcc-moderate/greenfield/role_assignment_schedules.json` — empty value array
- [ ] Create `scenarios/gcc-moderate/greenfield/applications.json` — empty value array (no custom apps on fresh tenant)
- [ ] Create `scenarios/gcc-moderate/greenfield/service_principals.json` — Microsoft Graph SP (`appId: "00000003-0000-0000-c000-000000000000"`) plus common pre-populated SPs (Office 365 Exchange Online, SharePoint Online, Microsoft Teams, Windows Azure Active Directory)
- [ ] Create `scenarios/gcc-moderate/greenfield/devices.json` — empty value array

**Success Criteria**:
- [ ] `directory_roles.json` has at least 10 built-in roles
- [ ] `role_assignments.json` assigns Mike Morris to Global Administrator role
- [ ] `service_principals.json` includes Microsoft Graph SP with correct appId
- [ ] Server starts and all endpoints return data: quick smoke test hitting each new endpoint

**Git Commit**:
```bash
git add -A && git commit -m "feat(fixtures): roles, applications, and service principals [4.1.3]"
```

---

### Task 4.1 Complete — Squash Merge
- [ ] All subtasks complete (4.1.1 through 4.1.3)
- [ ] All ~27 fixture files created in `scenarios/gcc-moderate/greenfield/`
- [ ] `ls scenarios/gcc-moderate/greenfield/*.json | wc -l` shows correct count
- [ ] All tests pass: `pytest tests/ -v`
- [ ] Push feature branch: `git push -u origin feature/4-1-greenfield-fixtures`
- [ ] Squash merge to main:
  ```bash
  git checkout main && git pull origin main
  git merge --squash feature/4-1-greenfield-fixtures
  git commit -m "feat: complete greenfield GCC Moderate fixture set"
  git push origin main
  ```
- [ ] Clean up:
  ```bash
  git branch -d feature/4-1-greenfield-fixtures
  git push origin --delete feature/4-1-greenfield-fixtures
  ```

---

## Phase 05: Smoke Tests

**Goal**: Comprehensive test suite verifying all endpoints, auth, query params, write stubs, and error simulation
**Duration**: 1 session

### Task 5.1: Test Suite

**Git**: Create branch `feature/5-1-smoke-tests` when starting first subtask.

**Subtask 5.1.1: Server Subprocess Fixture and GET Endpoint Tests (Single Session)**

**Prerequisites**:
- [x] 4.1.3: Roles, Applications, and Service Principals Fixtures

**Git Start** (first subtask of this task):
```bash
git checkout main && git pull origin main
git checkout -b feature/5-1-smoke-tests
```

**Deliverables**:
- [ ] Create `tests/conftest.py` with:
  - `mock_server` pytest fixture (session-scoped) that:
    - Picks a random available port
    - Starts `python server.py --port {port}` as a subprocess
    - Waits for `/health` to respond (retry loop, 5s timeout)
    - Yields `f"http://localhost:{port}"`
    - Kills subprocess on teardown
  - `auth_headers` fixture returning `{"Authorization": "Bearer test-token"}`
- [ ] Create `tests/test_server.py` with:
  - `test_health_no_auth_required` — GET /health returns 200 without auth
  - `test_auth_required` — GET /v1.0/users without auth returns 401
  - `test_users` — returns 200, has `value` key with 2 users
  - `test_me` — returns 200, has `displayName` key
  - `test_organization` — returns 200, has `value` with tenant info
  - `test_domains` — returns 200
  - `test_groups` — returns 200, empty `value` array
  - `test_conditional_access_policies` — returns 200, empty `value` array
  - `test_auth_methods_policy` — returns 200, has `authenticationMethodConfigurations`
  - `test_auth_method_config_by_id` — `/policies/.../fido2` returns fido2 config
  - `test_directory_roles` — returns 200, has roles in `value`
  - `test_role_assignments` — returns 200
  - `test_managed_devices` — returns 200, empty `value`
  - `test_secure_scores` — returns 200, `currentScore` is 12.0
  - `test_audit_sign_ins` — returns 200, has 1 sign-in entry
  - `test_security_incidents` — returns 200, empty `value`
  - `test_service_principals` — returns 200, includes Microsoft Graph SP
  - `test_information_protection_labels` — returns 200
  - `test_all_collection_endpoints_have_value_key` — parameterized test hitting all collection endpoints, asserting `value` key exists

**Success Criteria**:
- [ ] `pytest tests/ -v` shows all tests passing
- [ ] At least 18 test functions
- [ ] No TODO/FIXME in test files

**Git Commit**:
```bash
git add -A && git commit -m "test(smoke): subprocess fixture and GET endpoint tests [5.1.1]"
```

---

**Subtask 5.1.2: Query Param, Write, and Error Simulation Tests (Single Session)**

**Prerequisites**:
- [x] 5.1.1: Server Subprocess Fixture and GET Endpoint Tests

**Deliverables**:
- [ ] Create `tests/test_query_write_error.py` with (uses `mock_server` and `auth_headers` fixtures from conftest.py):
  - `test_top_truncation` — `GET /v1.0/directoryRoles?$top=2` returns exactly 2 roles
  - `test_top_on_empty_collection` — `$top=5` on empty collection returns empty `value`
  - `test_post_ca_policy` — POST to CA policies returns 201 with `id` and `createdDateTime`
  - `test_patch_auth_method` — PATCH to microsoftAuthenticator returns 200
  - `test_post_compliance_policy` — POST returns 201 with generated `id`
  - `test_mock_status_429` — `?mock_status=429` returns 429 with `Retry-After` header
  - `test_mock_status_403` — `?mock_status=403` returns 403 with Graph error body
  - `test_mock_status_404` — `?mock_status=404` returns 404
  - `test_unmapped_path_returns_404` — `GET /v1.0/nonexistent/path` returns 404 with path in error message
  - `test_write_operation_does_not_mutate_state` — POST a CA policy, then GET policies, verify original empty fixture unchanged

**Success Criteria**:
- [ ] `pytest tests/ -v` shows all tests passing (28+ total)
- [ ] No test uses mocks — all tests hit real HTTP via subprocess
- [ ] `grep -c "TODO\|FIXME" tests/*.py` returns 0

**Git Commit**:
```bash
git add -A && git commit -m "test(smoke): query param, write, and error simulation tests [5.1.2]"
```

---

### Task 5.1 Complete — Squash Merge
- [ ] All subtasks complete (5.1.1 and 5.1.2)
- [ ] All tests pass: `pytest tests/ -v`
- [ ] Push feature branch: `git push -u origin feature/5-1-smoke-tests`
- [ ] Squash merge to main:
  ```bash
  git checkout main && git pull origin main
  git merge --squash feature/5-1-smoke-tests
  git commit -m "test: comprehensive smoke tests for all endpoints, auth, query params, and write stubs"
  git push origin main
  ```
- [ ] Clean up:
  ```bash
  git branch -d feature/5-1-smoke-tests
  git push origin --delete feature/5-1-smoke-tests
  ```

---

## Phase 06: Hardened Fixture Set

**Goal**: Create fixture files representing a post-CMMC deployment with report-only CA policies, enrolled devices, and enabled auth methods
**Duration**: 1-2 sessions

### Task 6.1: Hardened Scenario Fixtures

**Git**: Create branch `feature/6-1-hardened-fixtures` when starting first subtask.

**Subtask 6.1.1: Hardened CA Policies and Auth Methods (Single Session)**

**Prerequisites**:
- [x] 5.1.2: Query Param, Write, and Error Simulation Tests

**Git Start** (first subtask of this task):
```bash
git checkout main && git pull origin main
git checkout -b feature/6-1-hardened-fixtures
```

**Deliverables**:
- [ ] Create `scenarios/gcc-moderate/hardened/conditional_access_policies.json` with 8 CMMC policies:
  1. CMMC-MFA-AllUsers — require MFA for all users
  2. CMMC-MFA-Admins — require phishing-resistant MFA for admin roles
  3. CMMC-Block-Legacy-Auth — block legacy authentication protocols
  4. CMMC-Compliant-Device — require compliant device for access
  5. CMMC-Approved-Apps — restrict to approved client apps
  6. CMMC-Session-Timeout — enforce session sign-in frequency
  7. CMMC-Risk-Based-Access — block high-risk sign-ins
  8. CMMC-Location-Based — restrict access by named location
  - **ALL** policies must have `"state": "enabledForReportingButNotEnforced"` (NOT `"enabled"`)
  - **ALL** policies must exclude break-glass account (`00000000-0000-0000-0000-000000000011`) in `conditions.users.excludeUsers`
  - Each policy must have realistic `grantControls`, `conditions`, and `sessionControls` matching what a CMMC remediation tool would deploy
- [ ] Create `scenarios/gcc-moderate/hardened/auth_methods_policy.json` — same structure as greenfield but with:
  - `microsoftAuthenticator`: `state: "enabled"`
  - `temporaryAccessPass`: `state: "enabled"`
  - `fido2`: `state: "enabled"`
  - `sms`: `state: "disabled"` (unchanged)
- [ ] Create `scenarios/gcc-moderate/hardened/me_auth_methods.json` — greenfield base + added FIDO2 key:
  - `@odata.type: "#microsoft.graph.fido2AuthenticationMethod"` with realistic fields

**Success Criteria**:
- [ ] `conditional_access_policies.json` has exactly 8 policies
- [ ] `grep -c "enabledForReportingButNotEnforced" scenarios/gcc-moderate/hardened/conditional_access_policies.json` returns 8
- [ ] `grep -c "00000000-0000-0000-0000-000000000011" scenarios/gcc-moderate/hardened/conditional_access_policies.json` returns 8 (break-glass excluded from each)
- [ ] No policy has `"state": "enabled"` (only `"enabledForReportingButNotEnforced"`)
- [ ] `auth_methods_policy.json` has 3 enabled + 1 disabled method
- [ ] `me_auth_methods.json` has 3 entries (Authenticator, password, FIDO2)

**Git Commit**:
```bash
git add -A && git commit -m "feat(hardened): CA policies and auth methods [6.1.1]"
```

---

**Subtask 6.1.2: Hardened Devices, Compliance, and Shared Fixtures (Single Session)**

**Prerequisites**:
- [x] 6.1.1: Hardened CA Policies and Auth Methods

**Deliverables**:
- [ ] Create `scenarios/gcc-moderate/hardened/managed_devices.json` — 3 devices:
  - Windows 11 Pro laptop, `complianceState: "compliant"`, Intune managed
  - Windows 11 Pro desktop, `complianceState: "compliant"`, Intune managed
  - iOS 17 iPhone, `complianceState: "compliant"`, Intune managed
- [ ] Create `scenarios/gcc-moderate/hardened/compliance_policies.json` — 3 policies:
  - CMMC-Windows-Compliance
  - CMMC-iOS-Compliance
  - CMMC-Android-Compliance
- [ ] Create `scenarios/gcc-moderate/hardened/device_configurations.json` — 2 configurations:
  - CMMC-ASR-Rules (Attack Surface Reduction)
  - CMMC-Defender-AV (Defender Antivirus)
- [ ] For all other fixtures not listed above: **symlink or copy from greenfield**. The hardened scenario only overrides the files that changed. Options:
  - Option A: Python symlinks (e.g., `organization.json -> ../../greenfield/organization.json`)
  - Option B: Copy files that don't change
  - Option C: Server falls back to greenfield for missing hardened fixtures
  - Recommendation: **Option C** — modify `server.py` fixture loading to load the base scenario (greenfield) first, then overlay the target scenario. This is the cleanest approach and avoids symlink/copy maintenance.
- [ ] If Option C: update `server.py` to load greenfield as base, then overlay target scenario fixtures on top

**Success Criteria**:
- [ ] `managed_devices.json` has 3 devices, all `complianceState: "compliant"`
- [ ] `compliance_policies.json` has 3 policies
- [ ] `device_configurations.json` has 2 configurations
- [ ] `python server.py --scenario hardened` starts and serves hardened fixtures
- [ ] Hardened scenario inherits greenfield fixtures for unchanged endpoints (e.g., `/users` returns same data)
- [ ] Hardened CA policies endpoint returns 8 policies

**Git Commit**:
```bash
git add -A && git commit -m "feat(hardened): devices, compliance, and shared fixtures [6.1.2]"
```

---

**Subtask 6.1.3: Hardened Scenario Smoke Tests (Single Session)**

**Prerequisites**:
- [x] 6.1.2: Hardened Devices, Compliance, and Shared Fixtures

**Deliverables**:
- [ ] Add `tests/test_hardened.py` with:
  - Separate `mock_server_hardened` fixture that starts server with `--scenario hardened`
  - `test_hardened_ca_policies_count` — 8 policies
  - `test_hardened_ca_policies_report_only` — all policies have state `enabledForReportingButNotEnforced`
  - `test_hardened_ca_policies_breakglass_excluded` — all policies exclude break-glass account
  - `test_hardened_auth_methods_enabled` — microsoftAuthenticator, fido2, temporaryAccessPass all enabled
  - `test_hardened_me_has_fido2` — me_auth_methods includes FIDO2 entry
  - `test_hardened_managed_devices` — 3 devices, all compliant
  - `test_hardened_inherits_greenfield` — `/users` returns same 2 users as greenfield
  - `test_hardened_compliance_policies` — 3 policies exist

**Success Criteria**:
- [ ] `pytest tests/test_hardened.py -v` all green
- [ ] At least 8 hardened-specific tests

**Git Commit**:
```bash
git add -A && git commit -m "test(hardened): hardened scenario smoke tests [6.1.3]"
```

---

### Task 6.1 Complete — Squash Merge
- [ ] All subtasks complete (6.1.1 through 6.1.3)
- [ ] All tests pass: `pytest tests/ -v`
- [ ] Push feature branch: `git push -u origin feature/6-1-hardened-fixtures`
- [ ] Squash merge to main:
  ```bash
  git checkout main && git pull origin main
  git merge --squash feature/6-1-hardened-fixtures
  git commit -m "feat: hardened scenario with CMMC CA policies, compliant devices, and enabled auth methods"
  git push origin main
  ```
- [ ] Clean up:
  ```bash
  git branch -d feature/6-1-hardened-fixtures
  git push origin --delete feature/6-1-hardened-fixtures
  ```

---

## Phase 07: GCC High Scaffold

**Goal**: Create directory structure and documentation for GCC High cloud target, with placeholder fixtures
**Duration**: 1 session

### Task 7.1: GCC High Structure

**Git**: Create branch `feature/7-1-gcc-high-scaffold` when starting first subtask.

**Subtask 7.1.1: GCC High Directory and Documentation (Single Session)**

**Prerequisites**:
- [x] 6.1.3: Hardened Scenario Smoke Tests

**Git Start** (first subtask of this task):
```bash
git checkout main && git pull origin main
git checkout -b feature/7-1-gcc-high-scaffold
```

**Deliverables**:
- [ ] Create `scenarios/gcc-high/greenfield/_README.md` documenting:
  - Graph base URL: `https://graph.microsoft.us/v1.0` (not `graph.microsoft.com`)
  - Auth URL: `https://login.microsoftonline.us` (not `login.microsoftonline.com`)
  - Known endpoint availability differences from commercial/GCC Moderate
  - Which fixtures are TODO and why
  - GCC High tenant characteristics (sovereign cloud, FedRAMP High, IL4/IL5)
- [ ] Create placeholder fixture files in `scenarios/gcc-high/greenfield/` — one per greenfield fixture, each containing:
  ```json
  {
    "@odata.context": "https://graph.microsoft.us/v1.0/$metadata#<resource>",
    "_TODO": "Populate with GCC High-specific fixture data",
    "value": []
  }
  ```
  Note: GCC High uses `graph.microsoft.us` in `@odata.context`, not `graph.microsoft.com`
- [ ] Verify server can start with `--cloud gcc-high`: `python server.py --cloud gcc-high`

**Success Criteria**:
- [ ] `scenarios/gcc-high/greenfield/_README.md` exists with URL documentation
- [ ] `ls scenarios/gcc-high/greenfield/*.json | wc -l` matches greenfield fixture count
- [ ] All placeholder JSON files use `graph.microsoft.us` in `@odata.context`
- [ ] `python server.py --cloud gcc-high` starts without error
- [ ] `curl -H "Authorization: Bearer x" http://localhost:8888/v1.0/users` returns placeholder data

**Git Commit**:
```bash
git add -A && git commit -m "feat(gcc-high): directory structure and documentation [7.1.1]"
```

---

### Task 7.1 Complete — Squash Merge
- [ ] All subtasks complete
- [ ] All tests pass: `pytest tests/ -v`
- [ ] Push feature branch: `git push -u origin feature/7-1-gcc-high-scaffold`
- [ ] Squash merge to main:
  ```bash
  git checkout main && git pull origin main
  git merge --squash feature/7-1-gcc-high-scaffold
  git commit -m "feat: GCC High scaffold with URL documentation and placeholder fixtures"
  git push origin main
  ```
- [ ] Clean up:
  ```bash
  git branch -d feature/7-1-gcc-high-scaffold
  git push origin --delete feature/7-1-gcc-high-scaffold
  ```

---

## Phase 08: TenantBuilder Fluent API

**Goal**: Programmatic tenant state construction as an alternative to hand-editing JSON fixture files
**Duration**: 1-2 sessions

### Task 8.1: TenantBuilder Implementation

**Git**: Create branch `feature/8-1-tenant-builder` when starting first subtask.

**Subtask 8.1.1: Core TenantBuilder Class (Single Session)**

**Prerequisites**:
- [x] 7.1.1: GCC High Directory and Documentation

**Git Start** (first subtask of this task):
```bash
git checkout main && git pull origin main
git checkout -b feature/8-1-tenant-builder
```

**Deliverables**:
- [ ] Create `builder/tenant_builder.py` with:
  - `TenantBuilder` class with fluent API methods:
    - `.with_organization(name, domain, ...)` — set org identity
    - `.with_user(display_name, upn, user_type, ...)` — add a user
    - `.with_ca_policy(display_name, state, grant_controls, conditions, ...)` — add CA policy
    - `.with_device(display_name, os, compliance_state, ...)` — add managed device
    - `.with_compliance_policy(display_name, platform, ...)` — add compliance policy
    - `.with_device_configuration(display_name, ...)` — add device config
    - `.with_auth_method_enabled(method_id, state)` — configure auth method
    - `.with_directory_role(display_name, role_template_id)` — add directory role
    - `.with_role_assignment(principal_id, role_definition_id)` — assign role
    - `.with_service_principal(display_name, app_id)` — add service principal
    - `.with_secure_score(current_score, max_score)` — set secure score
    - `.build(output_dir: Path)` — write all fixture JSON files to output directory
  - Convenience presets as class methods:
    - `TenantBuilder.greenfield_gcc_moderate()` — returns builder pre-configured with kickoff spec greenfield state
    - `TenantBuilder.hardened_gcc_moderate()` — returns builder pre-configured with hardened state
  - All generated JSON must include proper `@odata.context` fields
  - All generated UUIDs must be deterministic (seeded) for reproducibility

**Success Criteria**:
- [ ] `from builder.tenant_builder import TenantBuilder` works
- [ ] `TenantBuilder.greenfield_gcc_moderate().build(Path("/tmp/test-fixtures"))` creates fixture files
- [ ] Generated fixtures match the hand-authored greenfield fixtures in structure
- [ ] `python -m json.tool < /tmp/test-fixtures/users.json` succeeds (valid JSON)

**Git Commit**:
```bash
git add -A && git commit -m "feat(builder): core TenantBuilder class [8.1.1]"
```

---

**Subtask 8.1.2: TenantBuilder Tests (Single Session)**

**Prerequisites**:
- [x] 8.1.1: Core TenantBuilder Class

**Deliverables**:
- [ ] Create `tests/test_tenant_builder.py` with:
  - `test_greenfield_preset_creates_all_fixtures` — greenfield preset generates all expected fixture files
  - `test_hardened_preset_creates_all_fixtures` — hardened preset generates all expected fixture files
  - `test_greenfield_users_match_spec` — generated users.json matches kickoff spec
  - `test_hardened_ca_policies_report_only` — all CA policies have correct state
  - `test_custom_builder` — custom builder with `.with_user().with_ca_policy()` generates valid fixtures
  - `test_build_output_is_valid_json` — every generated file is valid JSON
  - `test_builder_is_fluent` — chained method calls return the builder instance
  - `test_generated_fixtures_loadable_by_server` — start server with `--scenario` pointing to generated fixtures, verify endpoints work

**Success Criteria**:
- [ ] `pytest tests/test_tenant_builder.py -v` all green
- [ ] At least 8 tests
- [ ] Full test suite still passes: `pytest tests/ -v`

**Git Commit**:
```bash
git add -A && git commit -m "test(builder): TenantBuilder tests [8.1.2]"
```

---

### Task 8.1 Complete — Squash Merge
- [ ] All subtasks complete (8.1.1 and 8.1.2)
- [ ] All tests pass: `pytest tests/ -v`
- [ ] Push feature branch: `git push -u origin feature/8-1-tenant-builder`
- [ ] Squash merge to main:
  ```bash
  git checkout main && git pull origin main
  git merge --squash feature/8-1-tenant-builder
  git commit -m "feat: TenantBuilder fluent API with greenfield/hardened presets"
  git push origin main
  ```
- [ ] Clean up:
  ```bash
  git branch -d feature/8-1-tenant-builder
  git push origin --delete feature/8-1-tenant-builder
  ```

---

## v2 Roadmap (Post-MVP)

The following features are planned for v2, after MVP is complete and stable.

### v2.1: OSCAL Component Definition Generation
**Status**: Deferred — implement after MVP

### v2.2: Partial Scenario
**Status**: Deferred — mid-deployment state between greenfield and hardened

### v2.3: Commercial E5 Cloud Target
**Status**: Deferred — appropriate license SKUs for commercial E5

### v2.4: Hot-Reload Fixtures
**Status**: Deferred — reload fixture files without server restart

### v2.5: Stateful Write Operations
**Status**: Deferred — writes mutate in-memory state for deploy-then-verify flows

### v2.6: Docker Packaging
**Status**: Deferred — container image for CI environments

### v2.7: Integration Test Harness
**Status**: Deferred — pytest fixture that runs a compliance assessment binary against mock server, asserts SPRS score ranges (greenfield -170 to -210, hardened -40 to -80)

---

## Git Workflow

### Branch Strategy
- **One branch per task** (e.g., `feature/3-1-route-table`)
- Subtasks are commits within the task branch
- Branch naming: `feature/{phase}-{task}-{description}`

### Commit Strategy
- One commit per subtask: `feat(scope): description`
- Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`

### Merge Strategy
- Squash merge when task is complete
- Delete feature branch after merge
- Push to remote after each merge: `git push origin main`

---

## Ready to Build

Start with Phase 00 (interactive decision log), then proceed through phases in order.

```
Use the m365-sim-executor agent to execute subtask 0.1.1
```

---

*Generated by DevPlan MCP Server — enhanced from scaffold*
