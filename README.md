# m365-sim

Drop-in Microsoft Graph API mock server for testing. Returns realistic JSON fixtures for 50+ endpoints across 3 cloud targets and 3 scenarios.

## Use This Instead of Real M365

Point your Graph API client at `http://localhost:8888` instead of `https://graph.microsoft.com`. That's it.

### What to Change in Your Project

1. **Base URL**: Replace `https://graph.microsoft.com` with `http://localhost:8888`
2. **Auth token**: Use any string — `Bearer test` works. The server accepts any Bearer token without validation.
3. **No other changes needed.** Responses match real Graph API shapes exactly (`@odata.context`, `value` arrays, singleton objects).

### Start the Server

```bash
# Clone and run (one-time setup)
cd ~/github/m365-sim
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python server.py --port 8888

# Or with Docker
docker build -t m365-sim .
docker run -d -p 8888:8888 m365-sim
```

### Pick Your Scenario

| Flag | What You Get |
|------|-------------|
| `--scenario greenfield` | Fresh tenant, zero controls (default) |
| `--scenario hardened` | Full CMMC posture: 8 CA policies, FIDO2, compliant devices |
| `--scenario partial` | Mid-deployment: 3 CA policies, partial auth |
| `--cloud gcc-moderate` | `graph.microsoft.com`, Contoso Defense LLC (default) |
| `--cloud gcc-high` | `graph.microsoft.us`, Contoso Defense Federal LLC |
| `--cloud commercial-e5` | `graph.microsoft.com`, Contoso Corp |

```bash
python server.py --scenario hardened --cloud gcc-high --port 8888
```

### Quick Test

```bash
# Health check (no auth)
curl http://localhost:8888/health

# Get users
curl -H "Authorization: Bearer test" http://localhost:8888/v1.0/users

# Get users via beta API
curl -H "Authorization: Bearer test" http://localhost:8888/beta/users

# Filter
curl -H "Authorization: Bearer test" "http://localhost:8888/v1.0/users?\$filter=userType eq 'Member'"

# Simulate throttling
curl -H "Authorization: Bearer test" "http://localhost:8888/v1.0/users?mock_status=429"
```

### Stateful Mode (Deploy-Then-Verify)

```bash
python server.py --stateful --port 8888
```

POST/PATCH now mutate state. `POST /v1.0/_reset` restores baseline.

## Full Documentation

See [docs/guide.md](docs/guide.md) for the complete endpoint list, query parameter support ($filter, $expand, $top), write operations, error simulation, Docker Compose setup, and runtime overrides.
