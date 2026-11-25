"""
Builds tests/corpus/intents.jsonl: requests an operator might type, with what each should read as.

Hand-written cases cover every kind, vague and compound requests and requests outside
scope; templated cases vary verbs, word order, units and values. The corpus is a
regression set written with the reader, not a sample of real operators' language: its
scores say the reader still does what it did, not how it does on words it has not seen.

    python tests/corpus/build_corpus.py      # rewrites intents.jsonl
"""
from __future__ import annotations

import itertools
import json
import random
from pathlib import Path

OUT = Path(__file__).with_name("intents.jsonl")
R, E = "region-a", "edge"
CASES = []


def case(text, kinds, **expect):
    CASES.append({"text": text, "expect": {"kinds": kinds, **expect}})


# ── deliver ───────────────────────────────────────────────────────────────────
case("Connect region-a and edge over VLAN 300 with 500 Mbps and at most 10 ms latency; keep the radio link at MCS4 or better",
     ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 500], "latency": ["le", 10], "modulation_floor": ["ge", "MCS4"], "vlan": ["eq", 300]})
case("Routed L3VPN slice between region-a 192.0.2.1/30 and edge 198.51.100.1/30 with 50 Mbps and at most 5 ms latency; keep the radio at MCS6 or better",
     ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 50], "latency": ["le", 5], "technology": ["eq", "L3VPN"], "modulation_floor": ["ge", "MCS6"]})
case("Gold slice from region A to the edge, 300 Mbps", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 300], "availability": ["ge", 99.99]}, profile="gold")
case("I need 200 Mbps between region-a and edge", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 200]})
case("Set up a 1 Gbps link from edge to region-a", ["deliver"], endpoints=[E, R], targets={"bandwidth": ["ge", 1000]})
case("Provision half a gig between region-a and edge for video", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 500]}, profile="video")
case("Create a URLLC slice region-a to edge, 20 Mbps, 1 ms", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 20], "latency": ["le", 1]}, profile="urllc")
case("Give the edge 150 Mbps", ["deliver"], endpoints=[E, R], targets={"bandwidth": ["ge", 150]})
case("A best-effort slice from region-a to edge for 100 Mbps", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 100]}, strictness="best_effort")
case("Connect region-a and edge with 300 Mbps, latency under 8 ms and loss below 0.1%", ["deliver"], endpoints=[R, E],
     targets={"bandwidth": ["ge", 300], "latency": ["le", 8], "loss": ["le", 0.1]})
case("Bridge region-a to edge on VLAN 410, 80 Mbps", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 80], "vlan": ["eq", 410]})
case("connect region-a <-> edge 250mbps", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 250]})
case("Connect region-a and edge with 300 Mbps at 99.99% availability", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 300], "availability": ["ge", 99.99]})
case("Connect region-a and edge with 300 Mbps and four nines", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 300], "availability": ["ge", 99.99]})
case("Connect HQ and edge with 100 Mbps", ["deliver"], question="endpoint[0]")
case("Connect region-a and edge", ["deliver"], endpoints=[R, E], question="bandwidth")
case("Stadium event Saturday 18:00-23:00: north 400 Mbps, south 300 Mbps, press 100 Mbps",
     ["deliver", "deliver", "deliver"], targets={"bandwidth": ["ge", 400]}, contexts=["window"])
case("Tonight from 20:00 to 23:00 give region-a to edge an extra 200 Mbps slice", ["deliver"], endpoints=[R, E],
     targets={"bandwidth": ["ge", 200]}, contexts=["window"])
case("For the next 2 hours, a 100 Mbps slice between region-a and edge", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 100]}, contexts=["window"])
case("Platinum service from region-a to edge, 50 Mbps", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 50], "latency": ["le", 2]}, profile="platinum")
case("Voice slice region-a to edge 30 Mbps", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 30], "jitter": ["le", 5]}, profile="voice")
case("Hook up the edge to region-a with 600 Mbps, top priority", ["deliver"], endpoints=[E, R], targets={"bandwidth": ["ge", 600]}, priority=8)
case("Connect region-a and edge, 300 Mbps, called cctv-feed", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 300]}, name="cctv-feed")
case("Connect region-a and edge over VLAN 100 with 50 Mbps", ["deliver"], endpoints=[R, E], question="vlan")
case("New slice from regiona to edge with 120 Mbps", ["deliver"], endpoints=[R, E], targets={"bandwidth": ["ge", 120]})

# ── change ────────────────────────────────────────────────────────────────────
case("Double the backhaul tonight 20:00-23:00, then restore it", ["change"], ids=["backhaul-ran"], action="scale",
     targets={"bandwidth": ["ge", 400]}, contexts=["window"], revert=True)
case("Increase backhaul-ran to 300 Mbps", ["change"], ids=["backhaul-ran"], targets={"bandwidth": ["ge", 300]})
case("Add 100 Mbps to the backhaul", ["change"], ids=["backhaul-ran"], action="add", targets={"bandwidth": ["ge", 300]})
case("Halve the RAN backhaul", ["change"], ids=["backhaul-ran"], action="scale", targets={"bandwidth": ["ge", 100]})
case("Bump backhaul-ran by 50%", ["change"], ids=["backhaul-ran"], targets={"bandwidth": ["ge", 300]})
case("Move backhaul-ran to VLAN 320", ["change"], ids=["backhaul-ran"], action="set", targets={"vlan": ["eq", 320]})
case("Set the backhaul's modulation floor to MCS6", ["change"], ids=["backhaul-ran"], targets={"modulation_floor": ["ge", "MCS6"]})
case("Make the RAN backhaul faster", ["change"], ids=["backhaul-ran"], question="improve")
case("Improve the backhaul", ["change"], ids=["backhaul-ran"], question="improve")
case("Lower the backhaul's latency to 3 ms", ["change"], ids=["backhaul-ran"], targets={"latency": ["le", 3]})
case("Change backhaul-ran to 250 Mbps during business hours", ["change"], ids=["backhaul-ran"], targets={"bandwidth": ["ge", 250]}, contexts=["window"])
case("Raise the backhaul by 0.1 Gbps", ["change"], ids=["backhaul-ran"], targets={"bandwidth": ["ge", 300]})

# ── lifecycle ─────────────────────────────────────────────────────────────────
case("Suspend the backhaul", ["lifecycle"], ids=["backhaul-ran"], action="suspend")
case("Pause backhaul-ran until tomorrow", ["lifecycle"], ids=["backhaul-ran"], action="suspend")
case("Resume the RAN backhaul", ["lifecycle"], ids=["backhaul-ran"], action="resume")
case("Remove backhaul-ran", ["lifecycle"], ids=["backhaul-ran"], action="delete")
case("Tear down the backhaul slice", ["lifecycle"], ids=["backhaul-ran"], action="delete")
case("Delete every slice except the backhaul", ["lifecycle"], action="delete")
case("Turn off backhaul-ran tonight", ["lifecycle"], ids=["backhaul-ran"], action="suspend", contexts=["window"])
case("Decommission the backhaul", ["lifecycle"], ids=["backhaul-ran"], action="delete")

# ── keep ──────────────────────────────────────────────────────────────────────
case("Never let the backhaul drop below 150 Mbps; take it from best effort first", ["keep"], ids=["backhaul-ran"],
     targets={"bandwidth": ["ge", 150]}, shed="best_effort")
case("Keep backhaul-ran under 5 ms latency at all times", ["keep"], ids=["backhaul-ran"], targets={"latency": ["le", 5]})
case("Make sure the backhaul stays above 99.99% availability", ["keep"], ids=["backhaul-ran"], targets={"availability": ["ge", 99.99]})
case("Keep the backhaul healthy", ["keep"], ids=["backhaul-ran"], targets={"bandwidth": ["ge", 200]})
case("Always keep the radio link at MCS4 or better", ["keep"], targets={"modulation_floor": ["ge", "MCS4"]})
case("Guarantee 200 Mbps for the backhaul even in heavy rain", ["keep"], ids=["backhaul-ran"], targets={"bandwidth": ["ge", 200]}, contexts=["weather"])
case("Don't let latency on the backhaul exceed 10 ms", ["keep"], ids=["backhaul-ran"], targets={"latency": ["le", 10]})
case("Ensure loss on backhaul-ran stays below 0.5%", ["keep"], ids=["backhaul-ran"], targets={"loss": ["le", 0.5]})

# ── optimise ──────────────────────────────────────────────────────────────────
case("Save energy on the hop at night when traffic is below 100 Mbps, keep MCS4", ["optimise"], action="minimize",
     targets={"modulation_floor": ["ge", "MCS4"]}, contexts=["window", "condition"])
case("Minimise power consumption on the radio link", ["optimise"], action="minimize")
case("Reduce energy use overnight", ["optimise"], action="minimize", contexts=["window"])
case("Go green on the radios during off-peak", ["optimise"], action="minimize", contexts=["window"])
case("Minimise latency for the backhaul", ["optimise"], action="minimize")
case("Maximise capacity on the hop", ["optimise"], action="maximize")

# ── guard ─────────────────────────────────────────────────────────────────────
case("No changes during business hours without approval", ["guard"], rule="approval", contexts=["window"])
case("Freeze all changes this weekend", ["guard"], rule="freeze", contexts=["window"])
case("Never let any hop go below MCS4", ["guard"], rule="floor", targets={"modulation_floor": ["ge", "MCS4"]})
case("Always keep 20% headroom on the radio link", ["guard"], rule="headroom", targets={"headroom": ["ge", 20]})
case("Don't touch the backhaul", ["guard"], rule="freeze", ids=["backhaul-ran"])
case("Changes to the backhaul need approval", ["guard"], rule="approval", ids=["backhaul-ran"])
case("No maintenance on the hop during peak hours", ["guard"], rule="freeze", contexts=["window"])

# ── observe ───────────────────────────────────────────────────────────────────
case("Report the lowest modulation on the radio link every hour", ["observe"], action="report", contexts=["schedule"], metric="lowest_modulation")
case("Alert me when the radio link drops below MCS6", ["observe"], action="alert", contexts=["condition"], metric="lowest_modulation")
case("Send me the backhaul's throughput every 15 minutes", ["observe"], action="report", ids=["backhaul-ran"], contexts=["schedule"], metric="throughput")
case("Notify me if latency on the backhaul goes above 8 ms", ["observe"], action="alert", ids=["backhaul-ran"], contexts=["condition"])
case("Weekly availability report for the hop", ["observe"], action="report", metric="availability")
case("Watch the backhaul's SLA", ["observe"], action="report", ids=["backhaul-ran"], metric="status")
case("Tell me when it starts raining more than 30 mm/h", ["observe"], action="alert", contexts=["weather"])

# ── explore ───────────────────────────────────────────────────────────────────
case("How much more can the hop carry in heavy rain?", ["explore"], question_type="headroom", contexts=["weather"])
case("How much headroom is left on the radio link?", ["explore"], question_type="headroom")
case("What if radio-1 fails?", ["explore"], question_type="whatif")
case("What happens if we remove the backhaul?", ["explore"], question_type="whatif")
case("Could I add 200 Mbps between region-a and edge in heavy rain?", ["explore"], question_type="feasible", targets={"bandwidth": ["ge", 200]})
case("Can the hop take another 300 Mbps?", ["explore"], targets={"bandwidth": ["ge", 300]})
case("What is the most I can add between region-a and edge?", ["explore"], question_type="headroom")
case("Simulate 100 mm/h of rain on the hop", ["explore"], question_type="whatif", contexts=["weather"])
case("Is there room for a 500 Mbps slice?", ["explore"], targets={"bandwidth": ["ge", 500]})
case("Would the backhaul survive torrential rain?", ["explore"], contexts=["weather"])

# ── ask ───────────────────────────────────────────────────────────────────────
case("What runs over radio-1?", ["ask"], question_type="inventory")
case("Which slices use the hop?", ["ask"], question_type="inventory")
case("Why is the backhaul degraded?", ["ask"], question_type="explain")
case("Show me all intents", ["ask"], question_type="list")
case("List the slices", ["ask"], question_type="list")
case("What can you do?", ["ask"], question_type="capability")
case("How is the network doing?", ["ask"], question_type="status")
case("Is the backhaul OK?", ["ask"], question_type="status")
case("What's the current capacity of the hop?", ["ask"], question_type="metric")

# ── compound ──────────────────────────────────────────────────────────────────
case("Connect region-a and edge with 300 Mbps and report its throughput every hour", ["deliver", "observe"], endpoints=[R, E])
case("Suspend the backhaul tonight 22:00-02:00, then resume it", ["lifecycle"], ids=["backhaul-ran"], contexts=["window"], revert=True)
case("Connect region-a and edge with 100 Mbps; also alert me if the hop drops below MCS5", ["deliver", "observe"], endpoints=[R, E])
case("Give region-a to edge 200 Mbps and never let it fall below 150 Mbps", ["deliver", "keep"], endpoints=[R, E])

# ── auto-approval: grants and restrictions (rule intents) ─────────────────────
case("Auto-approve deliveries up to 300 Mbps", ["guard"], rule="auto_approve", targets={"bandwidth": ["le", 300]})
case("Auto-approve slices of no more than 300 Mbps", ["guard"], rule="auto_approve", targets={"bandwidth": ["le", 300]})
case("Apply changes up to 100 Mbps without asking", ["guard"], rule="auto_approve", targets={"bandwidth": ["le", 100]})
case("Approve suspensions automatically at night", ["guard"], rule="auto_approve", contexts=["window"])
case("Never auto-approve deliveries", ["guard"], rule="approval")
case("Don't approve changes automatically", ["guard"], rule="approval")
case("Stop auto-approving slices on radio-1", ["guard"], rule="approval", ids=["radio-1"])
case("Turn off auto-approval", ["guard"], rule="approval")
case("No auto-approval for suspensions", ["guard"], rule="approval")

# ── described, not named: answered from what the network reports ─────────────
HOP = "radio-1|radio-2"
case("Double the slice on VLAN 100", ["change"], ids=["backhaul-ran"], action="scale", targets={"bandwidth": ["ge", 400]})
case("Suspend the VLAN 100 slice", ["lifecycle"], ids=["backhaul-ran"], action="suspend")
case("Keep the 200 Mbps slice under 5 ms", ["keep"], ids=["backhaul-ran"], targets={"latency": ["le", 5]})
case("Report the busiest hop every hour", ["observe"], ids=[HOP], contexts=["schedule"])
case("How is the 60 GHz link doing?", ["ask"], ids=[HOP])
case("Alert me when the hop to edge drops below MCS6", ["observe"], ids=[HOP], contexts=["condition"])
case("What is the radio at edge doing?", ["ask"], ids=["radio-2"])
case("Which slices use the V-band hop?", ["ask"], ids=[HOP])
case("What runs over the region-a hop?", ["ask"], ids=["backhaul-ran"])
case("Save energy on the V-band link at night, keep MCS4", ["optimise"], ids=[HOP], action="minimize")
case("Freeze the 60 GHz hop during peak hours", ["guard"], ids=[HOP], rule="freeze")
case("Never let the edge hop go below MCS5", ["keep"], ids=[HOP], targets={"modulation_floor": ["ge", "MCS5"]})
case("How much more can the 60 GHz hop carry?", ["explore"], ids=[HOP], question_type="headroom")
case("Remove the biggest slice", ["lifecycle"], ids=["backhaul-ran"], action="delete")
case("Give the VLAN 100 slice 50% more", ["change"], ids=["backhaul-ran"], targets={"bandwidth": ["ge", 300]})
case("Watch the hop to region-a", ["observe"], ids=[HOP])
case("Suspend every slice over radio-2", ["lifecycle"], ids=["backhaul-ran"], action="suspend")

# ── outside scope ─────────────────────────────────────────────────────────────
for t in ["Configure BGP on the core routers", "Order pizza for the NOC", "Reset my laptop password",
          "Update the firmware on the office printer", "What's the weather in Paris tomorrow?", "Write me a poem about networks",
          "Configure OSPF area 0 on the routers", "Open a ticket with the vendor's support desk", "Book a meeting room for 3pm",
          "Install Kubernetes on the servers"]:
    case(t, [], out_of_scope=True)

# ── templated variants ────────────────────────────────────────────────────────
random.seed(7)
verbs = ["Connect {a} and {b} with {bw}", "I need {bw} between {a} and {b}", "Set up {bw} from {a} to {b}",
         "Provision a slice from {a} to {b} with {bw}", "Create a {bw} slice between {a} and {b}", "Link {a} to {b} at {bw}",
         "Please connect {a} to {b}, {bw}", "{bw} from {a} to {b}, please", "Can you set up {bw} between {a} and {b}",
         "Build a slice {a} to {b} carrying {bw}"]
bws = [("50 Mbps", 50), ("75 Mbps", 75), ("120 Mbps", 120), ("0.2 Gbps", 200), ("250Mbps", 250), ("300 mbps", 300),
       ("400 Mbit/s", 400), ("1 Gbps", 1000)]
extras = [("", {}, []), (", at most 10 ms", {"latency": ["le", 10]}, []), (" with latency under 5 ms", {"latency": ["le", 5]}, []),
          (", loss below 0.5%", {"loss": ["le", 0.5]}, []), (" on VLAN 350", {"vlan": ["eq", 350]}, []),
          (" tonight 20:00-23:00", {}, ["window"]), (", keep MCS5 or better", {"modulation_floor": ["ge", "MCS5"]}, []),
          (" during business hours", {}, ["window"]), (" at 99.9% availability", {"availability": ["ge", 99.9]}, [])]
pairs = [(R, E), (E, R), ("Region A", "the edge"), ("region-a", "Edge")]
combos = list(itertools.product(verbs, bws, extras, pairs))
random.shuffle(combos)
for verb, (bws_txt, bw), (ex_txt, ex_t, ex_c), (a, b) in combos[:230]:
    text = verb.format(a=a, b=b, bw=bws_txt) + ex_txt
    na = R if a.lower().replace(" ", "-") in ("region-a",) else E
    nb = E if na == R else R
    case(text, ["deliver"], endpoints=[na, nb], targets={"bandwidth": ["ge", bw], **ex_t}, contexts=ex_c)

changes = [("Double {s}", "scale", 400), ("Triple {s}", "scale", 600), ("Halve {s}", "scale", 100), ("Add 50 Mbps to {s}", "add", 250),
           ("Increase {s} by 100 Mbps", "add", 300), ("Set {s} to 350 Mbps", "set", 350), ("Give {s} 50% more", None, 300),
           ("Take {s} down to 120 Mbps", "set", 120), ("Make {s} 260 Mbps", "set", 260)]
names = ["the backhaul", "backhaul-ran", "the RAN backhaul", "Backhaul-RAN"]
for (tpl, op, value), name in itertools.product(changes, names):
    case(tpl.format(s=name), ["change"], ids=["backhaul-ran"], targets={"bandwidth": ["ge", value]}, **({"action": op} if op else {}))

life = [("Suspend {s}", "suspend"), ("Pause {s}", "suspend"), ("Resume {s}", "resume"), ("Bring back {s}", "resume"),
        ("Remove {s}", "delete"), ("Delete {s}", "delete"), ("Tear down {s}", "delete")]
for (tpl, op), name in itertools.product(life, names[:3]):
    case(tpl.format(s=name), ["lifecycle"], ids=["backhaul-ran"], action=op)

with OUT.open("w") as f:
    for c in CASES:
        f.write(json.dumps(c) + "\n")
print(f"{len(CASES)} cases -> {OUT}")
