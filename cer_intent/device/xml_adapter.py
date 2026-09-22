import os
import xml.etree.ElementTree as ET
import logging
import time
import json
from typing import Any, Dict, List, Optional
import paramiko

from cer_intent.intent_schema import DeviceConfig
from cer_intent.device.state_store import StateStore
from cer_intent.device.adapter import AdapterBase, ApplyResult

logger = logging.getLogger(__name__)

class IP50CXMLAdapter(AdapterBase):
    """
    Configures Ceragon IP-50C devices by modifying and deploying XML configuration files.
    """

    def __init__(self, state_store: StateStore):
        self._store = state_store
        
        # Load device mapping
        raw_map = os.getenv("CERAGON_DEVICE_MAP", "{}")
        try:
            self._device_map: Dict[str, str] = json.loads(raw_map)
        except json.JSONDecodeError:
            logger.warning("CERAGON_DEVICE_MAP is not valid JSON; XML adapter might fail mapping")
            self._device_map = {}

        self._user = os.getenv("CERAGON_USER", "admin")
        self._password = os.getenv("CERAGON_PASSWORD", "admin")
        self._sftp_port = int(os.getenv("CERAGON_SFTP_PORT", "22"))
        
        # XML template path defaults to Yossi workspace folder
        template = os.getenv(
            "IP50C_TEMPLATE_XML",
            "c:/CER_Intent/Yossi/IP-50C_AI_chat_configuration_tool/IP50c_default_5.xml"
        )
        output = os.getenv("IP50C_OUTPUT_DIR", "c:/CER_Intent/scratch")
        
        # Translate Windows paths for WSL/Linux compatibility
        if os.name != 'nt':
            if template.lower().startswith("c:"):
                template = "/mnt/c" + template[2:]
            if output.lower().startswith("c:"):
                output = "/mnt/c" + output[2:]
                
        self._template_path = template
        self._output_dir = output
        os.makedirs(self._output_dir, exist_ok=True)

    def _device_ip(self, device_id: str) -> Optional[str]:
        return self._device_map.get(device_id)

    def apply(self, config: DeviceConfig) -> ApplyResult:
        logger.info(f"[XML] Applying {config.config_type} config to {config.device_id}")

        if not os.path.exists(self._template_path):
            msg = f"Template XML file not found at {self._template_path}"
            logger.error(msg)
            return ApplyResult(device_id=config.device_id, success=False, message=msg)

        try:
            # 1. Parse base XML
            tree = ET.parse(self._template_path)
            root = tree.getroot()

            # 2. Modify XML parameters based on config_type
            modified = False
            if config.config_type == "radio":
                # Frequencies, power, scripts
                mrmc_script_id = config.parameters.get("mrmc_script_id")
                tx_power = config.parameters.get("tx_power_dbm")
                tx_freq = config.parameters.get("tx_frequency")
                rx_freq = config.parameters.get("rx_frequency")

                # Iterate through RADIO type interfaces
                for interface in root.findall(".//Interface[@type='RADIO']"):
                    if mrmc_script_id is not None:
                        param = interface.find("./Param[@id='MRMC_SCRIPT']")
                        if param is not None:
                            param.set("value", str(mrmc_script_id))
                            param.set("displayValue", f"Script: {mrmc_script_id}")
                            modified = True
                    
                    if tx_power is not None:
                        param = interface.find("./Param[@id='TX_LEVEL']")
                        if param is not None:
                            param.set("value", str(tx_power))
                            param.set("displayValue", str(tx_power))
                            modified = True

                    if tx_freq is not None:
                        param = interface.find("./Param[@id='TX_FREQUENCY']")
                        if param is not None:
                            param.set("value", str(tx_freq))
                            modified = True

                    if rx_freq is not None:
                        param = interface.find("./Param[@id='RX_FREQUENCY']")
                        if param is not None:
                            param.set("value", str(rx_freq))
                            modified = True

            elif config.config_type == "qos":
                # Standard QoS / classification parameters
                qos_mode = config.parameters.get("qos_mode", "0")
                for qos in root.findall(".//QOS"):
                    param = qos.find("./Classification/Table/Param[@id='QOS_MODE']")
                    if param is not None:
                        param.set("value", str(qos_mode))
                        modified = True

            # 3. Write modified XML locally
            out_filename = f"config_{config.device_id}_{int(time.time())}.xml"
            out_path = os.path.join(self._output_dir, out_filename)
            tree.write(out_path, encoding="utf-8", xml_declaration=True)
            logger.info(f"[XML] Wrote modified XML to {out_path}")

            # 4. Update in-memory state store
            self._store.update_device_config(
                device_id=config.device_id,
                config_type=config.config_type,
                parameters=config.parameters,
                intent_id=config.intent_id,
                yang_xml=config.yang_xml,
            )

            # 5. Optional SFTP upload to physical device if mapped
            ip = self._device_ip(config.device_id)
            sftp_status = "Saved locally"
            if ip:
                logger.info(f"[XML] Deploying to device {config.device_id} at {ip}")
                try:
                    ssh = paramiko.SSHClient()
                    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    ssh.connect(ip, port=self._sftp_port, username=self._user, password=self._password, timeout=5)
                    sftp = ssh.open_sftp()
                    # Upload configuration to CeraOS import directory
                    remote_path = f"/flash/config.xml"
                    sftp.put(out_path, remote_path)
                    sftp.close()
                    ssh.close()
                    sftp_status = f"Deployed via SFTP to {ip}:{remote_path}"
                    logger.info(f"[XML] Successfully uploaded to {ip}")
                except Exception as ex:
                    sftp_status = f"Saved locally (SFTP failed: {str(ex)})"
                    logger.warning(f"[XML] SFTP upload to {ip} failed: {ex}")

            return ApplyResult(
                device_id=config.device_id,
                success=True,
                message=f"XML config applied — {sftp_status}",
                response_data={"xml_file": out_path, "modified": modified}
            )

        except Exception as e:
            msg = f"Failed to apply XML configuration: {str(e)}"
            logger.exception(msg)
            return ApplyResult(device_id=config.device_id, success=False, message=msg)

    def get_state(self, device_id: str) -> Dict[str, Any]:
        # Twinning state - loads config parameters directly from base XML template if available
        state = self._store.get_device_state(device_id)
        if not state:
            state = {"device_id": device_id, "configs": {}}
        
        # Load live parameters from template XML to populate dashboard state
        if os.path.exists(self._template_path):
            try:
                tree = ET.parse(self._template_path)
                root = tree.getroot()
                interfaces = []
                for interface in root.findall(".//Interface[@type='RADIO']"):
                    if_id = interface.get("id")
                    mrmc = interface.find("./Param[@id='MRMC_SCRIPT']")
                    tx_pwr = interface.find("./Param[@id='TX_LEVEL']")
                    tx_freq = interface.find("./Param[@id='TX_FREQUENCY']")
                    rx_freq = interface.find("./Param[@id='RX_FREQUENCY']")
                    
                    interfaces.append({
                        "interface_id": if_id,
                        "mrmc_script_id": mrmc.get("value") if mrmc is not None else None,
                        "tx_power_dbm": tx_pwr.get("value") if tx_pwr is not None else None,
                        "tx_frequency": tx_freq.get("value") if tx_freq is not None else None,
                        "rx_frequency": rx_freq.get("value") if rx_freq is not None else None,
                    })
                state["radio_interfaces"] = interfaces
            except Exception as e:
                logger.warning(f"Failed to twin device state from XML: {e}")
                
        return state
