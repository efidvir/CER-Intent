"""Unit and parity tests for the NS-3 Ceragon Functional Twin module and Python bridge."""
from __future__ import annotations

import json
import re
from pathlib import Path

from ceragon_tfs_adapter.portfolio import list_models
from ns3_ceragon.tools.tfs_to_ceragon_twin import convert, resolve

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRIB_DIR = REPO_ROOT / "ns3_ceragon" / "contrib" / "ceragon"


def test_contrib_ceragon_module_files_present() -> None:
    """Verify all required ns-3.45 contrib/ceragon files exist."""
    expected = [
        "CMakeLists.txt",
        "README.md",
        "doc/ceragon.rst",
        "model/ceragon-portfolio.h",
        "model/ceragon-portfolio.cc",
        "model/ceragon-acm.h",
        "model/ceragon-acm.cc",
        "model/ceragon-propagation.h",
        "model/ceragon-propagation.cc",
        "model/ceragon-radio-header.h",
        "model/ceragon-radio-header.cc",
        "model/ceragon-radio-channel.h",
        "model/ceragon-radio-channel.cc",
        "model/ceragon-radio-net-device.h",
        "model/ceragon-radio-net-device.cc",
        "model/ceragon-qos-queue-disc.h",
        "model/ceragon-qos-queue-disc.cc",
        "model/ceragon-oran-xhaul.h",
        "model/ceragon-oran-xhaul.cc",
        "helper/ceragon-helper.h",
        "helper/ceragon-helper.cc",
        "helper/ceragon-twin-helper.h",
        "helper/ceragon-twin-helper.cc",
        "test/ceragon-test-suite.cc",
        "examples/CMakeLists.txt",
        "examples/ceragon-portfolio-twin.cc",
        "examples/ceragon-multiband-rain.cc",
        "examples/ceragon-tsn-fronthaul.cc",
        "examples/ceragon-terragraph-mesh.cc",
        "examples/ceragon-protection-switchover.cc",
        "examples/ceragon-twin-from-file.cc",
        "examples/topologies/metro-ring.twin",
    ]
    for rel in expected:
        path = CONTRIB_DIR / rel
        assert path.is_file(), f"Missing ns-3 contrib/ceragon file: {rel}"


def test_cpp_portfolio_matches_python_adapter_catalog() -> None:
    """Verify every explicit model in ceragon_tfs_adapter.portfolio is in ceragon-portfolio.cc."""
    cpp_text = (CONTRIB_DIR / "model" / "ceragon-portfolio.cc").read_text(encoding="utf-8")
    cpp_explicit = set(re.findall(r'Spec\(\s*"([^"]+)"', cpp_text))
    python_explicit = {spec.model for spec in list_models(include_fallbacks=False)}
    assert cpp_explicit == python_explicit, (
        f"Portfolio mismatch: only in Python={python_explicit - cpp_explicit}, "
        f"only in C++={cpp_explicit - python_explicit}"
    )
    assert len(cpp_explicit) == 31
    # Verify only MH-T261 has verified = true in Spec(...)
    assert '"MH-T261"' in cpp_text
    for spec in list_models(include_fallbacks=True):
        resolved = resolve(spec.model)
        assert resolved is not None
        assert resolved[1] == spec.family


def test_cer_intent_topology_state_to_twin_generation() -> None:
    """Verify CER-Intent data/topology_state.json converts cleanly into a valid .twin specification."""
    topo_path = REPO_ROOT / "data" / "topology_state.json"
    topo = json.loads(topo_path.read_text(encoding="utf-8"))
    twin_text = convert(topo, rain=(1.0, 2.0, 80.0), auto_flows=2)
    lines = [
        ln.strip()
        for ln in twin_text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    node_lines = [ln for ln in lines if ln.startswith("node ")]
    link_lines = [ln for ln in lines if ln.startswith("link ") or ln.startswith("wire ")]
    rain_lines = [ln for ln in lines if ln.startswith("rain ")]
    assert len(node_lines) >= 8
    assert len(link_lines) >= 8
    assert rain_lines == ["rain 1 2 80"]


def test_tfs_context_to_twin_generation() -> None:
    """Verify synthetic multi-family topology dict converts cleanly into a .twin specification."""
    sample_topo = {
        "source": "TeraFlowSDN",
        "nodes": [
            {"id": "dn-sector-1", "model": "MH-N366", "x": 10, "y": 20},
            {"id": "cn-rooftop-1", "model": "MH-T261", "x": 25, "y": 20},
            {"id": "core-eband-1", "model": "IP-50EX", "x": 0, "y": 0},
            {"id": "core-dc", "model": "O-CU", "x": -10, "y": 0, "role": "core"},
            {"id": "edge-ru", "model": "O-RU", "x": 35, "y": 20, "role": "ru"},
        ],
        "links": [
            {"src": "dn-sector-1", "dst": "cn-rooftop-1", "role": "60ghz", "distance_km": 0.25},
            {"src": "dn-sector-1", "dst": "core-eband-1", "role": "eband", "distance_km": 1.8},
            {"src": "core-dc", "dst": "core-eband-1", "capacity_gbps": 25},
            {"src": "cn-rooftop-1", "dst": "edge-ru", "capacity_gbps": 10},
        ],
        "devices": {
            "core-eband-1": {
                "configs": {
                    "tsn": {"parameters": {"cycle_time_us": 500}},
                    "security": {"parameters": {}},
                }
            }
        },
    }
    twin_text = convert(sample_topo, auto_flows=1)
    assert "node dn-sector-1" in twin_text and "MH-N366" in twin_text
    assert "node cn-rooftop-1" in twin_text and "MH-T261" in twin_text
    assert "node core-eband-1" in twin_text and "IP-50EX" in twin_text
    assert "link dn-sector-1 cn-rooftop-1 model=MH-N366 distance=250" in twin_text
    assert "link dn-sector-1 core-eband-1 model=IP-50EX distance=1800" in twin_text
    assert "wire core-dc core-eband-1 rate=25Gbps" in twin_text
    assert "tsn core-eband-1 dn-sector-1 500" in twin_text
    assert "macsec 1" in twin_text
