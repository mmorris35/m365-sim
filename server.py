#!/usr/bin/env python3
"""
m365-sim: Microsoft Graph API simulation server.

A single-file FastAPI server that serves static JSON fixtures representing
M365 tenant states. Supports CLI args for scenario/cloud/port selection,
fixture loading, auth middleware, and error simulation.
"""

import argparse
import asyncio
import copy
import json
import logging
import re
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
STATEFUL = False
WATCH = False

# Map of expandable relations: fixture_name -> {expand_field: fixture_to_load_or_None}
EXPAND_MAP: dict[str, dict[str, str | None]] = {
    "users": {
        "memberOf": "groups",
        "authentication": "me_auth_methods",
    },
    "me": {
        "authentication": "me_auth_methods",
    },
    "directory_roles": {
        "members": "directory_role_members",
    },
    "organization": {
        "subscriptions": None,
    },
}


def load_fixtures(cloud: str, scenario: str) -> dict[str, dict]:
    """Load all JSON fixtures from scenarios/{cloud}/{scenario}/*.json.

    If scenario is not greenfield, load greenfield as base first, then overlay
    the target scenario. This allows target scenarios to only override files
    that changed.

    Also loads beta-specific fixtures from scenarios/{cloud}/{scenario}/beta/*.json
    and prefixes them with "beta/" in the fixture name (e.g., "beta/managed_devices").
    """
    fixtures: dict[str, dict] = {}
    base_path = Path(__file__).parent / "scenarios" / cloud

    # If scenario is not greenfield, load greenfield first as base
    if scenario != "greenfield":
        greenfield_dir = base_path / "greenfield"
        if greenfield_dir.exists():
            json_files = sorted(greenfield_dir.glob("*.json"))
            for json_file in json_files:
                try:
                    with open(json_file, "r") as f:
                        fixture_data = json.load(f)
                    stem = json_file.stem
                    fixtures[stem] = fixture_data
                    logger.info(f"Loaded base (greenfield) fixture: {stem}")
                except Exception as e:
                    logger.error(f"Failed to load base fixture {json_file}: {e}")

    # Load target scenario, overlaying any greenfield fixtures
    scenario_dir = base_path / scenario
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

    # Load beta-specific fixtures from beta/ subdirectory with "beta/" prefix
    beta_dir = scenario_dir / "beta"
    if beta_dir.exists():
        json_files = sorted(beta_dir.glob("*.json"))
        for json_file in json_files:
            try:
                with open(json_file, "r") as f:
                    fixture_data = json.load(f)
                stem = json_file.stem
                # Prefix with "beta/" to distinguish from v1.0 fixtures
                fixtures[f"beta/{stem}"] = fixture_data
                logger.info(f"Loaded beta fixture: beta/{stem}")
            except Exception as e:
                logger.error(f"Failed to load beta fixture {json_file}: {e}")

    # Also load greenfield beta fixtures as fallback if scenario is not greenfield
    if scenario != "greenfield":
        greenfield_beta_dir = base_path / "greenfield" / "beta"
        if greenfield_beta_dir.exists():
            json_files = sorted(greenfield_beta_dir.glob("*.json"))
            for json_file in json_files:
                try:
                    stem = json_file.stem
                    # Only load if we haven't already loaded this beta fixture from the target scenario
                    if f"beta/{stem}" not in fixtures:
                        with open(json_file, "r") as f:
                            fixture_data = json.load(f)
                        fixtures[f"beta/{stem}"] = fixture_data
                        logger.info(f"Loaded base (greenfield) beta fixture: beta/{stem}")
                except Exception as e:
                    logger.error(f"Failed to load base beta fixture {json_file}: {e}")

    logger.info(f"Loaded {len(fixtures)} fixtures for {cloud}/{scenario}")
    return fixtures


def _watch_fixtures(app: "FastAPI", cloud: str, scenario: str):
    """Background thread that watches fixture files for changes."""
    base_path = Path(__file__).parent / "scenarios" / cloud
    dirs_to_watch = [base_path / scenario]
    if scenario != "greenfield":
        dirs_to_watch.append(base_path / "greenfield")

    # Build initial mtime map
    mtimes: dict[str, float] = {}
    for watch_dir in dirs_to_watch:
        if watch_dir.exists():
            for f in watch_dir.glob("*.json"):
                mtimes[str(f)] = f.stat().st_mtime

    while True:
        time.sleep(2)
        changed = False
        for watch_dir in dirs_to_watch:
            if not watch_dir.exists():
                continue
            for f in watch_dir.glob("*.json"):
                path_str = str(f)
                current_mtime = f.stat().st_mtime
                if path_str not in mtimes or mtimes[path_str] != current_mtime:
                    mtimes[path_str] = current_mtime
                    changed = True
                    logger.info(f"WATCH: detected change in {f.name}")
        if changed:
            new_fixtures = load_fixtures(cloud, scenario)
            app.state.fixtures = new_fixtures
            if hasattr(app.state, "baseline_fixtures"):
                app.state.baseline_fixtures = copy.deepcopy(new_fixtures)
            logger.info(f"WATCH: reloaded {len(new_fixtures)} fixtures")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup/shutdown."""
    # Startup: load fixtures for default cloud
    fixtures = load_fixtures(CLOUD, SCENARIO)
    app.state.cloud = CLOUD
    app.state.scenario = SCENARIO
    app.state.stateful = STATEFUL
    # Pre-load alternate cloud fixtures for X-Mock-Cloud header support
    app.state.cloud_fixtures = {CLOUD: fixtures}

    # In stateful mode: deep-copy fixtures for baseline, use working copy as mutable
    if STATEFUL:
        app.state.baseline_fixtures = copy.deepcopy(fixtures)
        app.state.fixtures = copy.deepcopy(fixtures)
        logger.info(f"Server starting in STATEFUL mode with scenario={SCENARIO}, cloud={CLOUD}")
    else:
        app.state.fixtures = fixtures
        logger.info(f"Server starting with scenario={SCENARIO}, cloud={CLOUD}")

    # Start watch thread if enabled
    watch_thread = None
    if WATCH:
        watch_thread = threading.Thread(
            target=_watch_fixtures, args=(app, CLOUD, SCENARIO), daemon=True
        )
        watch_thread.start()
        logger.info(f"Watch thread started for {CLOUD}/{SCENARIO}")

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

        # Check for Authorization header with Bearer scheme
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.lower().startswith("bearer "):
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
            response.headers["Retry-After"] = "1"

        return response


# Add middleware (order matters: execute in reverse order of addition)
app.add_middleware(MockStatusMiddleware)
app.add_middleware(AuthMiddleware)


def parse_top_param(request: Request) -> int | None:
    """Parse $top query parameter from request.

    Returns None if not present or invalid.
    """
    top_str = request.query_params.get("$top")
    if not top_str:
        return None
    try:
        return int(top_str)
    except ValueError:
        return None


def _parse_filter_expression(filter_expr: str) -> list[dict] | None:
    """Parse OData $filter expression into a list of conditions.

    Supports:
    - eq operator: field eq 'value' or field eq value (string/bool/int)
    - ne operator: field ne 'value' (not equal)
    - gt, lt, ge, le operators: field gt 5, field lt 100 (numeric/string comparison)
    - startswith: startswith(field,'prefix')
    - contains: contains(field,'substring')
    - in operator: field in ('val1', 'val2', 'val3')
    - and/or combinators

    Returns list of dicts: [{"field": str, "value": Any, "filter_op": str, "operator": "and"|"or"}, ...]
    Returns None if filter is unparseable.
    """
    try:
        conditions = []
        # Split by 'and' and 'or' while capturing the operator
        # Pattern: (field/path) (op) (value) [(and|or) ...]
        parts = re.split(r'\s+(and|or)\s+', filter_expr.strip())

        i = 0
        while i < len(parts):
            part = parts[i].strip()
            if not part or part in ('and', 'or'):
                i += 1
                continue

            filter_op = None
            field = None
            value = None

            # Try startswith function: startswith(field,'value')
            match = re.match(r"startswith\((\w+(?:/\w+)*)\s*,\s*'([^']*)'\)", part)
            if match:
                filter_op = "startswith"
                field = match.group(1)
                value = match.group(2)

            # Try contains function: contains(field,'value')
            if not match:
                match = re.match(r"contains\((\w+(?:/\w+)*)\s*,\s*'([^']*)'\)", part)
                if match:
                    filter_op = "contains"
                    field = match.group(1)
                    value = match.group(2)

            # Try in operator: field in ('val1','val2',...)
            if not match:
                match = re.match(r"(\w+(?:/\w+)*)\s+in\s+\(([^)]+)\)", part)
                if match:
                    filter_op = "in"
                    field = match.group(1)
                    # Parse comma-separated quoted values
                    values_str = match.group(2)
                    values = re.findall(r"'([^']*)'", values_str)
                    value = values

            # Try comparison operators: ne, gt, lt, ge, le
            if not match:
                match = re.match(r"(\w+(?:/\w+)*)\s+(ne|gt|lt|ge|le)\s+(?:'([^']*)'|(\w+))", part)
                if match:
                    filter_op = match.group(2)
                    field = match.group(1)
                    string_value = match.group(3)
                    bare_value = match.group(4)

                    # Determine value type and convert
                    if string_value is not None:
                        value = string_value
                    elif bare_value == 'true':
                        value = True
                    elif bare_value == 'false':
                        value = False
                    else:
                        try:
                            value = float(bare_value)
                        except ValueError:
                            value = bare_value

            # Try eq operator (original): field eq value
            if not match:
                match = re.match(r"(\w+(?:/\w+)*)\s+eq\s+(?:'([^']*)'|(\w+))", part)
                if match:
                    filter_op = "eq"
                    field = match.group(1)
                    string_value = match.group(2)
                    bare_value = match.group(3)

                    # Determine value type and convert
                    if string_value is not None:
                        value = string_value
                    elif bare_value == 'true':
                        value = True
                    elif bare_value == 'false':
                        value = False
                    else:
                        try:
                            value = int(bare_value)
                        except ValueError:
                            value = bare_value

            if not match:
                return None

            # Get operator (next element if present and is and/or)
            operator = "and"  # default
            if i + 1 < len(parts) and parts[i + 1] in ('and', 'or'):
                operator = parts[i + 1]

            conditions.append({
                "field": field,
                "value": value,
                "filter_op": filter_op,
                "operator": operator
            })
            i += 2 if (i + 1 < len(parts) and parts[i + 1] in ('and', 'or')) else 1

        return conditions if conditions else None
    except Exception:
        return None


def _evaluate_filter(item: dict, conditions: list[dict]) -> bool:
    """Evaluate whether an item matches the filter conditions.

    Supports:
    - eq: equality
    - ne: not equal
    - gt, lt, ge, le: numeric and string comparison
    - startswith: string prefix match
    - contains: substring match
    - in: value in list
    - and/or operators for combining conditions

    Returns True if item matches all conditions, False otherwise.
    """
    if not conditions:
        return True

    result = None

    for i, condition in enumerate(conditions):
        field = condition["field"]
        expected_value = condition["value"]
        filter_op = condition["filter_op"]
        operator = condition["operator"]

        # Get field value from item (support nested paths like grantControls/builtInControls)
        field_parts = field.split('/')
        item_value = item
        for part in field_parts:
            if isinstance(item_value, dict):
                item_value = item_value.get(part)
            else:
                item_value = None
                break

        # Evaluate condition based on filter operator
        matches = False

        if filter_op == "eq":
            matches = item_value == expected_value

        elif filter_op == "ne":
            matches = item_value != expected_value

        elif filter_op in ("gt", "lt", "ge", "le"):
            # Numeric and string comparison
            if item_value is not None:
                try:
                    # Try numeric comparison first
                    item_num = float(item_value) if isinstance(item_value, (int, float, str)) else None
                    expected_num = float(expected_value) if isinstance(expected_value, (int, float, str)) else None

                    if item_num is not None and expected_num is not None:
                        if filter_op == "gt":
                            matches = item_num > expected_num
                        elif filter_op == "lt":
                            matches = item_num < expected_num
                        elif filter_op == "ge":
                            matches = item_num >= expected_num
                        elif filter_op == "le":
                            matches = item_num <= expected_num
                    else:
                        # Fall back to string comparison
                        item_str = str(item_value)
                        expected_str = str(expected_value)
                        if filter_op == "gt":
                            matches = item_str > expected_str
                        elif filter_op == "lt":
                            matches = item_str < expected_str
                        elif filter_op == "ge":
                            matches = item_str >= expected_str
                        elif filter_op == "le":
                            matches = item_str <= expected_str
                except (ValueError, TypeError):
                    # Fall back to string comparison
                    item_str = str(item_value)
                    expected_str = str(expected_value)
                    if filter_op == "gt":
                        matches = item_str > expected_str
                    elif filter_op == "lt":
                        matches = item_str < expected_str
                    elif filter_op == "ge":
                        matches = item_str >= expected_str
                    elif filter_op == "le":
                        matches = item_str <= expected_str

        elif filter_op == "startswith":
            if item_value is not None:
                matches = str(item_value).startswith(str(expected_value))

        elif filter_op == "contains":
            if item_value is not None:
                matches = str(expected_value) in str(item_value)

        elif filter_op == "in":
            # expected_value is a list
            if item_value is not None:
                matches = item_value in expected_value

        # Apply operator logic
        if i == 0:
            result = matches
        else:
            prev_operator = conditions[i - 1]["operator"]
            if prev_operator == "and":
                result = result and matches
            elif prev_operator == "or":
                result = result or matches

    return result if result is not None else True


def _apply_expand(data: dict, expand_expr: str, fixtures: dict[str, dict], fixture_name: str = "") -> dict:
    """Apply OData $expand to add related resources.

    For collection endpoints (with 'value' array), adds expanded property to each item.
    For singleton endpoints (no 'value' array), adds expanded property directly.
    Expansion happens after $filter but before $top.

    $expand=field1,field2 expands specific fields.
    $expand=* expands all known relations for the fixture type.
    Unknown fields are logged and skipped gracefully.
    """
    if not expand_expr:
        return data

    result = copy.deepcopy(data)
    is_collection = "value" in result and isinstance(result["value"], list)

    # Parse expand fields
    expand_fields = [f.strip() for f in expand_expr.split(",")]

    # Determine fixture type - try to match against EXPAND_MAP
    fixture_type = None

    # Use fixture_name to look up expand relations directly
    if fixture_name in EXPAND_MAP:
        fixture_type = fixture_name

    if fixture_type is None or fixture_type not in EXPAND_MAP:
        logger.warning(f"Could not determine fixture type for $expand")
        return result

    expand_map = EXPAND_MAP.get(fixture_type, {})

    # Handle $expand=*
    if expand_fields == ["*"]:
        expand_fields = list(expand_map.keys())

    # Apply expansions
    for expand_field in expand_fields:
        if expand_field == "*":
            continue

        if expand_field not in expand_map:
            logger.warning(f"Unknown expand field '{expand_field}' for fixture type '{fixture_type}', skipping")
            continue

        target_fixture_name = expand_map[expand_field]
        if target_fixture_name is None:
            # Expand maps to None (unsupported expansion)
            logger.info(f"Expand field '{expand_field}' not supported, skipping")
            continue

        # Load the target fixture
        target_data = fixtures.get(target_fixture_name)
        if target_data is None:
            logger.warning(f"Expand target fixture '{target_fixture_name}' not found")
            continue

        # For collection target fixtures, use the 'value' array
        if isinstance(target_data.get("value"), list):
            expansion_value = target_data["value"]
        else:
            # For singleton fixtures, use the whole fixture
            expansion_value = target_data

        # Apply expansion
        if is_collection:
            # Add the expanded property to each item in the value array
            for item in result.get("value", []):
                item[expand_field] = copy.deepcopy(expansion_value)
        else:
            # For singleton endpoints, add directly to the object
            result[expand_field] = copy.deepcopy(expansion_value)

    logger.info(f"Applying $expand: {expand_fields}")
    return result


def _apply_filter(data: dict, filter_expr: str) -> dict:
    """Apply OData $filter to fixture data.

    Returns filtered data with the same structure but filtered 'value' array.
    On parse error, returns unfiltered data with a warning.
    """
    if "value" not in data or not isinstance(data["value"], list):
        return data

    conditions = _parse_filter_expression(filter_expr)
    if conditions is None:
        logger.warning(f"Unsupported $filter syntax, returning unfiltered: {filter_expr}")
        return data

    logger.info(f"Applying $filter: {filter_expr}")
    filtered_value = [item for item in data["value"] if _evaluate_filter(item, conditions)]

    result = dict(data)
    result["value"] = filtered_value
    return result


def _get_fixtures_for_request(request: Request) -> dict[str, dict]:
    """Get the fixture dict for this request, respecting X-Mock-Cloud header."""
    override_cloud = request.headers.get("x-mock-cloud")
    if override_cloud and override_cloud != app.state.cloud:
        if override_cloud not in app.state.cloud_fixtures:
            app.state.cloud_fixtures[override_cloud] = load_fixtures(override_cloud, app.state.scenario)
            logger.info(f"Loaded fixtures for X-Mock-Cloud override: {override_cloud}")
        return app.state.cloud_fixtures[override_cloud]
    return app.state.fixtures


def get_fixture(name: str, request: Request, top: int | None = None) -> JSONResponse:
    """Return fixture data with optional $filter, $expand, and $top truncation.

    Processing order: $filter → $expand → $top
    $select is logged but ignored.
    """
    fixtures = _get_fixtures_for_request(request)
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

    result = dict(data)  # shallow copy

    # Apply $filter if present (applied before $expand)
    filter_expr = request.query_params.get("$filter")
    if filter_expr:
        result = _apply_filter(result, filter_expr)

    # Apply $expand if present (applied after $filter but before $top)
    expand_expr = request.query_params.get("$expand")
    if expand_expr:
        result = _apply_expand(result, expand_expr, fixtures, name)

    # Log ignored query param
    if "$select" in request.query_params:
        logger.info(f"Ignoring query param $select={request.query_params.get('$select')}")

    # Apply $top truncation (after filter is applied).
    # Negative $top values are silently ignored (returns full result set).
    if top is not None and top >= 0 and "value" in result:
        result["value"] = result["value"][:top]

    return JSONResponse(content=result)


def _rewrite_context_to_beta(data: Any) -> Any:
    """Recursively rewrite @odata.context URLs from v1.0 to beta in response data.

    Handles:
    - Direct dict with @odata.context key
    - Nested dicts (e.g., error objects)
    - Lists of items (e.g., 'value' arrays)
    - All cloud contexts: graph.microsoft.com, graph.microsoft.us, etc.

    Returns: data with all @odata.context URLs rewritten.
    """
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if key == "@odata.context" and isinstance(value, str):
                # Rewrite v1.0 to beta in the context URL
                result[key] = value.replace("/v1.0/", "/beta/")
            else:
                # Recursively process nested structures
                result[key] = _rewrite_context_to_beta(value)
        return result
    elif isinstance(data, list):
        return [_rewrite_context_to_beta(item) for item in data]
    else:
        return data


@app.get("/health")
async def health():
    """Health check endpoint (no auth required)."""
    return {
        "status": "healthy",
        "scenario": app.state.scenario,
        "cloud": app.state.cloud,
        "watch": WATCH,
    }


# Subtask 3.1.1: Identity and User Endpoints
@app.get("/v1.0/users")
async def get_users(request: Request):
    """GET /v1.0/users — return users fixture."""
    top = parse_top_param(request)
    return get_fixture("users", request, top)


@app.get("/v1.0/me")
async def get_me(request: Request):
    """GET /v1.0/me — return me fixture."""
    return get_fixture("me", request)


@app.get("/v1.0/me/authentication/methods")
async def get_me_auth_methods(request: Request):
    """GET /v1.0/me/authentication/methods — return me_auth_methods fixture."""
    top = parse_top_param(request)
    return get_fixture("me_auth_methods", request, top)


@app.get("/v1.0/users/{user_id}/authentication/methods")
async def get_user_auth_methods(user_id: str, request: Request):
    """GET /v1.0/users/{user_id}/authentication/methods — return me_auth_methods fixture."""
    top = parse_top_param(request)
    return get_fixture("me_auth_methods", request, top)


@app.get("/v1.0/organization")
async def get_organization(request: Request):
    """GET /v1.0/organization — return organization fixture."""
    return get_fixture("organization", request)


@app.get("/v1.0/domains")
async def get_domains(request: Request):
    """GET /v1.0/domains — return domains fixture."""
    top = parse_top_param(request)
    return get_fixture("domains", request, top)


@app.get("/v1.0/groups")
async def get_groups(request: Request):
    """GET /v1.0/groups — return groups fixture."""
    top = parse_top_param(request)
    return get_fixture("groups", request, top)


@app.get("/v1.0/applications")
async def get_applications(request: Request):
    """GET /v1.0/applications — return applications fixture."""
    top = parse_top_param(request)
    return get_fixture("applications", request, top)


@app.get("/v1.0/servicePrincipals")
async def get_service_principals(request: Request):
    """GET /v1.0/servicePrincipals — return service_principals fixture."""
    top = parse_top_param(request)
    return get_fixture("service_principals", request, top)


# Subtask 3.1.2: Security, Devices, and Conditional Access Endpoints
@app.get("/v1.0/devices")
async def get_devices(request: Request):
    """GET /v1.0/devices — return devices fixture."""
    top = parse_top_param(request)
    return get_fixture("devices", request, top)


@app.get("/v1.0/deviceManagement/managedDevices")
async def get_managed_devices(request: Request):
    """GET /v1.0/deviceManagement/managedDevices — return managed_devices fixture."""
    top = parse_top_param(request)
    return get_fixture("managed_devices", request, top)


@app.get("/v1.0/deviceManagement/deviceCompliancePolicies")
async def get_compliance_policies(request: Request):
    """GET /v1.0/deviceManagement/deviceCompliancePolicies — return compliance_policies fixture."""
    top = parse_top_param(request)
    return get_fixture("compliance_policies", request, top)


@app.get("/v1.0/deviceManagement/deviceConfigurations")
async def get_device_configurations(request: Request):
    """GET /v1.0/deviceManagement/deviceConfigurations — return device_configurations fixture."""
    top = parse_top_param(request)
    return get_fixture("device_configurations", request, top)


@app.get("/v1.0/deviceManagement/deviceEnrollmentConfigurations")
async def get_enrollment_configurations(request: Request):
    """GET /v1.0/deviceManagement/deviceEnrollmentConfigurations — return device_enrollment_configurations fixture."""
    top = parse_top_param(request)
    return get_fixture("device_enrollment_configurations", request, top)


@app.get("/v1.0/identity/conditionalAccess/policies")
async def get_ca_policies(request: Request):
    """GET /v1.0/identity/conditionalAccess/policies — return conditional_access_policies fixture."""
    top = parse_top_param(request)
    return get_fixture("conditional_access_policies", request, top)


@app.get("/v1.0/identity/conditionalAccess/namedLocations")
async def get_named_locations(request: Request):
    """GET /v1.0/identity/conditionalAccess/namedLocations — return named_locations fixture."""
    top = parse_top_param(request)
    return get_fixture("named_locations", request, top)


@app.get("/v1.0/security/incidents")
async def get_security_incidents(request: Request):
    """GET /v1.0/security/incidents — return security_incidents fixture."""
    top = parse_top_param(request)
    return get_fixture("security_incidents", request, top)


@app.get("/v1.0/security/alerts_v2")
async def get_security_alerts(request: Request):
    """GET /v1.0/security/alerts_v2 — return security_alerts fixture."""
    top = parse_top_param(request)
    return get_fixture("security_alerts", request, top)


@app.get("/v1.0/security/secureScores")
async def get_secure_scores(request: Request):
    """GET /v1.0/security/secureScores — return secure_scores fixture."""
    top = parse_top_param(request)
    return get_fixture("secure_scores", request, top)


@app.get("/v1.0/security/secureScoreControlProfiles")
async def get_score_control_profiles(request: Request):
    """GET /v1.0/security/secureScoreControlProfiles — return secure_score_control_profiles fixture."""
    top = parse_top_param(request)
    return get_fixture("secure_score_control_profiles", request, top)


# Subtask 3.1.3: Roles, Auth Methods Policy, Audit Logs, and Info Protection Endpoints
@app.get("/v1.0/directoryRoles")
async def get_directory_roles(request: Request):
    """GET /v1.0/directoryRoles — return directory_roles fixture."""
    top = parse_top_param(request)
    return get_fixture("directory_roles", request, top)


@app.get("/v1.0/directoryRoles/{role_id}/members")
async def get_directory_role_members(role_id: str, request: Request):
    """GET /v1.0/directoryRoles/{role_id}/members — return directory_role_members fixture."""
    top = parse_top_param(request)
    return get_fixture("directory_role_members", request, top)


@app.get("/v1.0/roleManagement/directory/roleAssignments")
async def get_role_assignments(request: Request):
    """GET /v1.0/roleManagement/directory/roleAssignments — return role_assignments fixture."""
    top = parse_top_param(request)
    return get_fixture("role_assignments", request, top)


@app.get("/v1.0/roleManagement/directory/roleDefinitions")
async def get_role_definitions(request: Request):
    """GET /v1.0/roleManagement/directory/roleDefinitions — return role_definitions fixture."""
    top = parse_top_param(request)
    return get_fixture("role_definitions", request, top)


@app.get("/v1.0/roleManagement/directory/roleEligibilitySchedules")
async def get_role_eligibility_schedules(request: Request):
    """GET /v1.0/roleManagement/directory/roleEligibilitySchedules — return role_eligibility_schedules fixture."""
    top = parse_top_param(request)
    return get_fixture("role_eligibility_schedules", request, top)


@app.get("/v1.0/roleManagement/directory/roleAssignmentSchedules")
async def get_role_assignment_schedules(request: Request):
    """GET /v1.0/roleManagement/directory/roleAssignmentSchedules — return role_assignment_schedules fixture."""
    top = parse_top_param(request)
    return get_fixture("role_assignment_schedules", request, top)


@app.get("/v1.0/policies/authenticationMethodsPolicy")
async def get_auth_methods_policy(request: Request):
    """GET /v1.0/policies/authenticationMethodsPolicy — return auth_methods_policy fixture."""
    return get_fixture("auth_methods_policy", request)


@app.get("/v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id}")
async def get_auth_method_config(method_id: str, request: Request):
    """GET /v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id}
    — extract and return specific auth method config by id."""
    fixtures = _get_fixtures_for_request(request)
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
    for param in ("$filter", "$select", "$expand"):
        if param in request.query_params:
            logger.info(f"Ignoring query param {param}={request.query_params.get(param)}")

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
async def get_audit_sign_ins(request: Request):
    """GET /v1.0/auditLogs/signIns — return audit_sign_ins fixture."""
    top = parse_top_param(request)
    return get_fixture("audit_sign_ins", request, top)


@app.get("/v1.0/auditLogs/directoryAudits")
async def get_audit_directory(request: Request):
    """GET /v1.0/auditLogs/directoryAudits — return audit_directory fixture."""
    top = parse_top_param(request)
    return get_fixture("audit_directory", request, top)


@app.get("/v1.0/informationProtection/policy/labels")
async def get_info_protection_labels(request: Request):
    """GET /v1.0/informationProtection/policy/labels — return information_protection_labels fixture."""
    top = parse_top_param(request)
    return get_fixture("information_protection_labels", request, top)


# Subtask 23.1.1: Priority 1 Endpoints
@app.get("/v1.0/policies/authorizationPolicy")
async def get_authorization_policy(request: Request):
    """GET /v1.0/policies/authorizationPolicy — return authorization_policy fixture."""
    return get_fixture("authorization_policy", request)


@app.get("/v1.0/subscribedSkus")
async def get_subscribed_skus(request: Request):
    """GET /v1.0/subscribedSkus — return subscribed_skus fixture."""
    top = parse_top_param(request)
    return get_fixture("subscribed_skus", request, top)


@app.get("/v1.0/reports/authenticationMethods/usersRegisteredByMethod")
async def get_users_registered_by_method(request: Request):
    """GET /v1.0/reports/authenticationMethods/usersRegisteredByMethod — return users_registered_by_method fixture."""
    return get_fixture("users_registered_by_method", request)


@app.get("/v1.0/identityGovernance/accessReviews/definitions")
async def get_access_review_definitions(request: Request):
    """GET /v1.0/identityGovernance/accessReviews/definitions — return access_review_definitions fixture."""
    top = parse_top_param(request)
    return get_fixture("access_review_definitions", request, top)


@app.get("/v1.0/deviceAppManagement/managedAppPolicies")
async def get_managed_app_policies(request: Request):
    """GET /v1.0/deviceAppManagement/managedAppPolicies — return managed_app_policies fixture."""
    top = parse_top_param(request)
    return get_fixture("managed_app_policies", request, top)


@app.get("/v1.0/deviceAppManagement/mobileApps")
async def get_mobile_apps(request: Request):
    """GET /v1.0/deviceAppManagement/mobileApps — return mobile_apps fixture."""
    top = parse_top_param(request)
    return get_fixture("mobile_apps", request, top)


@app.get("/v1.0/deviceManagement/detectedApps")
async def get_detected_apps(request: Request):
    """GET /v1.0/deviceManagement/detectedApps — return detected_apps fixture."""
    top = parse_top_param(request)
    return get_fixture("detected_apps", request, top)


@app.get("/v1.0/auditLogs/provisioning")
async def get_provisioning_logs(request: Request):
    """GET /v1.0/auditLogs/provisioning — return provisioning_logs fixture."""
    top = parse_top_param(request)
    return get_fixture("provisioning_logs", request, top)


@app.get("/v1.0/security/alerts")
async def get_security_alerts_v1(request: Request):
    """GET /v1.0/security/alerts — return security_alerts_v1 fixture."""
    top = parse_top_param(request)
    return get_fixture("security_alerts_v1", request, top)


# Subtask 3.2.1: POST and PATCH Write Stubs
@app.post("/v1.0/identity/conditionalAccess/policies")
async def post_ca_policy(request: Request):
    """POST /v1.0/identity/conditionalAccess/policies — return request body with added id and createdDateTime."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    body["id"] = str(uuid.uuid4())
    body["createdDateTime"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    logger.info(f"WRITE: POST /v1.0/identity/conditionalAccess/policies — created policy {body.get('displayName', 'unnamed')}")

    # In stateful mode: add to fixture value array
    if request.app.state.stateful:
        if "conditional_access_policies" in request.app.state.fixtures:
            fixture = request.app.state.fixtures["conditional_access_policies"]
            if "value" in fixture:
                # Shallow-copy body to avoid reference issues
                fixture["value"].append(copy.copy(body))

    return JSONResponse(status_code=201, content=body)


@app.patch("/v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id}")
async def patch_auth_method_config(method_id: str, request: Request):
    """PATCH /v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id}
    — return request body unchanged."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    logger.info(f"WRITE: PATCH /v1.0/policies/authenticationMethodsPolicy/authenticationMethodConfigurations/{method_id} — updated config")

    # In stateful mode: find the config in fixture and merge fields
    if request.app.state.stateful:
        if "auth_methods_policy" in request.app.state.fixtures:
            fixture = request.app.state.fixtures["auth_methods_policy"]
            if "authenticationMethodConfigurations" in fixture:
                configs = fixture["authenticationMethodConfigurations"]
                for config in configs:
                    if config.get("id") == method_id:
                        # Merge request body fields into the config
                        config.update(body)
                        break

    return JSONResponse(status_code=200, content=body)


@app.post("/v1.0/deviceManagement/deviceCompliancePolicies")
async def post_compliance_policy(request: Request):
    """POST /v1.0/deviceManagement/deviceCompliancePolicies — return request body with added id and createdDateTime."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    body["id"] = str(uuid.uuid4())
    body["createdDateTime"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    logger.info(f"WRITE: POST /v1.0/deviceManagement/deviceCompliancePolicies — created policy {body.get('displayName', 'unnamed')}")

    # In stateful mode: add to fixture value array
    if request.app.state.stateful:
        if "compliance_policies" in request.app.state.fixtures:
            fixture = request.app.state.fixtures["compliance_policies"]
            if "value" in fixture:
                # Shallow-copy body to avoid reference issues
                fixture["value"].append(copy.copy(body))

    return JSONResponse(status_code=201, content=body)


@app.post("/v1.0/deviceManagement/deviceConfigurations")
async def post_device_configuration(request: Request):
    """POST /v1.0/deviceManagement/deviceConfigurations — return request body with added id and createdDateTime."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    body["id"] = str(uuid.uuid4())
    body["createdDateTime"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    logger.info(f"WRITE: POST /v1.0/deviceManagement/deviceConfigurations — created configuration {body.get('displayName', 'unnamed')}")

    # In stateful mode: add to fixture value array
    if request.app.state.stateful:
        if "device_configurations" in request.app.state.fixtures:
            fixture = request.app.state.fixtures["device_configurations"]
            if "value" in fixture:
                # Shallow-copy body to avoid reference issues
                fixture["value"].append(copy.copy(body))

    return JSONResponse(status_code=201, content=body)


@app.post("/v1.0/_reset")
async def reset_fixtures(request: Request):
    """POST /v1.0/_reset — reset fixtures to baseline (stateful mode only)."""
    if not request.app.state.stateful:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "Request_ResourceNotFound",
                    "message": "Reset endpoint only available in stateful mode",
                }
            },
        )

    # Reset fixtures from baseline
    baseline = request.app.state.baseline_fixtures
    request.app.state.fixtures = copy.deepcopy(baseline)
    fixtures_count = len(request.app.state.fixtures)

    logger.info(f"WRITE: POST /v1.0/_reset — reset {fixtures_count} fixtures to baseline")

    return JSONResponse(
        status_code=200,
        content={"status": "reset", "fixtures_loaded": fixtures_count},
    )


@app.post("/v1.0/_reload")
async def reload_fixtures(request: Request):
    """POST /v1.0/_reload — reload fixtures from disk."""
    cloud = request.app.state.cloud
    scenario = request.app.state.scenario
    new_fixtures = load_fixtures(cloud, scenario)
    request.app.state.fixtures = new_fixtures
    if hasattr(request.app.state, "baseline_fixtures"):
        request.app.state.baseline_fixtures = copy.deepcopy(new_fixtures)
    fixtures_count = len(new_fixtures)

    logger.info(f"RELOAD: reloaded {fixtures_count} fixtures from disk for {cloud}/{scenario}")

    return JSONResponse(
        status_code=200,
        content={
            "status": "reloaded",
            "fixtures_loaded": fixtures_count,
            "scenario": scenario,
            "cloud": cloud,
        },
    )


# Subtask 25.1.1: Defender for Endpoint API Routes
@app.get("/api/alerts")
async def get_defender_alerts(request: Request):
    """GET /api/alerts — return Defender security alerts."""
    top = parse_top_param(request)
    return get_fixture("defender_alerts", request, top)


@app.get("/api/apps")
async def get_defender_apps(request: Request):
    """GET /api/apps — return discovered applications."""
    top = parse_top_param(request)
    return get_fixture("defender_apps", request, top)


@app.get("/api/deviceavinfo")
async def get_defender_deviceavinfo(request: Request):
    """GET /api/deviceavinfo — return device antivirus status."""
    top = parse_top_param(request)
    return get_fixture("defender_deviceavinfo", request, top)


@app.get("/api/machines/{machine_id}/recommendations")
async def get_defender_recommendations(machine_id: str, request: Request):
    """GET /api/machines/{machine_id}/recommendations — return security recommendations per device."""
    top = parse_top_param(request)
    return get_fixture("defender_recommendations", request, top)


@app.get("/api/machines/{machine_id}/vulnerabilities")
async def get_defender_vulnerabilities(machine_id: str, request: Request):
    """GET /api/machines/{machine_id}/vulnerabilities — return CVE objects per device."""
    top = parse_top_param(request)
    return get_fixture("defender_vulnerabilities", request, top)


@app.get("/api/policies/appcontrol")
async def get_defender_appcontrol(request: Request):
    """GET /api/policies/appcontrol — return WDAC/AppLocker policies."""
    top = parse_top_param(request)
    return get_fixture("defender_appcontrol", request, top)


@app.get("/api/vulnerabilities/machinesVulnerabilities")
async def get_defender_machine_vulnerabilities(request: Request):
    """GET /api/vulnerabilities/machinesVulnerabilities — return all machine vulnerabilities."""
    top = parse_top_param(request)
    return get_fixture("defender_machine_vulnerabilities", request, top)


@app.api_route("/beta/{path:path}", methods=["GET", "POST", "PATCH", "DELETE", "PUT"])
async def beta_route(path: str, request: Request):
    """Mirror /v1.0/ routes under /beta/ with context URL rewriting.

    This catch-all handler maps /beta/{path} to the /v1.0/{path} fixtures,
    with @odata.context URLs rewritten from v1.0 to beta.

    Beta-specific fixtures are checked first (in fixtures["beta/{fixture_name}"]).
    If not found, falls back to v1.0 fixtures (in fixtures["{fixture_name}"]).

    Supports all query parameters ($top, $filter, $expand) and write operations
    (POST, PATCH) with the same behavior as v1.0 routes.
    """
    method = request.method

    # Construct the equivalent v1.0 path
    v1_path = f"v1.0/{path}"

    # Map the path to a fixture name for get_fixture() calls
    # This reuses the exact same logic as v1.0 routes
    v1_fixture_name = _path_to_fixture_name(path)

    # Check for beta-specific fixture first, then fall back to v1.0 fixture
    fixtures = _get_fixtures_for_request(request)
    beta_fixture_name = f"beta/{v1_fixture_name}"

    if beta_fixture_name in fixtures:
        fixture_name = beta_fixture_name
        logger.info(f"Beta route {method} /beta/{path} -> beta fixture '{fixture_name}'")
    else:
        fixture_name = v1_fixture_name
        logger.info(f"Beta route {method} /beta/{path} -> v1.0 fixture '{fixture_name}'")

    if method == "GET":
        # For GET requests, delegate to get_fixture with context rewriting
        top = parse_top_param(request)
        response = get_fixture(fixture_name, request, top)

        # Rewrite context URLs in the response
        if response.status_code == 200:
            data = json.loads(response.body)
            data = _rewrite_context_to_beta(data)
            return JSONResponse(content=data, status_code=200)
        else:
            return response

    elif method in ("POST", "PATCH"):
        # For write operations, delegate to the appropriate handler based on path
        response = await _handle_beta_write(path, request, method)

        # Rewrite context URLs in the response
        if isinstance(response, JSONResponse):
            try:
                data = json.loads(response.body)
                data = _rewrite_context_to_beta(data)
                return JSONResponse(content=data, status_code=response.status_code)
            except Exception:
                return response
        else:
            return response

    else:
        # DELETE, PUT, or other methods not yet supported
        return JSONResponse(
            status_code=405,
            content={
                "error": {
                    "code": "Request_MethodNotAllowed",
                    "message": f"Method {method} not supported",
                }
            },
        )


def _path_to_fixture_name(path: str) -> str:
    """Map a URL path to a fixture name for lookup.

    Examples:
    - "users" -> "users"
    - "me" -> "me"
    - "identity/conditionalAccess/policies" -> "conditional_access_policies"
    - "deviceManagement/managedDevices" -> "managed_devices"
    """
    # Build a mapping based on known v1.0 routes
    path_map = {
        "users": "users",
        "me": "me",
        "organization": "organization",
        "domains": "domains",
        "groups": "groups",
        "applications": "applications",
        "servicePrincipals": "service_principals",
        "devices": "devices",
        "deviceManagement/managedDevices": "managed_devices",
        "deviceManagement/deviceCompliancePolicies": "compliance_policies",
        "deviceManagement/deviceConfigurations": "device_configurations",
        "deviceManagement/deviceEnrollmentConfigurations": "device_enrollment_configurations",
        "identity/conditionalAccess/policies": "conditional_access_policies",
        "identity/conditionalAccess/namedLocations": "named_locations",
        "security/incidents": "security_incidents",
        "security/alerts_v2": "security_alerts",
        "security/secureScores": "secure_scores",
        "security/secureScoreControlProfiles": "secure_score_control_profiles",
        "directoryRoles": "directory_roles",
        "roleManagement/directory/roleAssignments": "role_assignments",
        "roleManagement/directory/roleDefinitions": "role_definitions",
        "roleManagement/directory/roleEligibilitySchedules": "role_eligibility_schedules",
        "roleManagement/directory/roleAssignmentSchedules": "role_assignment_schedules",
        "policies/authenticationMethodsPolicy": "auth_methods_policy",
        "auditLogs/signIns": "audit_sign_ins",
        "auditLogs/directoryAudits": "audit_directory",
        "informationProtection/policy/labels": "information_protection_labels",
        "policies/authorizationPolicy": "authorization_policy",
        "subscribedSkus": "subscribed_skus",
        "reports/authenticationMethods/usersRegisteredByMethod": "users_registered_by_method",
        "identityGovernance/accessReviews/definitions": "access_review_definitions",
        "deviceAppManagement/managedAppPolicies": "managed_app_policies",
        "deviceAppManagement/mobileApps": "mobile_apps",
        "deviceManagement/detectedApps": "detected_apps",
        "auditLogs/provisioning": "provisioning_logs",
        "security/alerts": "security_alerts_v1",
        # Beta-only paths (not available in v1.0)
        "identityProtection/riskDetections": "risk_detections",
        "security/attackSimulation/simulations": "attack_simulations",
        "security/attackSimulation/trainings": "attack_trainings",
        "deviceManagement/deviceHealthScripts": "device_health_scripts",
        "security/securityIntents": "intents",
        "deviceManagement/groupPolicyConfigurations": "group_policy_configurations",
        "deviceManagement/remoteActionAudits": "remote_action_audits",
    }

    # Try exact match first
    if path in path_map:
        return path_map[path]

    # Try prefix match for paths with IDs (e.g., "users/123/authentication/methods")
    if path.startswith("users/") and "/authentication/methods" in path:
        return "me_auth_methods"
    if path.startswith("me/authentication/methods"):
        return "me_auth_methods"
    if path.startswith("directoryRoles/") and "/members" in path:
        return "directory_role_members"

    # Default to the last path component
    parts = path.split('/')
    return parts[-1] if parts else path


async def _handle_beta_write(path: str, request: Request, method: str) -> JSONResponse:
    """Handle POST/PATCH operations on beta routes.

    This delegates to the same write logic as v1.0 routes.
    """
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse JSON body: {e}")
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "Request_BadRequest",
                    "message": "Invalid JSON body",
                }
            },
        )

    # Handle specific write paths
    if method == "POST":
        if path == "identity/conditionalAccess/policies":
            # Add id and createdDateTime like the v1.0 handler
            body["id"] = str(uuid.uuid4())
            body["createdDateTime"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            return JSONResponse(status_code=201, content=body)

        elif path == "deviceManagement/deviceCompliancePolicies":
            body["id"] = str(uuid.uuid4())
            body["createdDateTime"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            return JSONResponse(status_code=201, content=body)

        elif path == "deviceManagement/deviceConfigurations":
            body["id"] = str(uuid.uuid4())
            body["createdDateTime"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            return JSONResponse(status_code=201, content=body)

        else:
            # Unknown POST endpoint
            logger.warning(f"Unknown beta POST endpoint: /beta/{path}")
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "Request_ResourceNotFound",
                        "message": f"POST not supported for /beta/{path}",
                    }
                },
            )

    elif method == "PATCH":
        if path.startswith("policies/authenticationMethodsPolicy/authenticationMethodConfigurations/"):
            # Return the PATCH body unchanged
            return JSONResponse(status_code=200, content=body)

        else:
            logger.warning(f"Unknown beta PATCH endpoint: /beta/{path}")
            return JSONResponse(
                status_code=404,
                content={
                    "error": {
                        "code": "Request_ResourceNotFound",
                        "message": f"PATCH not supported for /beta/{path}",
                    }
                },
            )

    return JSONResponse(
        status_code=405,
        content={
            "error": {
                "code": "Request_MethodNotAllowed",
                "message": f"Method {method} not supported",
            }
        },
    )


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
    parser.add_argument(
        "--stateful",
        action="store_true",
        default=False,
        help="Enable stateful write operations (default: False)",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        default=False,
        help="Enable fixture file watcher for hot reload (default: False)",
    )

    return parser.parse_args()


def main():
    """Parse arguments and start uvicorn server."""
    args = parse_args()

    # Update module-level variables
    global SCENARIO, CLOUD, PORT, STATEFUL, WATCH
    SCENARIO = args.scenario
    CLOUD = args.cloud
    PORT = args.port
    STATEFUL = args.stateful
    WATCH = args.watch

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
