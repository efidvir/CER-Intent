"""
Unit tests for Ceragon TFS Mapper
"""
import json
import unittest

from ceragon_tfs_adapter.models import CeragonDeviceState, NetworkInterface, RadioSector
from ceragon_tfs_adapter.mapper import CeragonTFSMapper


class TestCeragonTFSMapper(unittest.TestCase):

    def setUp(self):
        self.state = CeragonDeviceState(
            device_id="AE09100255",
            node_name="ctu-96",
            model="MH-T261",
            vendor="Siklu / Ceragon",
            serial_number="AE09100255",
            hardware_rev="A0",
            software_version="3.4.0-4377-5faacf06a",
            management_ip="192.168.1.225",
            management_port=80,
            operation_mode="TU",
            uptime="00079:01:32:36",
            interfaces=[
                NetworkInterface(
                    index=101,
                    name="eth1",
                    description="eth1 RJ-45 1Gbps",
                    if_type="ethernetCsmacd",
                    speed_bps=1_000_000_000,
                    mtu=1500,
                    admin_status="up",
                    oper_status="up",
                )
            ],
            sectors=[
                RadioSector(
                    index=1,
                    admin_status="up",
                    frequency_mhz=58320.0,
                    antenna_mode="massive2",
                    mac_address="02:02:da:44:cf:24",
                )
            ]
        )

    def test_add_descriptor_generation(self):
        descriptor = CeragonTFSMapper.to_tfs_add_device_descriptor(self.state)
        
        self.assertIn("device_id", descriptor)
        self.assertIn("device_uuid", descriptor["device_id"])
        self.assertEqual(descriptor["device_endpoints"], [])
        
        # Verify connect rules only
        rules = descriptor["device_config"]["config_rules"]
        for r in rules:
            self.assertTrue(r["custom"]["resource_key"].startswith("_connect/"))

        # Verify operational rules
        op_rules = CeragonTFSMapper.to_tfs_operational_config_rules(self.state)
        op_keys = [r["custom"]["resource_key"] for r in op_rules]
        self.assertIn("/device/capabilities", op_keys)
        self.assertIn("/device/hardware_info", op_keys)
        self.assertIn("/device/operating_parameters", op_keys)


if __name__ == "__main__":
    unittest.main()
