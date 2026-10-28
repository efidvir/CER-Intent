"""
Unit tests for the Ceragon portfolio catalog and its use by the mapper / driver.
"""
import json
import unittest
from unittest import mock

from ceragon_tfs_adapter.config import AdapterConfig
from ceragon_tfs_adapter.driver import TFSCeragonDriver, config_type_from_key
from ceragon_tfs_adapter.mapper import CeragonTFSMapper
from ceragon_tfs_adapter.models import CeragonDeviceState, NetworkInterface, RadioSector
from ceragon_tfs_adapter.portfolio import (
    FLAVOR_CERAOS, FLAVOR_SIKLU_EH, FLAVOR_SIKLU_TG,
    check_config_support, list_families, list_models, resolve_model,
)


def _state(model: str, freq_mhz: float, serial: str = "SN1") -> CeragonDeviceState:
    return CeragonDeviceState(
        device_id=serial, node_name="n1", model=model, vendor="Ceragon", serial_number=serial,
        hardware_rev="A", software_version="x", management_ip="10.0.0.1", management_port=80,
        operation_mode="x", uptime="x",
        interfaces=[NetworkInterface(1, "eth1", "eth1", "ethernetCsmacd", 10_000_000_000, 1500, "up", "up")],
        sectors=[RadioSector(1, "up", freq_mhz, "fixed")],
    )


class TestPortfolioResolution(unittest.TestCase):

    def test_every_catalog_model_and_alias_resolves_to_itself(self):
        for spec in list_models():
            self.assertIs(resolve_model(spec.model), spec, spec.model)
            for alias in spec.aliases:
                self.assertIs(resolve_model(alias), spec, alias)

    def test_vendor_string_normalisation(self):
        cases = {
            "FibeAir IP20C": "IP-20C",
            "ip_50cx": "IP-50CX",
            "Ceragon IP-50EXA": "IP-50EXA",
            "Siklu EtherHaul-8010FX": "EH-8010FX",
            "EtherHaul 8020": "EH-8020FX",
            "Ceragon-MH-T261-ctu-96": "MH-T261",
            "ceragon-mh-t261-ctu-96": "MH-T261",
            "MultiHaul TG N366": "MH-N366",
            "IP-20 Evolution LH": "IP-20A-LH",
            "IP-20C-HP": "IP-20C-HP",
            "IP-100E": "IP-100E",
        }
        for raw, expected in cases.items():
            spec = resolve_model(raw)
            self.assertIsNotNone(spec, raw)
            self.assertEqual(spec.model, expected, raw)
            self.assertFalse(spec.is_family_fallback, raw)

    def test_longest_prefix_wins(self):
        self.assertEqual(resolve_model("IP-50CXB").model, "IP-50CX")

    def test_unknown_variants_fall_back_to_family(self):
        cases = {"IP-50ZZZ9": "IP-50", "IP-20Q": "IP-20", "IP-100FR2": "IP-100",
                 "EH-9999FX": "EtherHaul", "MH-N999": "MultiHaul TG"}
        for raw, fam in cases.items():
            spec = resolve_model(raw)
            self.assertIsNotNone(spec, raw)
            self.assertTrue(spec.is_family_fallback, raw)
            self.assertEqual(spec.family, fam, raw)
            self.assertFalse(spec.api_verified, raw)

    def test_non_ceragon_nodes_do_not_resolve(self):
        for raw in ("node-A", "oran-cu1", "Core-DC", "O-RU", "Generic", "", None):
            self.assertIsNone(resolve_model(raw), raw)

    def test_every_family_has_fallback_and_flavor(self):
        flavors = {FLAVOR_CERAOS, FLAVOR_SIKLU_EH, FLAVOR_SIKLU_TG}
        self.assertEqual(set(list_families()), {"IP-20", "IP-50", "IP-100", "EtherHaul", "MultiHaul TG"})
        for spec in list_models(include_fallbacks=True):
            self.assertIn(spec.api_flavor, flavors)
            self.assertIn(spec.protocol, ("terragraph", "ceraos"))
            self.assertTrue(spec.bands)

    def test_only_lab_device_is_marked_verified(self):
        verified = [s.model for s in list_models(include_fallbacks=True) if s.api_verified]
        self.assertEqual(verified, ["MH-T261"])


class TestCapabilityGating(unittest.TestCase):

    def test_hard_requirements(self):
        self.assertFalse(check_config_support(resolve_model("IP-20C"), "beamforming")[0])
        self.assertTrue(check_config_support(resolve_model("MH-N366"), "beamforming")[0])
        self.assertFalse(check_config_support(resolve_model("EH-8010FX"), "multiband")[0])
        self.assertTrue(check_config_support(resolve_model("IP-50EX"), "multiband")[0])
        self.assertFalse(check_config_support(resolve_model("IP-20S"), "interference")[0])
        self.assertTrue(check_config_support(resolve_model("IP-50C"), "interference")[0])
        self.assertTrue(check_config_support(None, "beamforming")[0])

    def test_driver_rejects_unsupported_and_out_of_band(self):
        drv = TFSCeragonDriver(AdapterConfig(device_ip="127.0.0.9", model_hint="IP-20C"))
        drv._cached_state = _state("IP-20C", 23000.0)
        with mock.patch.object(drv.client, "apply_radio_tuning", return_value=(True, "ok")) as tune:
            res = drv.set_config([
                ("/interface[name=node-x]/beamforming", json.dumps({"steer_azimuth_deg": 15})),
                ("/device/operating_parameters", json.dumps({"frequency_mhz": 60480})),
                ("/device/operating_parameters", json.dumps({"frequency_mhz": 18000})),
            ])
        self.assertFalse(res[0][1]); self.assertIn("beamforming", res[0][2])
        self.assertFalse(res[1][1]); self.assertIn("outside IP-20C", res[1][2])
        self.assertTrue(res[2][1])
        tune.assert_called_once()

    def test_config_type_from_key(self):
        self.assertEqual(config_type_from_key("/interface[name=ceragon-mh-t261-ctu-96]/beamforming"), "beamforming")
        self.assertIsNone(config_type_from_key("/device/operating_parameters"))


class TestMapperUsesPortfolio(unittest.TestCase):

    def test_endpoint_types_and_capabilities_follow_model(self):
        expectations = {
            ("IP-20C", 23000.0): ("radio-mw", "transport_microwave"),
            ("IP-50E", 73500.0): ("radio-e-band", "transport_mmwave_eband"),
            ("EH-8010FX", 73500.0): ("radio-e-band", "transport_mmwave_eband"),
            ("MH-T261", 58320.0): ("radio-v-band", "transport_mmwave_vband"),
            ("IP-50FX", 23000.0): ("radio-mw", "transport_nodal_aggregation"),
        }
        for (model, freq), (ep_type, role) in expectations.items():
            st = _state(model, freq, serial=f"SN-{model}")
            desc = CeragonTFSMapper.to_tfs_add_device_descriptor(st)
            settings = json.loads(next(r for r in desc["device_config"]["config_rules"]
                                       if r["custom"]["resource_key"] == "_connect/settings")["custom"]["resource_value"])
            rf = [e for e in settings["endpoints"] if "rf-sector" in e["name"]]
            self.assertEqual(rf[0]["type"], ep_type, model)
            caps = json.loads(next(r for r in CeragonTFSMapper.to_tfs_operational_config_rules(st)
                                   if r["custom"]["resource_key"] == "/device/capabilities")["custom"]["resource_value"])
            self.assertEqual(caps["model"], model)
            self.assertEqual(caps["role"], role)
            self.assertEqual(caps["beamforming"], model.startswith("MH-"))

    def test_multiband_carrier_endpoint_uses_carrier_band(self):
        st = _state("IP-50EX", 18000.0)
        desc = CeragonTFSMapper.to_tfs_add_device_descriptor(st)
        settings = json.loads(desc["device_config"]["config_rules"][2]["custom"]["resource_value"])
        self.assertEqual([e for e in settings["endpoints"] if "rf-sector" in e["name"]][0]["type"], "radio-mw")

    def test_unknown_model_does_not_claim_60ghz(self):
        st = _state("SomeOtherRadio", 23000.0)
        caps = json.loads(CeragonTFSMapper.to_tfs_operational_config_rules(st)[0]["custom"]["resource_value"])
        self.assertEqual(caps["catalog_match"], "none")
        self.assertNotIn("beamforming", caps)


if __name__ == "__main__":
    unittest.main()
