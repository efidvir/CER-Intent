import sys
sys.path.insert(0, '/var/teraflow')
import json
from context.service.database.Engine import Engine
from context.service.database.models._Base import _Base
eng = Engine.get_engine()
Engine.create_database(eng)
_Base.metadata.create_all(eng)

from google.protobuf.json_format import ParseDict
from common.proto.context_pb2 import Context, Topology, Device, Link
from context.client.ContextClient import ContextClient

with open('/tmp/descriptors.json') as f:
    data = json.load(f)

c = ContextClient(host='127.0.0.1', port=1010)
c.connect()
for ctx in data.get('contexts', []):
    c.SetContext(ParseDict(ctx, Context(), ignore_unknown_fields=True))
for topo in data.get('topologies', []):
    c.SetTopology(ParseDict(topo, Topology(), ignore_unknown_fields=True))
for dev in data.get('devices', []):
    dev['device_drivers'] = []
    c.SetDevice(ParseDict(dev, Device(), ignore_unknown_fields=True))
for lnk in data.get('links', []):
    c.SetLink(ParseDict(lnk, Link(), ignore_unknown_fields=True))
print('SUCCESSFULLY_LOADED:', len(data.get('devices', [])), 'devices,', len(data.get('links', [])), 'links')
