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
from contextlib import asynccontextmanager
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


@app.get("/health")
async def health():
    """Health check endpoint (no auth required)."""
    return {
        "status": "healthy",
        "scenario": app.state.scenario,
        "cloud": app.state.cloud,
    }


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
