# CER-Intent: 6G Transport Domain Intent Management PoC

> **Proof-of-Concept** — Intent-Based Networking for Ceragon transport devices in 6G architectures.

Translates high-level natural-language or structured intents from operators and agents into specific Ceragon device configurations, applied via simulated NETCONF, TeraFlow SDN, or direct RESTCONF.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Intent Input Layer                             │
│   NL Text · Structured JSON · Agent REST API               │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              Intent Engine                                  │
│  LLM Parser (Gemini) or Rule Parser → Schema Validation    │
│  Conflict Detection · Hardware Capability Checks           │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              Translation Layer                              │
│  Capacity · QoS · Modulation · Resilience · Slice          │
│  MRMC Script Selection · YANG XML Builder                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│     ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│     │  Simulated   │ │  TeraFlow    │ │  Direct Ceragon  │  │
│     │  Adapter     │ │  SDN Adapter │ │  REST Adapter    │  │
│     │  (default)   │ │  (REST API)  │ │  (RESTCONF)      │  │
│     └──────────────┘ └──────────────┘ └──────────────────┘  │
│              Device Adapter Layer                           │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              Closed-Loop Assurance                          │
│  Hardware-Aware Resilience Fallbacks · State Verification  │
│  Append-Only Audit Log                                     │
└─────────────────────────────────────────────────────────────┘
                           │
               Offline-Safe Dashboard (Native SVG)
```

---

## Smart Reconciliation Engine

The system features an advanced **Intent Architect** capable of multi-domain reasoning and constraint solving:

- **Hardware-Aware Fallbacks**: Automatically downgrades intents when hardware limits are hit (e.g., Falling back from Space Diversity to 1+1 HSB on unsupported IP-20C nodes).
- **Optimization (No-Op) Detection**: Intelligently skips configuration steps if the desired optimal state is already active on the device.
- **Reasoning Trace**: Provides a full audit of the Architect's logic for every decision made, visible directly in the dashboard.

---

## Offline Resilience

Optimized for restricted network and field environments:
- **Zero-Dependency Visualizer**: Replaced D3.js with a native SVG engine for 100% reliable topology rendering without internet access.
- **Local Asset Hosting**: All required frontend libraries (Socket.IO) and fonts are hosted locally by the backend.
- **Graceful Degradation**: Dashboard components remain functional even if individual external assets fail to load.

---

## Quick Start

```bash
# 1. Clone / enter the project
cd CER_Intent

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure (optional — works without LLM key)
cp .env.example .env
# Edit .env to add GEMINI_API_KEY if you have one

# 4. Start the system
python run.py

# 5. Open the dashboard
#    → http://localhost:5000
```

---

## Supported Intent Types

| Type | Example Input | Ceragon Config Generated |
|---|---|---|
| **Capacity** | "Ensure 5 Gbps on link-A-B for eMBB" | MRMC script #50, 112 MHz BW, ACM 64QAM–2048QAM |
| **QoS** | "Enforce < 5ms latency on link-D-E for URLLC" | QoS profile: EF class, DSCP 46 |
| **Modulation** | "Set minimum ACM to 256QAM on all links" | ACM profile: min=256QAM, max=2048QAM |
| **Resilience** | "Enable 1+1 HSB protection on sector-north" | Protection group: mode=1+1-hsb, revertive, WTR=300s |
| **Slice** | "Allocate 30% to eMBB slice on link-E-H" | Slice config: VLAN 104, priority 5, 30% BW |

---

## Device Adapter Backends

Select backend via `ADAPTER_BACKEND` environment variable:

| Value | Description | Required Env Vars |
|---|---|---|
| `simulated` (default) | In-memory mock, no device needed | None |
| `teraflow` | TeraFlow SDN controller REST API | `TERAFLOW_URL`, `TERAFLOW_TOKEN` |
| `direct_rest` | Ceragon RESTCONF directly on devices | `CERAGON_DEVICE_MAP`, `CERAGON_USER`, `CERAGON_PASSWORD` |

### TeraFlow Example
```bash
ADAPTER_BACKEND=teraflow
TERAFLOW_URL=http://10.0.0.1:8080
TERAFLOW_TOKEN=your-bearer-token
python run.py
```

### Direct RESTCONF Example
```bash
ADAPTER_BACKEND=direct_rest
CERAGON_DEVICE_MAP={"node-A":"192.168.1.10","node-B":"192.168.1.11"}
CERAGON_USER=admin
CERAGON_PASSWORD=ceragon123
CERAGON_PORT=443
CERAGON_TLS_VERIFY=false  # Lab use only
python run.py
```

---

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/intent` | Submit intent (NL text or JSON) |
| `GET` | `/api/v1/intents` | List all intents |
| `GET` | `/api/v1/intents/<id>` | Get specific intent |
| `DELETE` | `/api/v1/intents/<id>` | Delete intent |
| `GET` | `/api/v1/topology` | Network topology + device states |
| `GET` | `/api/v1/devices` | List all nodes and links |
| `GET` | `/api/v1/devices/<id>/state` | Device running config |
| `GET` | `/api/v1/audit-log` | Event audit trail |
| `GET` | `/api/v1/health` | System health check |

### Example API calls

```bash
# Natural language intent
curl -X POST http://localhost:5000/api/v1/intent \
  -H "Content-Type: application/json" \
  -d '{"intent": "Enable 1+1 HSB protection on link-A-B", "source": "agent"}'

# Structured JSON intent
curl -X POST http://localhost:5000/api/v1/intent \
  -H "Content-Type: application/json" \
  -d '{
    "intent": {
      "intent_type": "capacity",
      "target": {"target_type": "link", "identifier": "link-D-E"},
      "parameters": {"min_throughput_gbps": 8.0, "channel_bandwidth_mhz": 112}
    }
  }'
```

---

## Simulated Topology

8 Ceragon nodes across 4 sectors, 10 bidirectional links:

```
[sector-south]  node-A (IP-50FX) ── node-B (IP-50FX)
                    │                    │
[sector-west]  node-C (IP-20C)      node-F (IP-20N)  [sector-east]
                    │                    │
[sector-north] node-D (IP-20N) ── node-E (IP-50FX) ── node-H (IP-50FX)
                              node-G (IP-20C) ──────────┘
```

---

## LLM Integration

If a Gemini API key is set, natural-language parsing uses the Gemini LLM with few-shot examples tuned for 6G/Ceragon terminology.

Without an API key, the system automatically falls back to the built-in keyword-based rule parser — all functionality still works.

```bash
# .env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-1.5-flash  # or gemini-1.5-pro
```

---

## Simulated Features

- **SNR-driven ACM**: Modulation shifts with simulated atmospheric conditions
- **Daily utilization cycles**: Traffic load follows sinusoidal patterns  
- **Intent drift detection**: Reconciler detects when applied intent is violated
- **Closed-loop remediation**: Drift events are emitted to the dashboard
- **NETCONF XML generation**: Full RFC 6241-compliant edit-config payloads

---

## Project Structure

```
CER_Intent/
├── run.py                    # Entry point
├── requirements.txt
├── .env.example
├── cer_intent/
│   ├── intent_schema.py      # Pydantic data models
│   ├── intent_parser.py      # LLM + rule-based parser
│   ├── intent_validator.py   # Topology + hardware validation
│   ├── yang_builder.py       # NETCONF XML generator
│   ├── translators/          # 5 intent type translators
│   ├── device/               
│   │   ├── registry.py       # Network topology registry
│   │   ├── adapter.py        # Multi-backend adapter (Sim/TeraFlow/REST)
│   │   └── state_store.py    # Persistent JSON state
│   ├── assurance/
│   │   ├── telemetry_simulator.py
│   │   ├── reconciler.py     # Closed-loop drift detection
│   │   └── audit_log.py      # Append-only event log
│   └── api/
│       └── server.py         # Flask REST + Socket.IO
└── dashboard/                # Web UI (D3.js topology + live telemetry)
```

---

## References

## Documentation

- **System Specification**: [Ceragon Intent Architect — The Cognitive Future of 6G Transport](file:///c:/CER_Intent/docs/Ceragon_Intent_Architect_System_Spec.docx) — Detailed 10-page enterprise architecture guide.
- **Technical Whitepaper**: [The Cognitive Future of 6G Transport](file:///c:/CER_Intent/docs/CER_Intent_Technical_Whitepaper.docx) — Deep dive into intent lifecycle management.
- Ceragon CeraOS NETCONF/YANG: [Ceragon Support Portal](https://www.ceragon.com)
- TeraFlow SDN: [teraflowsdn.etsi.org](https://teraflowsdn.etsi.org)
- IETF IBN: [RFC 9417 — SAIN](https://www.rfc-editor.org/rfc/rfc9417)
- ETSI ZSM: [Zero-Touch Network Management](https://www.etsi.org/technologies/zero-touch-network-service-management)
