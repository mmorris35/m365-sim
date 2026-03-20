"""Tests for OSCAL Component Definition Generator."""

import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid5, NAMESPACE_DNS

import pytest


# Fixed namespace UUID for deterministic control UUIDs (same as in generator)
COMPONENT_NAMESPACE = uuid5(NAMESPACE_DNS, "m365-sim.example.com")


@pytest.fixture
def component_definition():
    """Load the generated component definition."""
    oscal_file = Path(__file__).parent.parent / "oscal" / "component-definition.json"
    with open(oscal_file) as f:
        data = json.load(f)
    return data["component-definition"]


def test_generate_component_definition():
    """Test that generator produces valid JSON with required structure."""
    with TemporaryDirectory() as tmpdir:
        output_file = Path(tmpdir) / "test-output.json"
        result = subprocess.run(
            ["python3", "oscal/generate_component_definition.py",
             "--output", str(output_file)],
            cwd=Path(__file__).parent.parent,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Generator failed: {result.stderr}"
        assert output_file.exists(), "Output file not created"

        with open(output_file) as f:
            data = json.load(f)

        assert "component-definition" in data
        cd = data["component-definition"]
        assert "uuid" in cd
        assert "metadata" in cd
        assert "components" in cd


def test_oscal_metadata(component_definition):
    """Test that metadata has required fields."""
    metadata = component_definition["metadata"]
    assert metadata["title"] == "m365-sim Graph API Simulation Platform"
    assert metadata["version"] == "1.0.0"
    assert metadata["oscal-version"] == "1.1.2"
    assert "last-modified" in metadata
    assert "T" in metadata["last-modified"]


def test_oscal_component_type(component_definition):
    """Test that component type is software."""
    components = component_definition["components"]
    assert len(components) > 0
    component = components[0]
    assert component["type"] == "software"
    assert component["title"] == "m365-sim"
    assert "description" in component
    assert "CMMC 2.0 L2" in component["description"]


def test_oscal_implemented_requirements_count(component_definition):
    """Test that at least 12 requirements are defined."""
    components = component_definition["components"]
    assert len(components) > 0
    control_impl = components[0]["control-implementations"][0]
    requirements = control_impl["implemented-requirements"]
    assert len(requirements) >= 12, f"Expected at least 12 requirements, got {len(requirements)}"


def test_oscal_control_ids_valid(component_definition):
    """Test that all control-ids follow pattern xx.l2-3.x.x."""
    components = component_definition["components"]
    control_impl = components[0]["control-implementations"][0]
    requirements = control_impl["implemented-requirements"]
    import re
    control_id_pattern = re.compile(r"^[a-z]{2}\.l2-3\.\d+\.\d+$")
    for req in requirements:
        control_id = req["control-id"]
        assert control_id_pattern.match(control_id), f"Invalid control-id format: {control_id}"


def test_oscal_graph_endpoints_valid(component_definition):
    """Test that all graph-endpoint props start with /v1.0/."""
    components = component_definition["components"]
    control_impl = components[0]["control-implementations"][0]
    requirements = control_impl["implemented-requirements"]
    for req in requirements:
        props = req.get("props", [])
        endpoints = [p["value"] for p in props if p.get("name") == "graph-endpoint"]
        assert len(endpoints) > 0, f"Requirement {req['control-id']} has no graph-endpoint prop"
        for endpoint in endpoints:
            assert endpoint.startswith("/v1.0/"), f"Endpoint {endpoint} does not start with /v1.0/"


def test_oscal_deterministic_uuids():
    """Test that running generator twice produces identical UUIDs."""
    with TemporaryDirectory() as tmpdir:
        file1 = Path(tmpdir) / "gen1.json"
        file2 = Path(tmpdir) / "gen2.json"
        subprocess.run(["python3", "oscal/generate_component_definition.py", "--output", str(file1)],
            cwd=Path(__file__).parent.parent, check=True, capture_output=True)
        subprocess.run(["python3", "oscal/generate_component_definition.py", "--output", str(file2)],
            cwd=Path(__file__).parent.parent, check=True, capture_output=True)
        with open(file1) as f1, open(file2) as f2:
            data1 = json.load(f1)
            data2 = json.load(f2)
        cd1 = data1["component-definition"]
        cd2 = data2["component-definition"]
        assert cd1["uuid"] == cd2["uuid"], "Component-definition UUID not deterministic"
        comp1 = cd1["components"][0]
        comp2 = cd2["components"][0]
        assert comp1["uuid"] == comp2["uuid"], "Component UUID not deterministic"
        reqs1 = comp1["control-implementations"][0]["implemented-requirements"]
        reqs2 = comp2["control-implementations"][0]["implemented-requirements"]
        for r1, r2 in zip(reqs1, reqs2):
            assert r1["uuid"] == r2["uuid"], f"UUID mismatch for {r1['control-id']}"


def test_oscal_covers_all_control_families(component_definition):
    """Test that control families AC, IA, MP, CM, SC, AU are all present."""
    components = component_definition["components"]
    control_impl = components[0]["control-implementations"][0]
    requirements = control_impl["implemented-requirements"]
    families = set()
    for req in requirements:
        control_id = req["control-id"]
        family = control_id.split(".")[0].upper()
        families.add(family)
    required_families = {"AC", "IA", "MP", "CM", "SC", "AU"}
    assert required_families.issubset(families), f"Missing control families. Have {families}, need {required_families}"


def test_oscal_requirements_have_props(component_definition):
    """Test that each requirement has required props."""
    components = component_definition["components"]
    control_impl = components[0]["control-implementations"][0]
    requirements = control_impl["implemented-requirements"]
    for req in requirements:
        assert "uuid" in req
        assert "control-id" in req
        assert "description" in req
        assert "props" in req
        props = req["props"]
        assert len(props) > 0
        prop_names = {p["name"] for p in props}
        assert "graph-endpoint" in prop_names
        assert "fixture-file" in prop_names
        assert "assessment-method" in prop_names


def test_oscal_fixture_files_valid(component_definition):
    """Test that all fixture-file props reference known files."""
    components = component_definition["components"]
    control_impl = components[0]["control-implementations"][0]
    requirements = control_impl["implemented-requirements"]
    known_fixtures = {"users.json", "me.json", "me_auth_methods.json", "conditional_access_policies.json", "auth_methods_policy.json", "managed_devices.json", "compliance_policies.json", "device_configurations.json", "secure_scores.json", "audit_sign_ins.json", "audit_directory.json", "directory_roles.json", "role_assignments.json", "information_protection_labels.json"}
    fixture_files = set()
    for req in requirements:
        props = req.get("props", [])
        files = [p["value"] for p in props if p.get("name") == "fixture-file"]
        fixture_files.update(files)
    for fixture in fixture_files:
        assert fixture in known_fixtures, f"Unknown fixture file: {fixture}"


def test_oscal_assessment_methods(component_definition):
    """Test that assessment-method is set to automated for all requirements."""
    components = component_definition["components"]
    control_impl = components[0]["control-implementations"][0]
    requirements = control_impl["implemented-requirements"]
    for req in requirements:
        props = req.get("props", [])
        methods = [p["value"] for p in props if p.get("name") == "assessment-method"]
        assert len(methods) > 0, f"Requirement {req['control-id']} has no assessment-method"
        assert all(m == "automated" for m in methods), f"Requirement {req['control-id']} has non-automated methods"


def test_oscal_control_implementation_source(component_definition):
    """Test that control-implementation source is valid OSCAL reference."""
    components = component_definition["components"]
    control_impl = components[0]["control-implementations"][0]
    source = control_impl.get("source", "")
    assert "nist.gov" in source.lower()
    assert "800-171" in source.lower()
    assert source.startswith("https://")


def test_oscal_json_is_valid(component_definition):
    """Test that the component definition is valid JSON and serializable."""
    json_str = json.dumps(component_definition)
    reloaded = json.loads(json_str)
    assert reloaded["uuid"] == component_definition["uuid"]
    assert reloaded["metadata"]["title"] == component_definition["metadata"]["title"]
