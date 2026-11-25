"""
Words the reader knows: verbs per intent kind, metric words, comparators,
service profiles, vague words and what is out of scope.

Service profiles and named time windows are operator policy: they can be
changed at run time (PUT /api/v2/policy) and every value taken from them is
marked as such in the intent record.
"""
from __future__ import annotations

import re
from typing import Dict, List, Pattern, Tuple

from cer_intent.imf.model import Kind

# ── kinds, by the verb or cue that signals them; checked in this order ──────
KIND_CUES: List[Tuple[Kind, Pattern[str]]] = [
    (Kind.EXPLORE, re.compile(
        r"\bwhat\s+(?:if|happens\s+if|would\s+happen)\b|\bhow\s+much\s+(?:more|extra|additional|spare|headroom|room)\b"
        r"|\bhow\s+much\s+(?:can|could)\b|\b(?:can|could|would)\s+(?:the\s+|it\s+|we\s+|i\s+)?(?:[\w-]+\s+){0,3}?"
        r"(?:take|handle|carry|survive|cope\s+with|sustain|support|absorb|fit)\b"
        r"|\bis\s+there\s+(?:room|headroom|capacity)\b|\b(?:max(?:imum)?|most)\s+(?:i|we)\s+can\b"
        r"|^\s*(?:can|could|would|may)\s+(?:i|we|you)\s+(?:still\s+)?(?:add|get|have|give|connect|deliver|provision|squeeze|run|put)\b.*\?\s*$"
        r"|^\s*(?:is\s+it\s+possible|would\s+it\s+(?:work|fit))\b"
        r"|\bsimulate\b|\btest\s+(?:whether|if)\b|\bheadroom\b(?=.*\?)", re.I)),
    (Kind.ASK, re.compile(
        r"^\s*(?:why|what(?:'s|\s+is|\s+are|\s+runs|\s+uses|\s+happened)?|which|who|where|when|how\s+(?:many|is|are|does|do)"
        r"|is\s+(?:the|it|there|slice|service|radio|[\w-]+\s+(?:ok|up|healthy|down|degraded))|are\s+(?:the|there|all)|show|list|explain"
        r"|tell\s+me\s+(?:about|why|what|which|how)|status\s+of|give\s+me\s+(?:the\s+)?(?:status|state|list))\b", re.I)),
    (Kind.GUARD, re.compile(
        r"\bauto[- ]?approv\w*|\b(?:approve|apply)\s+(?:[\w-]+\s+){0,6}?automatically\b|\bapply\s+(?:[\w.-]+\s+){0,8}?without\s+(?:asking|approval|waiting)\b"
        r"|\b(?:never|don'?t|do\s+not)\s+let\s+(?:any|a\s+single|every|all(?:\s+the)?)\s+(?:hops?|radios?|links?)\b"
        r"|\b(?:no|every|any)\s+(?:hop|radio|link)s?\s+(?:may|can|should|must)\s+(?:go|drop|fall)\s+below\b", re.I)),
    (Kind.KEEP, re.compile(
        r"\b(?:don'?t|do\s+not|never)\s+let\b|\bmust\s+(?:not|never)\s+(?:drop|fall|exceed|go|rise)\b", re.I)),
    (Kind.GUARD, re.compile(
        r"\b(?:(?:don'?t|do\s+not|never|must\s+not|no\s+one\s+may)\s+(?:touch|change|modify|reconfigure|restart|reboot|update|apply|deploy|make\s+changes|configure)"
        r"|no\s+(?:changes?|config(?:uration)?\s+changes?|touch(?:ing)?|work|maintenance)\b|freeze|frozen|forbid|prevent\s+changes|lock(?:ed)?\s+down"
        r"|avoid\s+(?:touching|changing)|maintenance\s+window|change\s+window|leave\s+[\w-]+\s+alone|hands\s+off"
        r"|(?:keep|reserve|hold\s+back|leave)\s+(?:at\s+least\s+)?\d+(?:\.\d+)?\s*(?:%|percent|mbps)\s+(?:of\s+)?(?:headroom|spare|free|in\s+reserve)"
        r"|(?:keep|reserve|leave)\s+(?:\w+\s+)?headroom|only\s+(?:allow|permit)\s+changes?|require\s+approval|needs?\s+approval"
        r"|(?:never|not)\s+(?:below|under)\s+mcs\s*\d+|floor\s+(?:of|at)\s+mcs\s*\d+\s+(?:everywhere|on\s+all|network[- ]wide))\b", re.I)),
    (Kind.OBSERVE, re.compile(
        r"\b(?:report|notify|alert|warn|tell\s+me\s+(?:if|when|whenever)|let\s+me\s+know|inform\s+me|send\s+me|e-?mail\s+me"
        r"|monitor|watch|track|subscribe|keep\s+an\s+eye|hourly|daily\s+report|weekly\s+report)\b", re.I)),
    (Kind.LIFECYCLE, re.compile(
        r"\b(?:suspend|pause|stop|halt|resume|restart|reactivate|re-?enable|unpause|bring\s+back|remove|delete|tear\s+down|terminate"
        r"|withdraw|cancel|decommission|release|deactivate|disable|drop\s+(?:the|all|every)|get\s+rid\s+of|clean\s+up"
        r"|turn\s+off|switch\s+off|shut\s+(?:down|off))\b", re.I)),
    (Kind.OPTIMISE, re.compile(
        r"\b(?:save\s+(?:energy|power)|reduce\s+(?:the\s+)?(?:energy|power|consumption)|lower\s+(?:the\s+)?(?:power|energy|consumption)"
        r"|minimi[sz]e|maximi[sz]e|optimi[sz]e|balance|green(?:er)?\b|energy[- ]sav|power[- ]sav|eco\b|be\s+efficient|cut\s+(?:energy|power))\b", re.I)),
    (Kind.KEEP, re.compile(
        r"\b(?:keep|maintain|ensure|guarantee|make\s+sure|hold|assure|preserve|protect|sustain|never\s+let|at\s+all\s+times"
        r"|must\s+(?:stay|remain)|stay\s+(?:above|below|under|over))\b", re.I)),
    (Kind.CHANGE, re.compile(
        r"\b(?:increase|decrease|raise|lower|double|triple|quadruple|halve|scale|bump|boost|cut|upgrade|downgrade|move|change|set(?!\s+up)"
        r"|modify|update|switch|extend|shorten|rename|re-?prioriti[sz]e|tighten|relax|loosen|grow|shrink|expand|reduce|add\s+\d"
        r"|give\s+(?:the\s+)?[\w-]+(?:\s+[\w-]+){0,2}\s+(?:\d+(?:\.\d+)?\s*%\s+)?(?:more|less)|take\s+[\w-]+(?:\s+[\w-]+)?\s+(?:down|up)\s+to"
        r"|make\s+(?:it|[\w-]+)\s+(?:\d|faster|bigger|smaller))\b", re.I)),
    (Kind.DELIVER, re.compile(
        r"\b(?:connect|link\s+up|create|provision|set\s+up|setup|establish|build|deploy|give|provide|need|want|order|request"
        r"|allocate|reserve\s+a|add\s+(?:a|an|another|new)|new\s+(?:slice|service|vpn|link|circuit)|bring\s+up|stand\s+up|open\s+a)\b", re.I)),
]

VAGUE = re.compile(r"(?<!or\s)\b(?:faster|quicker|better(?!\s+than)|improve|improved|more\s+reliable|more\s+stable|speed\s+up|fix\s+(?:it|the\s+network)"
                   r"|make\s+(?:it|the\s+network)\s+(?:work|good)|smoother|snappier|less\s+laggy|laggy|slow)\b", re.I)

OUT_OF_SCOPE: List[Tuple[Pattern[str], str]] = [
    (re.compile(r"\b(?:bgp|ospf|is-is|isis|eigrp|rip)\b", re.I), "routing protocols on routers"),
    (re.compile(r"\b(?:firewall|acl|access\s+list|nat\b|dns|dhcp)\b", re.I), "firewall, ACL, NAT, DNS and DHCP"),
    (re.compile(r"\b(?:wi-?fi|wlan|ssid)\b", re.I), "Wi-Fi access"),
    (re.compile(r"\b(?:kubernetes|k8s|docker|vm\b|virtual\s+machine|server\s+os)\b", re.I), "compute and cloud resources"),
    (re.compile(r"\b(?:core\s+router|mpls\s+core|segment\s+routing\s+policy\s+on\s+the\s+core)\b", re.I), "the IP/MPLS core"),
    (re.compile(r"\b(?:billing|invoice|price|pricing|customer\s+account)\b", re.I), "billing and accounts"),
    (re.compile(r"\b(?:password|laptop|desktop|printer|e-?mail\s+account|vpn\s+client|office\s+wi-?fi)\b", re.I), "IT support"),
    (re.compile(r"\b(?:ticket|support\s+desk|help\s*desk|vendor\s+support|rma)\b", re.I), "ticketing and vendor support"),
    (re.compile(r"\b(?:meeting|calendar|book\s+a\s+room|meeting\s+room|lunch|pizza|coffee)\b", re.I), "office logistics"),
    (re.compile(r"\b(?:poem|joke|story|essay|song|recipe)\b", re.I), "writing that is not about the network"),
    (re.compile(r"\bweather\s+(?:in|for|at)\s+[A-Z]", re.I), "weather forecasts (rain on a hop is in scope: say the hop and the rain)"),
]
NETWORK_WORDS = re.compile(
    r"\b(?:slices?|vpns?|l2vpn|l3vpn|radios?|hops?|links?|networks?|backhaul|fronthaul|midhaul|sites?|nodes?|mbps|gbps|kbps|bandwidth|"
    r"latency|delay|jitter|loss|availability|uptime|vlan|mcs\d*|modulation|qam|acm|rain(?:ing|fall|s)?|mm/h|storms?|capacity|headroom|throughput|traffic|"
    r"energy|power|intents?|rules?|polic(?:y|ies)|services?|alerts?|reports?|twin|sla|slos?|changes?|maintenance|freeze|approval|"
    r"auto[- ]?approv\w*|approv(?:e|als?)\s+(?:\w+\s+){0,3}?automatically|deliver(?:y|ies)|guardrails?|"
    r"what\s+can\s+you|help|status|health|state)\b", re.I)
# "never auto-approve ...", "stop auto-approving ...", "turn auto-approval off" (the negation leads the phrase,
# so "auto-approve slices of no more than 300 Mbps" stays a grant)
NO_AUTO = re.compile(
    r"\b(?:never|don'?t|do\s+not|stop|cease|no\s+longer|no\s+more)\b(?=.{0,30}?\b(?:auto[- ]?approv|approv|apply))|"
    r"\b(?:disable|turn\s+off|switch\s+off|pause|suspend)\s+(?:the\s+)?auto[- ]?approv\w*|"
    r"\bauto[- ]?approv\w*\s+(?:is\s+)?off\b|\bno\s+(?:automatic\s+approv|auto[- ]?approv)\w*|"
    r"^\s*(?:no|nothing)\b(?=.*\bwithout\b)", re.I)
IN_SCOPE = ("transport slices and VPNs (L2 and L3) between sites", "changing, suspending and removing them",
            "radio settings: modulation floor, TX power, energy saving", "standing objectives on bandwidth, latency, loss "
            "and availability", "rules (freeze windows, headroom)", "reports and alerts",
            "what-if questions answered on the digital twin", "questions about the network and past decisions")

# ── metric words (looked up near a number) ──────────────────────────────────
METRIC_WORDS: Dict[str, Pattern[str]] = {
    "latency": re.compile(r"\b(?:latency|delay|rtt|round[- ]trip|one[- ]way|lag|ping)\b", re.I),
    "jitter": re.compile(r"\b(?:jitter|pdv|delay\s+variation)\b", re.I),
    "loss": re.compile(r"\b(?:loss|packet\s+loss|drops?|dropped|plr)\b", re.I),
    "availability": re.compile(r"\b(?:availability|available|uptime|nines|up\s+time)\b", re.I),
    "headroom": re.compile(r"\b(?:headroom|spare|reserve|free\s+capacity|room)\b", re.I),
    "utilisation": re.compile(r"\b(?:utili[sz]ation|utili[sz]ed|load|busy|occupancy)\b", re.I),
    "bandwidth": re.compile(r"\b(?:bandwidth|throughput|capacity|rate|speed|bw|traffic)\b", re.I),
    "energy": re.compile(r"\b(?:energy|power\s+draw|consumption|watts?)\b", re.I),
    "tx_power": re.compile(r"\b(?:tx\s+power|transmit\s+power|output\s+power|power\s+level)\b", re.I),
}

GE_WORDS = re.compile(r"(?:at\s+least|min(?:imum)?(?:\s+of)?|no\s+less\s+than|not\s+less\s+than|>=|≥|over|above|more\s+than|greater\s+than"
                      r"|guaranteed|guarantee|from|beyond|higher\s+than|exceed(?:ing|s)?)\s*$", re.I)
LE_WORDS = re.compile(r"(?:at\s+most|max(?:imum)?(?:\s+of)?|no\s+more\s+than|not\s+more\s+than|<=|≤|under|below|less\s+than|within"
                      r"|up\s+to|not\s+exceed(?:ing)?|lower\s+than|beneath|no\s+higher\s+than|<|sub)\s*$", re.I)
EQ_WORDS = re.compile(r"(?:exactly|equal\s+to|=|of|at)\s*$", re.I)

# ── service profiles: operator policy, shown as "profile" in the record ──────
PROFILES: Dict[str, Dict[str, object]] = {
    "platinum": {"latency": 2.0, "loss": 0.001, "availability": 99.999, "priority": 8, "label": "platinum"},
    "gold": {"latency": 5.0, "loss": 0.01, "availability": 99.99, "priority": 7, "label": "gold"},
    "silver": {"latency": 10.0, "loss": 0.1, "availability": 99.9, "priority": 5, "label": "silver"},
    "bronze": {"latency": 20.0, "loss": 1.0, "availability": 99.5, "priority": 3, "label": "bronze"},
    "best_effort": {"priority": 1, "strictness": "best_effort", "label": "best effort"},
    "urllc": {"latency": 1.0, "loss": 0.001, "priority": 8, "slice_type": "URLLC", "label": "URLLC"},
    "embb": {"latency": 10.0, "loss": 0.1, "priority": 5, "slice_type": "eMBB", "label": "eMBB"},
    "mmtc": {"latency": 50.0, "loss": 1.0, "priority": 3, "slice_type": "mMTC", "label": "mMTC"},
    "low_latency": {"latency": 5.0, "loss": 0.1, "priority": 6, "label": "low latency"},
    "critical": {"latency": 5.0, "loss": 0.01, "availability": 99.99, "priority": 8, "label": "critical"},
    "video": {"latency": 50.0, "loss": 0.1, "priority": 4, "label": "video"},
    "voice": {"latency": 20.0, "jitter": 5.0, "loss": 0.5, "priority": 6, "label": "voice"},
}
PROFILE_WORDS: List[Tuple[str, Pattern[str]]] = [
    ("platinum", re.compile(r"\bplatinum\b", re.I)), ("gold", re.compile(r"\bgold(?:en)?\b|\bpremium\b", re.I)),
    ("silver", re.compile(r"\bsilver\b|\bstandard\b", re.I)), ("bronze", re.compile(r"\bbronze\b|\bbasic\b", re.I)),
    ("best_effort", re.compile(r"\bbest[- ]effort\b", re.I)), ("urllc", re.compile(r"\burllc\b|\bultra[- ]reliable\b", re.I)),
    ("embb", re.compile(r"\bembb\b|\bbroadband\b", re.I)), ("mmtc", re.compile(r"\bmmtc\b|\biot\b|\bsensors?\b", re.I)),
    ("low_latency", re.compile(r"\blow[- ]latency\b|\breal[- ]time\b|\blatency[- ]sensitive\b|\bfast\s+response\b", re.I)),
    ("critical", re.compile(r"\bmission[- ]critical\b|\bcritical\b", re.I)),
    ("voice", re.compile(r"\bvoice\b|\bvoip\b", re.I)), ("video", re.compile(r"\bvideo\b|\bstreaming\b|\bcctv\b|\bcameras?\b", re.I)),
]

# ── named time windows: operator policy ──────────────────────────────────────
WINDOWS: Dict[str, Dict[str, object]] = {
    "tonight": {"start": "20:00", "end": "23:59", "once": True},
    "this evening": {"start": "18:00", "end": "23:00", "once": True},
    "this morning": {"start": "06:00", "end": "12:00", "once": True},
    "this afternoon": {"start": "12:00", "end": "18:00", "once": True},
    "at night": {"start": "22:00", "end": "06:00"},
    "overnight": {"start": "22:00", "end": "06:00"},
    "nightly": {"start": "22:00", "end": "06:00"},
    "business hours": {"start": "08:00", "end": "18:00", "days": ["mon", "tue", "wed", "thu", "fri"]},
    "working hours": {"start": "08:00", "end": "18:00", "days": ["mon", "tue", "wed", "thu", "fri"]},
    "office hours": {"start": "08:00", "end": "18:00", "days": ["mon", "tue", "wed", "thu", "fri"]},
    "peak hours": {"start": "17:00", "end": "22:00"},
    "busy hour": {"start": "19:00", "end": "21:00"},
    "off-peak": {"start": "00:00", "end": "06:00"},
    "off peak": {"start": "00:00", "end": "06:00"},
    "weekends": {"start": "00:00", "end": "23:59", "days": ["sat", "sun"]},
    "this weekend": {"start": "00:00", "end": "23:59", "days": ["sat", "sun"], "once": True},
    "over the weekend": {"start": "00:00", "end": "23:59", "days": ["sat", "sun"], "once": True},
    "weekdays": {"start": "00:00", "end": "23:59", "days": ["mon", "tue", "wed", "thu", "fri"]},
}

DAYS = {"monday": "mon", "mon": "mon", "tuesday": "tue", "tue": "tue", "tues": "tue", "wednesday": "wed", "wed": "wed",
        "thursday": "thu", "thu": "thu", "thur": "thu", "thurs": "thu", "friday": "fri", "fri": "fri",
        "saturday": "sat", "sat": "sat", "sunday": "sun", "sun": "sun"}

TECH_WORDS = [("L3VPN", re.compile(r"\b(?:l3vpn|l3\s*vpn|layer[- ]?3|routed|ip\s*vpn|l3)\b", re.I)),
              ("L2VPN", re.compile(r"\b(?:l2vpn|l2\s*vpn|layer[- ]?2|bridged|ethernet\s+(?:line|service|circuit)|e-?line|l2)\b", re.I))]

STRICT_WORDS = [("must", re.compile(r"\b(?:must|required|guarantee(?:d)?|at\s+all\s+times|always|strict(?:ly)?|hard)\b", re.I)),
                ("prefer", re.compile(r"\b(?:prefer(?:ably)?|ideally|if\s+possible|try\s+to|where\s+possible|nice\s+to\s+have|soft)\b", re.I)),
                ("best_effort", re.compile(r"\bbest[- ]effort\b", re.I))]

PRIORITY_WORDS = [(8, re.compile(r"\b(?:top|highest|max(?:imum)?)\s+priority\b|\bcritical\b", re.I)),
                  (7, re.compile(r"\bhigh\s+priority\b|\bhigh-priority\b|\burgent\b", re.I)),
                  (5, re.compile(r"\b(?:normal|medium)\s+priority\b", re.I)),
                  (2, re.compile(r"\blow\s+priority\b|\blow-priority\b", re.I))]
