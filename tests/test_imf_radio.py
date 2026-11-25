"""The intent manager's radio screen: the twin's ACM table and the ITU-R rain statistics."""
from __future__ import annotations

import math

import pytest

from cer_intent.imf import radio


def test_p838_coefficients_at_60_ghz_match_the_recommendation():
    k, a = radio.p838(60.0)
    assert (round(k, 4), round(a, 4)) == (0.8606, 0.7656)
    kv, av = radio.p838(60.0, vertical=True)
    assert (round(kv, 4), round(av, 4)) == (0.8515, 0.7486)
    assert radio.specific_attenuation(60.0, 0) == 0.0


def test_p530_exceedance_is_one_at_001_percent_and_falls_with_p():
    for f in (20.0, 60.0, 80.0):
        assert radio.exceedance_ratio(0.01, f) == pytest.approx(1.0, abs=0.02)
        assert radio.exceedance_ratio(0.001, f) > 1.0 > radio.exceedance_ratio(0.1, f)
    c1, c2, c3 = radio._coeffs(60.0)
    c0 = 0.12 + 0.4 * math.log10(6.0) ** 0.8
    assert c2 == pytest.approx(0.855 * c0 + 0.546 * (1 - c0))
    assert radio.distance_factor(0.25, 60.48, 42.0, 0.7656) == 2.5     # short hops: capped


def test_payload_follows_the_twins_acm_table():
    assert radio.capacity_mbps("MCS7") == 770.0 and radio.capacity_mbps("MCS8") == 924.0
    assert radio.capacity_mbps("MCS10") == 1000.0                        # the port
    assert radio.mcs_for_load(700) == "MCS7" and radio.mcs_for_load(5000) is None
    assert radio.needed_mcs(100, "MCS4") == "MCS4"


def test_the_demo_hop_holds_mcs10_clear_and_mcs7_in_design_rain_as_the_twin_does():
    hop = radio.Hop("radio-1", "radio-2")
    assert hop.mcs(0) == "MCS10" and hop.mcs(60) == "MCS7"
    assert hop.capacity(60) == 770.0


def test_availability_falls_as_the_needed_modulation_rises():
    hop = radio.Hop("radio-1", "radio-2")
    avs = [hop.availability(f"MCS{i}")["availability_pct"] for i in range(3, 11)]
    assert avs == sorted(avs, reverse=True)
    a7 = hop.availability("MCS7")
    assert 99.95 < a7["availability_pct"] < 99.99 and a7["method"].startswith("ITU-R")
    assert radio.availability_for(hop, 5000)["availability_pct"] == 0.0
    assert radio.pct(99.9783) == "99.978 %"
