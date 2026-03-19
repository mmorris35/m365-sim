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
