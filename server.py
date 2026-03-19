#!/usr/bin/env python3
"""
m365-sim: Microsoft Graph API simulation server.

A single-file FastAPI server that serves static JSON fixtures representing
M365 tenant states. Supports CLI args for scenario/cloud/port selection,
fixture loading, auth middleware, and error simulation.
"""

import argparse
import asyncio
import json
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# Module-level variables populated by CLI args
SCENARIO = "greenfield"
CLOUD = "gcc-moderate"
PORT = 8888


def load_fixtures(cloud: str, scenario: str) -> dict[str, dict]:
    """Load all JSON fixtures from scenarios/{cloud}/{scenario}/*.json."""
    fixtures: dict[str, dict] = {}
    scenario_dir = Path(__file__).parent / "scenarios" / cloud / scenario

    if not scenario_dir.exists():
        logger.warning(f"Scenario directory not found: {scenario_dir}")
        return fixtures

    json_files = sorted(scenario_dir.glob("*.json"))
    for json_file in json_files:
        try:
            with open(json_file, "r") as f:
                fixture_data = json.load(f)
            # Key by filename stem (e.g., "users.json" -> "users")
            stem = json_file.stem
            fixtures[stem] = fixture_data
            logger.info(f"Loaded fixture: {stem}")
        except Exception as e:
            logger.error(f"Failed to load fixture {json_file}: {e}")

    logger.info(f"Loaded {len(fixtures)} fixtures for {cloud}/{scenario}")
    return fixtures


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup/shutdown."""
    # Startup: load fixtures
    fixtures = load_fixtures(CLOUD, SCENARIO)
    app.state.fixtures = fixtures
    app.state.cloud = CLOUD
    app.state.scenario = SCENARIO
    logger.info(f"Server starting with scenario={SCENARIO}, cloud={CLOUD}")

    yield

    # Shutdown
    logger.info("Server shutting down")


# Create FastAPI app
app = FastAPI(
    title="m365-sim",
    description="Microsoft Graph API simulation platform for CMMC 2.0 compliance assessment",
    version="1.0.0",
    lifespan=lifespan,
)


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to check for Authorization: Bearer token header.

    Skips /health endpoint.
    Returns 401 if Authorization header is missing.
    """

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health endpoint
        if request.url.path == "/health":
            return await call_next(request)

        # Check for Authorization header
        auth_header = request.headers.get("authorization")
        if not auth_header:
            return JSONResponse(
                status_code=401,
                content={
                    "error": {
                        "code": "Authorization_RequestDenied",
                        "message": "Authorization header missing or invalid",
                    }
                },
            )

        return await call_next(request)


class MockStatusMiddleware(BaseHTTPMiddleware):
    """Middleware to handle mock_status query param for error simulation.

    If mock_status query param is present, return that status code with
    appropriate Graph-style error body before route matching.
    """

    async def dispatch(self, request: Request, call_next):
        mock_status_str = request.query_params.get("mock_status")
        if not mock_status_str:
            return await call_next(request)

        try:
            status_code = int(mock_status_str)
        except ValueError:
            return await call_next(request)

        # Build error response based on status code
        error_code = "Request_InternalServerError"
        message = "Internal server error"

        if status_code == 429:
            error_code = "Request_Throttled"
            message = "The request was throttled"
        elif status_code == 400:
            error_code = "Request_BadRequest"
            message = "Bad request"
        elif status_code == 404:
            error_code = "Request_ResourceNotFound"
            message = "Resource not found"
        elif status_code == 403:
            error_code = "Authorization_RequestDenied"
            message = "Access denied"

        response = JSONResponse(
            status_code=status_code,
            content={
                "error": {
                    "code": error_code,
                    "message": message,
                }
            },
        )

        # Add Retry-After header for 429
        if status_code == 429:
            response.headers["Retry-After"] = "60"

        return response


# Add middleware (order matters: execute in reverse order of addition)
app.add_middleware(MockStatusMiddleware)
app.add_middleware(AuthMiddleware)


def get_fixture(name: str, request: Request, top: int | None = None) -> JSONResponse:
    """Return fixture data with optional $top truncation.

    Logs $filter, $select, $expand params if present (does not apply them).
    """
    cloud = request.headers.get("X-Mock-Cloud") or app.state.cloud
    fixtures = app.state.fixtures.get(cloud, app.state.fixtures.get(app.state.cloud, {}))
    data = fixtures.get(name)

    if data is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "Request_ResourceNotFound",
                    "message": f"Fixture not found: {name}",
                }
            },
        )

    # Log ignored query params
    for param in ("filter", "select", "expand"):
        if param in request.query_params:
            logger.info(f"Ignoring query param ${param}={request.query_params.get(param)}")

    result = dict(data)  # shallow copy
    if top is not None and "value" in result:
        result["value"] = result["value"][:top]

    return JSONResponse(content=result)


@app.get("/health")
async def health():
    """Health check endpoint (no auth required)."""
    return {
        "status": "healthy",
        "scenario": app.state.scenario,
        "cloud": app.state.cloud,
    }


# Subtask 3.1.1: Identity and User Endpoints
@app.get("/v1.0/users")
async def get_users(request: Request, top: int | None = None):
    """GET /v1.0/users — return users fixture."""
    return get_fixture("users", request, top)


@app.get("/v1.0/me")
async def get_me(request: Request):
    """GET /v1.0/me — return me fixture."""
    return get_fixture("me", request)


@app.get("/v1.0/me/authentication/methods")
async def get_me_auth_methods(request: Request, top: int | None = None):
    """GET /v1.0/me/authentication/methods — return me_auth_methods fixture."""
    return get_fixture("me_auth_methods", request, top)


@app.get("/v1.0/users/{user_id}/authentication/methods")
async def get_user_auth_methods(user_id: str, request: Request, top: int | None = None):
    """GET /v1.0/users/{user_id}/authentication/methods — return me_auth_methods fixture."""
    return get_fixture("me_auth_methods", request, top)


@app.get("/v1.0/organization")
async def get_organization(request: Request):
    """GET /v1.0/organization — return organization fixture."""
    return get_fixture("organization", request)


@app.get("/v1.0/domains")
async def get_domains(request: Request, top: int | None = None):
    """GET /v1.0/domains — return domains fixture."""
    return get_fixture("domains", request, top)


@app.get("/v1.0/groups")
async def get_groups(request: Request, top: int | None = None):
    """GET /v1.0/groups — return groups fixture."""
    return get_fixture("groups", request, top)


@app.get("/v1.0/applications")
async def get_applications(request: Request, top: int | None = None):
    """GET /v1.0/applications — return applications fixture."""
    return get_fixture("applications", request, top)


@app.get("/v1.0/servicePrincipals")
async def get_service_principals(request: Request, top: int | None = None):
    """GET /v1.0/servicePrincipals — return service_principals fixture."""
    return get_fixture("service_principals", request, top)


# Subtask 3.1.2: Security, Devices, and Conditional Access Endpoints
@app.get("/v1.0/devices")
async def get_devices(request: Request, top: int | None = None):
    """GET /v1.0/devices — return devices fixture."""
    return get_fixture("devices", request, top)


@app.get("/v1.0/deviceManagement/managedDevices")
async def get_managed_devices(request: Request, top: int | None = None):
    """GET /v1.0/deviceManagement/managedDevices — return managed_devices fixture."""
    return get_fixture("managed_devices", request, top)


@app.get("/v1.0/deviceManagement/deviceCompliancePolicies")
async def get_compliance_policies(request: Request, top: int | None = None):
    """GET /v1.0/deviceManagement/deviceCompliancePolicies — return compliance_policies fixture."""
    return get_fixture("compliance_policies", request, top)


@app.get("/v1.0/deviceManagement/deviceConfigurations")
async def get_device_configurations(request: Request, top: int | None = None):
    """GET /v1.0/deviceManagement/deviceConfigurations — return device_configurations fixture."""
    return get_fixture("device_configurations", request, top)


@app.get("/v1.0/deviceManagement/deviceEnrollmentConfigurations")
async def get_enrollment_configurations(request: Request, top: int | None = None):
    """GET /v1.0/deviceManagement/deviceEnrollmentConfigurations — return device_enrollment_configurations fixture."""
    return get_fixture("device_enrollment_configurations", request, top)


@app.get("/v1.0/identity/conditionalAccess/policies")
async def get_ca_policies(request: Request, top: int | None = None):
    """GET /v1.0/identity/conditionalAccess/policies — return conditional_access_policies fixture."""
    return get_fixture("conditional_access_policies", request, top)


@app.get("/v1.0/identity/conditionalAccess/namedLocations")
async def get_named_locations(request: Request, top: int | None = None):
    """GET /v1.0/identity/conditionalAccess/namedLocations — return named_locations fixture."""
    return get_fixture("named_locations", request, top)


@app.get("/v1.0/security/incidents")
async def get_security_incidents(request: Request, top: int | None = None):
    """GET /v1.0/security/incidents — return security_incidents fixture."""
    return get_fixture("security_incidents", request, top)


@app.get("/v1.0/security/alerts_v2")
async def get_security_alerts(request: Request, top: int | None = None):
    """GET /v1.0/security/alerts_v2 — return security_alerts fixture."""
    return get_fixture("security_alerts", request, top)


@app.get("/v1.0/security/secureScores")
async def get_secure_scores(request: Request, top: int | None = None):
    """GET /v1.0/security/secureScores — return secure_scores fixture."""
    return get_fixture("secure_scores", request, top)


@app.get("/v1.0/security/secureScoreControlProfiles")
async def get_score_control_profiles(request: Request, top: int | None = None):
    """GET /v1.0/security/secureScoreControlProfiles — return secure_score_control_profiles fixture."""
    return get_fixture("secure_score_control_profiles", request, top)


# Subtask 3.1.3: Roles, Auth Methods Policy, Audit Logs, and Info Protection Endpoints
@app.get("/v1.0/directoryRoles")
async def get_directory_roles(request: Request, top: int | None = None):
    """GET /v1.0/directoryRoles — return directory_roles fixture."""
    return get_fixture("directory_roles", request, top)


@app.get("/v1.0/directoryRoles/{role_id}/members")
async def get_directory_role_members(role_id: str, request: Request, top: int | None = None):
    """GET /v1.0/directoryRoles/{role_id}/members — return directory_role_members fixture."""
    return get_fixture("directory_role_members", request, top)


@app.get("/v1.0/roleManagement/directory/roleAssignments")
async def get_role_assignments(request: Request, top: int | None = None):
    """GET /v1.0/roleManagement/directory/roleAssignments — return role_assignments fixture."""
    return get_fixture("role_assignments", request, top)


@app.get("/v1.0/roleManagement/directory/roleDefinitions")
async def get_role_definitions(request: Request, top: int | None = None):
    """GET /v1.0/roleManagement/directory/roleDefinitions — return role_definitions fixture."""
    return get_fixture("role_definitions", request, top)


@app.get("/v1.0/roleManagement/directory/roleEligibilitySchedules")
async def get_role_eligibility_schedules(request: Request, top: int | None = None):
    """GET /v1.0/roleManagement/directory/roleEligibilitySchedules — return role_eligibility_schedules fixture."""
    return get_fixture("role_eligibility_schedules", request, top)


@app.get("/v1.0/roleManagement/directory/roleAssignmentSchedules")
async def get_role_assignment_schedules(request: Request, top: int | None = None):
    """GET /v1.0/roleManagement/directory/roleAssignmentSchedules — return role_assignment_schedules fixture."""
    return get_fixture("role_assignment_schedules", request, top)


@app.get("/v1.0/policies/authenticationMethodsPolicy")
async def get_auth_methods_policy(request: Request):
    """GET /v1.0/policies/authenticationMethodsPolicy — return auth_methods_policy fixture."""
    return get_fixture("auth_methods_policy", request)


@app.get("/v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id}")
async def get_auth_method_config(method_id: str, request: Request):
    """GET /v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id}
    — extract and return specific auth method config by id."""
    cloud = request.headers.get("X-Mock-Cloud") or app.state.cloud
    fixtures = app.state.fixtures.get(cloud, app.state.fixtures.get(app.state.cloud, {}))
    data = fixtures.get("auth_methods_policy")

    if data is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "Request_ResourceNotFound",
                    "message": "Fixture not found: auth_methods_policy",
                }
            },
        )

    # Log ignored query params
    for param in ("filter", "select", "expand"):
        if param in request.query_params:
            logger.info(f"Ignoring query param ${param}={request.query_params.get(param)}")

    # Find the auth method config by id in the authenticationMethodConfigurations array
    configs = data.get("authenticationMethodConfigurations", [])
    for config in configs:
        if config.get("id") == method_id:
            return JSONResponse(content=config)

    # Not found
    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "Request_ResourceNotFound",
                "message": f"Authentication method configuration not found: {method_id}",
            }
        },
    )


@app.get("/v1.0/auditLogs/signIns")
async def get_audit_sign_ins(request: Request, top: int | None = None):
    """GET /v1.0/auditLogs/signIns — return audit_sign_ins fixture."""
    return get_fixture("audit_sign_ins", request, top)


@app.get("/v1.0/auditLogs/directoryAudits")
async def get_audit_directory(request: Request, top: int | None = None):
    """GET /v1.0/auditLogs/directoryAudits — return audit_directory fixture."""
    return get_fixture("audit_directory", request, top)


@app.get("/v1.0/informationProtection/policy/labels")
async def get_info_protection_labels(request: Request, top: int | None = None):
    """GET /v1.0/informationProtection/policy/labels — return information_protection_labels fixture."""
    return get_fixture("information_protection_labels", request, top)


# Subtask 3.2.1: POST and PATCH Write Stubs
@app.post("/v1.0/identity/conditionalAccess/policies")
async def post_ca_policy(request: Request):
    """POST /v1.0/identity/conditionalAccess/policies — return request body with added id and createdDateTime."""
    body = await request.json()
    body["id"] = str(uuid.uuid4())
    body["createdDateTime"] = datetime.utcnow().isoformat() + "Z"

    logger.info(f"WRITE: POST /v1.0/identity/conditionalAccess/policies — created policy {body.get('displayName', 'unnamed')}")

    return JSONResponse(status_code=201, content=body)


@app.patch("/v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id}")
async def patch_auth_method_config(method_id: str, request: Request):
    """PATCH /v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id}
    — return request body unchanged."""
    body = await request.json()

    logger.info(f"WRITE: PATCH /v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id} — updated config")

    return JSONResponse(status_code=200, content=body)


@app.post("/v1.0/deviceManagement/deviceCompliancePolicies")
async def post_compliance_policy(request: Request):
    """POST /v1.0/deviceManagement/deviceCompliancePolicies — return request body with added id and createdDateTime."""
    body = await request.json()
    body["id"] = str(uuid.uuid4())
    body["createdDateTime"] = datetime.utcnow().isoformat() + "Z"

    logger.info(f"WRITE: POST /v1.0/deviceManagement/deviceCompliancePolicies — created policy {body.get('displayName', 'unnamed')}")

    return JSONResponse(status_code=201, content=body)


@app.post("/v1.0/deviceManagement/deviceConfigurations")
async def post_device_configuration(request: Request):
    """POST /v1.0/deviceManagement/deviceConfigurations — return request body with added id and createdDateTime."""
    body = await request.json()
    body["id"] = str(uuid.uuid4())
    body["createdDateTime"] = datetime.utcnow().isoformat() + "Z"

    logger.info(f"WRITE: POST /v1.0/deviceManagement/deviceConfigurations — created configuration {body.get('displayName', 'unnamed')}")

    return JSONResponse(status_code=201, content=body)


@app.api_route("/{path:path}", methods=["GET", "POST", "PATCH", "DELETE", "PUT"])
async def catch_all(path: str, request: Request):
    """Catch-all 404 handler for unmapped paths."""
    method = request.method
    logger.warning(f"Unmapped path requested: {method} /{path}")

    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "Request_ResourceNotFound",
                "message": f"Resource not found: /{path}",
            }
        },
    )


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Start m365-sim Microsoft Graph API simulation server"
    )
    parser.add_argument(
        "--scenario",
        default="greenfield",
        help="Scenario name (default: greenfield)",
    )
    parser.add_argument(
        "--cloud",
        default="gcc-moderate",
        help="Cloud environment (default: gcc-moderate)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8888,
        help="Port to run server on (default: 8888)",
    )

    return parser.parse_args()


def main():
    """Parse arguments and start uvicorn server."""
    args = parse_args()

    # Update module-level variables
    global SCENARIO, CLOUD, PORT
    SCENARIO = args.scenario
    CLOUD = args.cloud
    PORT = args.port

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Start uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=PORT,
        log_level="info",
    )


if __name__ == "__main__":
    main()
