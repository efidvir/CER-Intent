import sys
import json
sys.path.extend(['/home/webui/teraflow', '/var/teraflow'])
from google.protobuf.json_format import ParseDict

from context.client.ContextClient import ContextClient
from common.proto.context_pb2 import (
    Context, Topology, Device, Link, Slice, Service,
    ContextId, TopologyId, DeviceId, LinkId, Empty
)

def main():
    print("=== Loading 6G Transport Topology into TeraFlowSDN Context ===")
    client = ContextClient()
    client.connect()

    with open('/tmp/6g_transport_tfs_descriptors.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 1. Define Context admin
    ctx_admin_uuid = "43813baf-195e-5da6-af20-b3d0922e71a7"
    topo_admin_uuid = "c76135e3-24a8-5e92-9bed-c3c9139359c8"
    topo_6g_uuid = "687be284-4ab9-55e7-a311-a132710064be"

    ctx = Context()
    ctx.context_id.context_uuid.uuid = ctx_admin_uuid
    ctx.name = "admin"
    client.SetContext(ctx)
    print(" [+] Context 'admin' created/updated.")

    # 2. Define Initial Topologies
    topo_admin = Topology()
    topo_admin.topology_id.context_id.context_uuid.uuid = ctx_admin_uuid
    topo_admin.topology_id.topology_uuid.uuid = topo_admin_uuid
    topo_admin.name = "admin"
    client.SetTopology(topo_admin)
    print(" [+] Topology 'admin' registered.")

    topo_6g = Topology()
    topo_6g.topology_id.context_id.context_uuid.uuid = ctx_admin_uuid
    topo_6g.topology_id.topology_uuid.uuid = topo_6g_uuid
    topo_6g.name = "6g-transport"
    client.SetTopology(topo_6g)
    print(" [+] Topology '6g-transport' registered.")

    # 3. Load Devices
    devices = data.get('devices', [])
    print(f" [*] Loading {len(devices)} Devices...")
    dev_ids = []
    for d in devices:
        dev = Device()
        ParseDict(d, dev)
        client.SetDevice(dev)
        dev_ids.append(dev.device_id)
    print(f" [+] Successfully loaded {len(devices)} Devices.")

    # 4. Load Links
    links = data.get('links', [])
    print(f" [*] Loading {len(links)} Links...")
    link_ids = []
    for l in links:
        link = Link()
        ParseDict(l, link)
        client.SetLink(link)
        link_ids.append(link.link_id)
    print(f" [+] Successfully loaded {len(links)} Links.")

    # 5. Associate all devices and links with BOTH topologies (admin and 6g-transport)
    print(" [*] Associating devices and links with topologies...")
    for t_uuid, t_name in [(topo_admin_uuid, "admin"), (topo_6g_uuid, "6g-transport")]:
        t = Topology()
        t.topology_id.context_id.context_uuid.uuid = ctx_admin_uuid
        t.topology_id.topology_uuid.uuid = t_uuid
        t.name = t_name
        for did in dev_ids:
            t.device_ids.add().CopyFrom(did)
        for lid in link_ids:
            t.link_ids.add().CopyFrom(lid)
        client.SetTopology(t)
        print(f" [+] Associated {len(dev_ids)} devices & {len(link_ids)} links with Topology '{t_name}'.")

    # 6. Verification
    print("\n=== Verification ===")
    contexts = client.ListContexts(Empty())
    for c in contexts.contexts:
        print(f" Context: {c.name} ({c.context_id.context_uuid.uuid})")
        topos = client.ListTopologies(c.context_id)
        for topo in topos.topologies:
            t_detail = client.GetTopologyDetails(topo.topology_id)
            print(f"   |-- Topology: {topo.name} ({topo.topology_id.topology_uuid.uuid})")
            print(f"       |-- Devices: {len(t_detail.devices)}")
            print(f"       +-- Links:   {len(t_detail.links)}")

    print("\nAll 6G transport devices and links are now successfully active in TFS Context!")

if __name__ == '__main__':
    main()
