import json

nodes = []
links = []

def add_node(nid, name, role, model, sector, x, y, cap=10.0):
    nodes.append({
        "id": nid, "name": name, "role": role, "model": model, 
        "sector": sector, "x": round(x), "y": round(y), "max_throughput_gbps": cap
    })

def add_link(lid, src, dst, role="mw", cap=10.0, dist=2.0, degrade=False):
    links.append({
        "id": lid, "src": src, "dst": dst, "role": role,
        "capacity_gbps": cap, "distance_km": dist, "status": "degraded" if degrade else "active"
    })

# --- LAYER 1: AGGREGATION RING (IP-50FX) ---
agg_coords = [(400, 300), (600, 300), (600, 500), (400, 500)]
for i, (x, y) in enumerate(agg_coords):
    add_node(f"mw-agg-{i+1}", f"Agg Node {i+1}", "transport", "IP-50FX", f"core-{i}", x, y, 10.0)

for i in range(4):
    add_link(f"mw-ring-{i+1}", f"mw-agg-{i+1}", f"mw-agg-{(i+1)%4+1}", "mw", 10.0, 5.0)

# O-RAN drops on Agg Ring
add_node("oran-core", "5G Core", "oran", "Core-DC", "core-0", 300, 200, 100.0)
add_link("eth-core", "oran-core", "mw-agg-1", "ethernet", 100.0, 0.1)

add_node("oran-cu1", "CU-NE", "oran", "O-CU", "core-1", 700, 200, 10.0)
add_link("eth-cu1", "oran-cu1", "mw-agg-2", "ethernet", 10.0, 0.1)

add_node("oran-cu2", "CU-SE", "oran", "O-CU", "core-2", 700, 600, 10.0)
add_link("eth-cu2", "oran-cu2", "mw-agg-3", "ethernet", 10.0, 0.1)

add_node("oran-cu3", "CU-SW", "oran", "O-CU", "core-3", 300, 600, 10.0)
add_link("eth-cu3", "oran-cu3", "mw-agg-4", "ethernet", 10.0, 0.1)


# --- LAYER 2: EDGE HUBS (IP-20N) ---
hub_coords = [(250, 300), (750, 300), (750, 500), (250, 500)]
for i, (x, y) in enumerate(hub_coords):
    hid = f"mw-hub-{i+1}"
    add_node(hid, f"Hub Node {i+1}", "transport", "IP-20N", f"sector-{i+1}", x, y, 5.0)
    add_link(f"mw-branch-{i+1}", f"mw-agg-{i+1}", hid, "mw", 5.0, 3.0)
    
    # O-RAN DU drops
    did = f"oran-du{i+1}"
    dx = x - 70 if x < 500 else x + 70
    add_node(did, f"DU-{i+1}", "oran", "O-DU", f"sector-{i+1}", dx, y, 10.0)
    add_link(f"eth-du{i+1}", did, hid, "ethernet", 10.0, 0.1)


# --- LAYER 3: TAIL SITES (IP-20C) ---
# Each hub gets 2 tails bridging out vertically/diagonally
tail_offsets = [
    # Hub 1 (Top Left)
    [(-50, -100), (50, -100)],
    # Hub 2 (Top Right)
    [(-50, -100), (50, -100)],
    # Hub 3 (Bottom Right)
    [(-50, 100), (50, 100)],
    # Hub 4 (Bottom Left)
    [(-50, 100), (50, 100)]
]

tail_cnt = 1
for i, (hx, hy) in enumerate(hub_coords):
    for ox, oy in tail_offsets[i]:
        tx, ty = hx + ox, hy + oy
        tid = f"mw-tail-{tail_cnt}"
        add_node(tid, f"Tail {tail_cnt}", "transport", "IP-20C", f"sector-{i+1}", tx, ty, 2.5)
        add_link(f"mw-tail-link-{tail_cnt}", f"mw-hub-{i+1}", tid, "mw", 2.5, 1.5)
        
        # O-RAN RU drops further out
        rx = tx + (ox // 2)
        ry = ty + (oy // 2)
        rid = f"oran-ru{tail_cnt}"
        add_node(rid, f"RU-{tail_cnt}", "oran", "O-RU", f"sector-{i+1}", rx, ry, 2.5)
        add_link(f"eth-ru{tail_cnt}", rid, tid, "ethernet", 2.5, 0.1)
        tail_cnt += 1

data = {"nodes": nodes, "links": links}
with open(r"c:\CER_Intent\scratch\topology_out.py", "w") as f:
    f.write("INITIAL_TOPOLOGY = " + json.dumps(data, indent=4))


