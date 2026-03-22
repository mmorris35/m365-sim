"""
Shared pytest fixtures for m365-sim tests.

Provides:
- mock_server: session-scoped fixture that starts a subprocess server
- auth_headers: fixture returning Bearer token headers
"""

import subprocess
import time
import socket
from pathlib import Path
import pytest
import httpx


def get_free_port():
    """Get a free port by creating a socket and letting the OS assign one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture(scope="session")
def mock_server():
    """
    Session-scoped fixture that starts m365-sim server as a subprocess.

    - Picks a random available port
    - Starts: python server.py --port {port}
    - Waits for /health to respond (retry loop, 5s timeout)
    - Yields f"http://localhost:{port}"
    - Kills subprocess on teardown
    """
    port = get_free_port()
    url = f"http://localhost:{port}"

    # Find git root by looking for .git directory
    git_root = Path(__file__).parent.parent
    while git_root != git_root.parent and not (git_root / ".git").exists():
        git_root = git_root.parent

    # Start subprocess
    process = subprocess.Popen(
        ["python3", "server.py", "--port", str(port)],
        cwd=str(git_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready (retry loop, 5s timeout)
    start_time = time.time()
    timeout = 5
    while time.time() - start_time < timeout:
        try:
            response = httpx.get(f"{url}/health", timeout=1.0)
            if response.status_code == 200:
                break
        except (httpx.ConnectError, httpx.TimeoutException):
            time.sleep(0.1)
    else:
        # Timeout reached
        process.kill()
        raise RuntimeError(f"Server failed to start on port {port} within {timeout}s")

    yield url

    # Cleanup: kill subprocess
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture
def auth_headers():
    """Return Bearer token headers for authenticated requests."""
    return {"Authorization": "Bearer test-token"}


@pytest.fixture(scope="session")
def mock_server_hardened():
    """
    Session-scoped fixture that starts m365-sim server with hardened scenario.

    - Picks a random available port
    - Starts: python server.py --scenario hardened --port {port}
    - Waits for /health to respond (retry loop, 5s timeout)
    - Yields f"http://localhost:{port}"
    - Kills subprocess on teardown
    """
    port = get_free_port()
    url = f"http://localhost:{port}"

    # Find git root by looking for .git directory
    git_root = Path(__file__).parent.parent
    while git_root != git_root.parent and not (git_root / ".git").exists():
        git_root = git_root.parent

    # Start subprocess with hardened scenario
    process = subprocess.Popen(
        ["python3", "server.py", "--scenario", "hardened", "--port", str(port)],
        cwd=str(git_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready (retry loop, 5s timeout)
    start_time = time.time()
    timeout = 5
    while time.time() - start_time < timeout:
        try:
            response = httpx.get(f"{url}/health", timeout=1.0)
            if response.status_code == 200:
                break
        except (httpx.ConnectError, httpx.TimeoutException):
            time.sleep(0.1)
    else:
        # Timeout reached
        process.kill()
        raise RuntimeError(f"Server failed to start on port {port} within {timeout}s")

    yield url

    # Cleanup: kill subprocess
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
