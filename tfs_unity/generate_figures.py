"""
Script to generate all technical and illustrative figures for TFS-NS3 Digital Twin:
  1. figures/digital_twin_mirror_concept.svg
  2. figures/telecom_ndt_5layer_architecture.svg
  3. figures/3gpp_ts28561_ndti_lifecycle.svg
  4. figures/closed_loop_sequence_diagram.svg
  5. figures/rain_attenuation_and_acm_curves.png
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

FIGURES_DIR = r"c:\tfs-ns3-digital-twin\figures"
os.makedirs(FIGURES_DIR, exist_ok=True)

# ==============================================================================
# FIGURE 1: Illustrative Conceptual Diagram (Cyber-Physical Mirror)
# ==============================================================================
FIG1_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 680" width="100%" height="100%">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0B132B"/>
      <stop offset="50%" stop-color="#1C2541"/>
      <stop offset="100%" stop-color="#0B132B"/>
    </linearGradient>
    <linearGradient id="physGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1E3A8A"/>
      <stop offset="100%" stop-color="#0284C7"/>
    </linearGradient>
    <linearGradient id="twinGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#065F46"/>
      <stop offset="100%" stop-color="#10B981"/>
    </linearGradient>
    <linearGradient id="mirrorLine" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#38BDF8" stop-opacity="0.1"/>
      <stop offset="50%" stop-color="#38BDF8" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="#38BDF8" stop-opacity="0.1"/>
    </linearGradient>
    <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="6" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>

  <!-- Background Canvas -->
  <rect width="1200" height="680" fill="url(#bgGrad)"/>

  <!-- Title Banner -->
  <text x="600" y="48" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="26" font-weight="bold" fill="#F8FAFC" text-anchor="middle" letter-spacing="1.5">
    TELECOM NETWORK DIGITAL TWIN (NDT) CYBER-PHYSICAL MIRROR
  </text>
  <text x="600" y="78" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="14" fill="#94A3B8" text-anchor="middle">
    Bi-directional closed-loop synchronization between physical Ceragon 6G transport infrastructure and high-fidelity virtual twin
  </text>

  <!-- Central Reflection Plane (The Mirror) -->
  <line x1="600" y1="100" x2="600" y2="640" stroke="url(#mirrorLine)" stroke-width="3" stroke-dasharray="8 6"/>
  <rect x="530" y="340" width="140" height="36" rx="18" fill="#0F172A" stroke="#38BDF8" stroke-width="2" filter="url(#glow)"/>
  <text x="600" y="363" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="12" font-weight="bold" fill="#38BDF8" text-anchor="middle">
    CYBER MIRROR
  </text>

  <!-- ================= LEFT: PHYSICAL WORLD ================= -->
  <g transform="translate(40, 110)">
    <rect width="520" height="520" rx="16" fill="#0F172A" fill-opacity="0.8" stroke="#1E40AF" stroke-width="2"/>
    
    <!-- Header -->
    <rect width="520" height="48" rx="16" fill="url(#physGrad)"/>
    <text x="260" y="30" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="18" font-weight="bold" fill="#FFFFFF" text-anchor="middle">
      PHYSICAL TELECOM NETWORK
    </text>

    <!-- Physical Ceragon Nodes -->
    <!-- Tower A -->
    <g transform="translate(60, 240)">
      <polygon points="40,20 20,180 60,180" fill="#334155" stroke="#64748B" stroke-width="2"/>
      <line x1="20" y1="60" x2="60" y2="60" stroke="#64748B" stroke-width="1.5"/>
      <line x1="25" y1="110" x2="55" y2="110" stroke="#64748B" stroke-width="1.5"/>
      <line x1="30" y1="150" x2="50" y2="150" stroke="#64748B" stroke-width="1.5"/>
      <!-- Ceragon MH-T261 TU Antenna -->
      <circle cx="40" cy="20" r="14" fill="#0284C7" stroke="#38BDF8" stroke-width="2" filter="url(#glow)"/>
      <path d="M40,6 A14,14 0 0,1 54,20" fill="none" stroke="#F8FAFC" stroke-width="2"/>
      <text x="40" y="205" font-family="Segoe UI, sans-serif" font-size="13" font-weight="bold" fill="#E2E8F0" text-anchor="middle">Ceragon MH-T261</text>
      <text x="40" y="222" font-family="Segoe UI, sans-serif" font-size="11" fill="#94A3B8" text-anchor="middle">(ctu-96) 60 GHz TU</text>
    </g>

    <!-- Tower B -->
    <g transform="translate(380, 240)">
      <polygon points="40,20 20,180 60,180" fill="#334155" stroke="#64748B" stroke-width="2"/>
      <line x1="20" y1="60" x2="60" y2="60" stroke="#64748B" stroke-width="1.5"/>
      <line x1="25" y1="110" x2="55" y2="110" stroke="#64748B" stroke-width="1.5"/>
      <line x1="30" y1="150" x2="50" y2="150" stroke="#64748B" stroke-width="1.5"/>
      <!-- Ceragon Node B -->
      <circle cx="40" cy="20" r="14" fill="#0284C7" stroke="#38BDF8" stroke-width="2" filter="url(#glow)"/>
      <path d="M40,6 A14,14 0 0,1 54,20" fill="none" stroke="#F8FAFC" stroke-width="2"/>
      <text x="40" y="205" font-family="Segoe UI, sans-serif" font-size="13" font-weight="bold" fill="#E2E8F0" text-anchor="middle">Ceragon MH-N366</text>
      <text x="40" y="222" font-family="Segoe UI, sans-serif" font-size="11" fill="#94A3B8" text-anchor="middle">(dn-01) 4-Sector DN</text>
    </g>

    <!-- Multi-Domain Network Stressors & Perturbations -->
    <g transform="translate(140, 115)">
      <rect width="250" height="95" rx="8" fill="#1E293B" stroke="#F59E0B" stroke-width="1.5"/>
      <text x="125" y="24" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#FBBF24" text-anchor="middle">
        MULTI-DOMAIN STRESSORS
      </text>
      <text x="15" y="44" font-family="Segoe UI, sans-serif" font-size="10" fill="#E2E8F0">• Traffic Surges &amp; Bufferbloat (3.5x load)</text>
      <text x="15" y="60" font-family="Segoe UI, sans-serif" font-size="10" fill="#E2E8F0">• Link Outages &amp; Fiber Cuts (Fast Reroute)</text>
      <text x="15" y="76" font-family="Segoe UI, sans-serif" font-size="10" fill="#E2E8F0">• Green Telco Sleep Mode Scheduling</text>
      <text x="15" y="92" font-family="Segoe UI, sans-serif" font-size="10" fill="#E2E8F0">• Atmospheric / mmWave Channel Fading</text>
    </g>

    <!-- Operational State Badges -->
    <g transform="translate(40, 430)">
      <rect width="440" height="70" rx="8" fill="#1E293B" stroke="#334155" stroke-width="1.5"/>
      <text x="20" y="26" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#38BDF8">REAL-TIME HARDWARE METRICS:</text>
      <text x="20" y="48" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">Carrier: 64.8 GHz | Active MCS: MCS 8 | RSSI: -58.4 dBm | SNR: 24.1 dB</text>
      <circle cx="410" cy="35" r="8" fill="#10B981" filter="url(#glow)"/>
      <text x="390" y="39" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#10B981" text-anchor="end">ONLINE</text>
    </g>
  </g>

  <!-- ================= RIGHT: DIGITAL TWIN WORLD ================= -->
  <g transform="translate(640, 110)">
    <rect width="520" height="520" rx="16" fill="#0F172A" fill-opacity="0.8" stroke="#059669" stroke-width="2"/>
    
    <!-- Header -->
    <rect width="520" height="48" rx="16" fill="url(#twinGrad)"/>
    <text x="260" y="30" font-family="Segoe UI, Helvetica, Arial, sans-serif" font-size="18" font-weight="bold" fill="#FFFFFF" text-anchor="middle">
      TELECOM DIGITAL TWIN (CYBER WORLD)
    </text>

    <!-- 3D Topology Shadow Container -->
    <g transform="translate(40, 70)">
      <rect width="440" height="150" rx="10" fill="#064E3B" fill-opacity="0.4" stroke="#10B981" stroke-width="1.5"/>
      <text x="20" y="25" font-family="Segoe UI, sans-serif" font-size="13" font-weight="bold" fill="#34D399">
        3GPP TS 28.561 NDTI Instance Shadow (34 Nodes / 34 Links)
      </text>

      <!-- Graph Nodes -->
      <circle cx="70" cy="80" r="14" fill="#047857" stroke="#34D399" stroke-width="2"/>
      <text x="70" y="84" font-family="Segoe UI, sans-serif" font-size="10" font-weight="bold" fill="#FFFFFF" text-anchor="middle">UPF</text>

      <circle cx="160" cy="55" r="14" fill="#047857" stroke="#34D399" stroke-width="2"/>
      <text x="160" y="59" font-family="Segoe UI, sans-serif" font-size="10" font-weight="bold" fill="#FFFFFF" text-anchor="middle">CU</text>

      <circle cx="260" cy="55" r="14" fill="#047857" stroke="#34D399" stroke-width="2"/>
      <text x="260" y="59" font-family="Segoe UI, sans-serif" font-size="10" font-weight="bold" fill="#FFFFFF" text-anchor="middle">DU</text>

      <circle cx="370" cy="80" r="16" fill="#D97706" stroke="#FBBF24" stroke-width="2" filter="url(#glow)"/>
      <text x="370" y="84" font-family="Segoe UI, sans-serif" font-size="10" font-weight="bold" fill="#FFFFFF" text-anchor="middle">T261</text>

      <line x1="84" y1="80" x2="146" y2="55" stroke="#34D399" stroke-width="2"/>
      <line x1="174" y1="55" x2="246" y2="55" stroke="#34D399" stroke-width="2"/>
      <line x1="274" y1="55" x2="354" y2="80" stroke="#FBBF24" stroke-width="2.5" stroke-dasharray="4 3"/>

      <text x="220" y="125" font-family="Segoe UI, sans-serif" font-size="11" fill="#A7F3D0" text-anchor="middle">
        Real-time telemetry shadow updated via RFC 8040 RESTCONF
      </text>
    </g>

    <!-- Simulation & AI Optimization Engines -->
    <g transform="translate(40, 240)">
      <rect width="210" height="170" rx="10" fill="#1E293B" stroke="#38BDF8" stroke-width="1.5"/>
      <text x="105" y="26" font-family="Segoe UI, sans-serif" font-size="13" font-weight="bold" fill="#38BDF8" text-anchor="middle">
        NS-3 Simulation Engine
      </text>
      <text x="15" y="52" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• C++ Discrete Event</text>
      <text x="15" y="74" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• ITU-R P.838 Rain Model</text>
      <text x="15" y="96" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Queueing Delay &amp; Jitter</text>
      <text x="15" y="118" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Predicted Drop: MCS 8→0</text>
      <rect x="15" y="130" width="180" height="26" rx="6" fill="#EF4444" fill-opacity="0.2" stroke="#EF4444" stroke-width="1"/>
      <text x="105" y="147" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#EF4444" text-anchor="middle">
        SLA BREACH PREDICTED
      </text>
    </g>

    <g transform="translate(270, 240)">
      <rect width="210" height="170" rx="10" fill="#1E293B" stroke="#10B981" stroke-width="1.5"/>
      <text x="105" y="26" font-family="Segoe UI, sans-serif" font-size="13" font-weight="bold" fill="#10B981" text-anchor="middle">
        Cognitive AI Reconciler
      </text>
      <text x="15" y="52" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• TMF921 Intent Contract</text>
      <text x="15" y="74" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• RF Safety Verification</text>
      <text x="15" y="96" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• ACM Floor: MCS 2</text>
      <text x="15" y="118" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Retune Freq: 64.8 GHz</text>
      <rect x="15" y="130" width="180" height="26" rx="6" fill="#10B981" fill-opacity="0.2" stroke="#10B981" stroke-width="1"/>
      <text x="105" y="147" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#10B981" text-anchor="middle">
        REMEDIATION VERIFIED
      </text>
    </g>

    <!-- Actuation Dispatcher Badge -->
    <g transform="translate(40, 430)">
      <rect width="440" height="70" rx="8" fill="#1E293B" stroke="#334155" stroke-width="1.5"/>
      <text x="20" y="26" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#10B981">CLOSED-LOOP ACTUATION DISPATCHER:</text>
      <text x="20" y="48" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">TFS 2-Phase Commit (2PC) Candidate Commit -> Hardware Reconfigured</text>
    </g>
  </g>

  <!-- ================= BI-DIRECTIONAL FLOW ARROWS ================= -->
  <!-- Telemetry Sync (Physical -> Twin) -->
  <g transform="translate(530, 200)">
    <path d="M0,0 L140,0" stroke="#38BDF8" stroke-width="3" stroke-linecap="round" marker-end="url(#arrowBlue)"/>
    <text x="70" y="-8" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#38BDF8" text-anchor="middle">
      Telemetry Sync (L1)
    </text>
  </g>

  <!-- Control Actuation (Twin -> Physical) -->
  <g transform="translate(530, 470)">
    <path d="M140,0 L0,0" stroke="#10B981" stroke-width="3" stroke-linecap="round"/>
    <polygon points="0,0 12,-5 12,5" fill="#10B981"/>
    <text x="70" y="-8" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#10B981" text-anchor="middle">
      2PC Actuation (L3)
    </text>
  </g>
</svg>
"""

with open(os.path.join(FIGURES_DIR, "digital_twin_mirror_concept.svg"), "w", encoding="utf-8") as f:
    f.write(FIG1_SVG)


# ==============================================================================
# FIGURE 2: Technical 5-Layer Telecom Digital Twin Architecture
# ==============================================================================
FIG2_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 760" width="100%" height="100%">
  <defs>
    <linearGradient id="l5grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#4C1D95"/><stop offset="100%" stop-color="#7C3AED"/>
    </linearGradient>
    <linearGradient id="l4grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#1E3A8A"/><stop offset="100%" stop-color="#2563EB"/>
    </linearGradient>
    <linearGradient id="l2grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#065F46"/><stop offset="100%" stop-color="#059669"/>
    </linearGradient>
    <linearGradient id="l3grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#9A3412"/><stop offset="100%" stop-color="#EA580C"/>
    </linearGradient>
    <linearGradient id="l1grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#0F172A"/><stop offset="100%" stop-color="#334155"/>
    </linearGradient>
  </defs>

  <rect width="1200" height="760" fill="#0B0F19"/>

  <text x="600" y="42" font-family="Segoe UI, sans-serif" font-size="24" font-weight="bold" fill="#F8FAFC" text-anchor="middle">
    STANDARDIZED FIVE-LAYER TELECOM DIGITAL TWIN API ARCHITECTURE
  </text>
  <text x="600" y="68" font-family="Segoe UI, sans-serif" font-size="13" fill="#94A3B8" text-anchor="middle">
    Decomposition into discrete functional boundaries: 3GPP TS 28.561 | ITU-T Y.3090 | IETF NMRG DTI | TM Forum ODA | ETSI OpenCAPIF
  </text>

  <!-- LAYER 5: GOVERNANCE & EXPOSURE -->
  <g transform="translate(60, 95)">
    <rect width="1080" height="95" rx="10" fill="#1E1B4B" stroke="#8B5CF6" stroke-width="2"/>
    <rect width="260" height="95" rx="10" fill="url(#l5grad)"/>
    <text x="130" y="38" font-family="Segoe UI, sans-serif" font-size="15" font-weight="bold" fill="#FFFFFF" text-anchor="middle">LAYER 5</text>
    <text x="130" y="58" font-family="Segoe UI, sans-serif" font-size="13" font-weight="bold" fill="#DDD6FE" text-anchor="middle">API Governance &amp; Security</text>
    <text x="130" y="78" font-family="Segoe UI, sans-serif" font-size="11" fill="#C4B5FD" text-anchor="middle">3GPP TS 29.222 / OpenCAPIF</text>

    <!-- Sub-blocks -->
    <rect x="280" y="15" width="240" height="65" rx="6" fill="#2E1065" stroke="#7C3AED" stroke-width="1"/>
    <text x="400" y="38" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#EDE9FE" text-anchor="middle">CAPIF Core Function (CCF)</text>
    <text x="400" y="58" font-family="Segoe UI, sans-serif" font-size="10" fill="#C4B5FD" text-anchor="middle">API Publishing &amp; Universal Catalog</text>

    <rect x="540" y="15" width="250" height="65" rx="6" fill="#2E1065" stroke="#7C3AED" stroke-width="1"/>
    <text x="665" y="38" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#EDE9FE" text-anchor="middle">API Exposing Function (AEF)</text>
    <text x="665" y="58" font-family="Segoe UI, sans-serif" font-size="10" fill="#C4B5FD" text-anchor="middle">OAuth 2.0 / mTLS &amp; Rate Quotas</text>

    <rect x="810" y="15" width="250" height="65" rx="6" fill="#2E1065" stroke="#7C3AED" stroke-width="1"/>
    <text x="935" y="38" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#EDE9FE" text-anchor="middle">API Invoker Domain</text>
    <text x="935" y="58" font-family="Segoe UI, sans-serif" font-size="10" fill="#C4B5FD" text-anchor="middle">Authenticated AI Agents &amp; NS-3 Harness</text>
  </g>

  <!-- LAYER 4: NORTHBOUND INTENT & INVENTORY -->
  <g transform="translate(60, 210)">
    <rect width="1080" height="95" rx="10" fill="#172554" stroke="#3B82F6" stroke-width="2"/>
    <rect width="260" height="95" rx="10" fill="url(#l4grad)"/>
    <text x="130" y="38" font-family="Segoe UI, sans-serif" font-size="15" font-weight="bold" fill="#FFFFFF" text-anchor="middle">LAYER 4</text>
    <text x="130" y="58" font-family="Segoe UI, sans-serif" font-size="13" font-weight="bold" fill="#BFDBFE" text-anchor="middle">Intent &amp; Resource Abstraction</text>
    <text x="130" y="78" font-family="Segoe UI, sans-serif" font-size="11" fill="#93C5FD" text-anchor="middle">TM Forum Open APIs (ODA)</text>

    <!-- Sub-blocks -->
    <rect x="280" y="15" width="240" height="65" rx="6" fill="#1E3A8A" stroke="#2563EB" stroke-width="1"/>
    <text x="400" y="38" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#EFF6FF" text-anchor="middle">TMF921 Intent Management</text>
    <text x="400" y="58" font-family="Segoe UI, sans-serif" font-size="10" fill="#BFDBFE" text-anchor="middle">Declarative SLA (Latency &lt; 1.5ms, 5Nines)</text>

    <rect x="540" y="15" width="250" height="65" rx="6" fill="#1E3A8A" stroke="#2563EB" stroke-width="1"/>
    <text x="665" y="38" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#EFF6FF" text-anchor="middle">TMF639 Resource Inventory</text>
    <text x="665" y="58" font-family="Segoe UI, sans-serif" font-size="10" fill="#BFDBFE" text-anchor="middle">Standardized Multi-Vendor Equipment Graph</text>

    <rect x="810" y="15" width="250" height="65" rx="6" fill="#1E3A8A" stroke="#2563EB" stroke-width="1"/>
    <text x="935" y="38" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#EFF6FF" text-anchor="middle">Applications &amp; Orchestrators</text>
    <text x="935" y="58" font-family="Segoe UI, sans-serif" font-size="10" fill="#BFDBFE" text-anchor="middle">RCA, Planning, Cognitive Energy Savers</text>
  </g>

  <!-- LAYER 2: DIGITAL TWIN INTERFACE (DTI) -->
  <g transform="translate(60, 325)">
    <rect width="1080" height="110" rx="10" fill="#064E3B" stroke="#10B981" stroke-width="2"/>
    <rect width="260" height="110" rx="10" fill="url(#l2grad)"/>
    <text x="130" y="42" font-family="Segoe UI, sans-serif" font-size="15" font-weight="bold" fill="#FFFFFF" text-anchor="middle">LAYER 2</text>
    <text x="130" y="62" font-family="Segoe UI, sans-serif" font-size="13" font-weight="bold" fill="#A7F3D0" text-anchor="middle">Digital Twin Interface (DTI)</text>
    <text x="130" y="82" font-family="Segoe UI, sans-serif" font-size="11" fill="#6EE7B7" text-anchor="middle">IETF NMRG &amp; 3GPP TS 28.561</text>

    <!-- Sub-blocks -->
    <rect x="280" y="18" width="240" height="74" rx="6" fill="#047857" stroke="#10B981" stroke-width="1"/>
    <text x="400" y="42" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#ECFDF5" text-anchor="middle">3GPP TS 28.561 NDTI Lifecycle</text>
    <text x="400" y="62" font-family="Segoe UI, sans-serif" font-size="10" fill="#A7F3D0" text-anchor="middle">Create, Init, Sync, Experiment, Terminate</text>
    <text x="400" y="78" font-family="Segoe UI, sans-serif" font-size="10" fill="#D1FAE5" text-anchor="middle">State Machine &amp; Shadow Manager</text>

    <rect x="540" y="18" width="250" height="74" rx="6" fill="#047857" stroke="#10B981" stroke-width="1"/>
    <text x="665" y="42" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#ECFDF5" text-anchor="middle">IETF DTI What-If Scenarios</text>
    <text x="665" y="62" font-family="Segoe UI, sans-serif" font-size="10" fill="#A7F3D0" text-anchor="middle">POST /digitalTwin/scenarios</text>
    <text x="665" y="78" font-family="Segoe UI, sans-serif" font-size="10" fill="#D1FAE5" text-anchor="middle">Perturbation Vector &amp; SLA Predictor</text>

    <rect x="810" y="18" width="250" height="74" rx="6" fill="#047857" stroke="#10B981" stroke-width="1"/>
    <text x="935" y="42" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#ECFDF5" text-anchor="middle">NS-3 &amp; Analytical Models</text>
    <text x="935" y="62" font-family="Segoe UI, sans-serif" font-size="10" fill="#A7F3D0" text-anchor="middle">C++ PointToPoint &amp; ErrorModels</text>
    <text x="935" y="78" font-family="Segoe UI, sans-serif" font-size="10" fill="#D1FAE5" text-anchor="middle">ITU-R P.838 Rain &amp; Shannon Capacity</text>
  </g>

  <!-- LAYER 3: CLOSED-LOOP ACTUATION -->
  <g transform="translate(60, 455)">
    <rect width="1080" height="95" rx="10" fill="#431407" stroke="#F97316" stroke-width="2"/>
    <rect width="260" height="95" rx="10" fill="url(#l3grad)"/>
    <text x="130" y="38" font-family="Segoe UI, sans-serif" font-size="15" font-weight="bold" fill="#FFFFFF" text-anchor="middle">LAYER 3</text>
    <text x="130" y="58" font-family="Segoe UI, sans-serif" font-size="13" font-weight="bold" fill="#FED7AA" text-anchor="middle">Closed-Loop Actuation</text>
    <text x="130" y="78" font-family="Segoe UI, sans-serif" font-size="11" fill="#FDBA74" text-anchor="middle">Pre-Commit Safety &amp; TFS 2PC</text>

    <!-- Sub-blocks -->
    <rect x="280" y="15" width="240" height="65" rx="6" fill="#7C2D12" stroke="#EA580C" stroke-width="1"/>
    <text x="400" y="38" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#FFF7ED" text-anchor="middle">Pre-Flight Safety Verifier</text>
    <text x="400" y="58" font-family="Segoe UI, sans-serif" font-size="10" fill="#FED7AA" text-anchor="middle">RF EIRP, 57-71GHz Bands, Thermal</text>

    <rect x="540" y="15" width="250" height="65" rx="6" fill="#7C2D12" stroke="#EA580C" stroke-width="1"/>
    <text x="665" y="38" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#FFF7ED" text-anchor="middle">TFS Device Service (2PC)</text>
    <text x="665" y="58" font-family="Segoe UI, sans-serif" font-size="10" fill="#FED7AA" text-anchor="middle">Candidate Datastore Atomic Commit</text>

    <rect x="810" y="15" width="250" height="65" rx="6" fill="#7C2D12" stroke="#EA580C" stroke-width="1"/>
    <text x="935" y="38" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#FFF7ED" text-anchor="middle">Transport Configuration Rules</text>
    <text x="935" y="58" font-family="Segoe UI, sans-serif" font-size="10" fill="#FED7AA" text-anchor="middle">/radio/tuning, /modulation/acm_floor</text>
  </g>

  <!-- LAYER 1: SOUTHBOUND SYNCHRONIZATION -->
  <g transform="translate(60, 570)">
    <rect width="1080" height="110" rx="10" fill="#0F172A" stroke="#475569" stroke-width="2"/>
    <rect width="260" height="110" rx="10" fill="url(#l1grad)"/>
    <text x="130" y="42" font-family="Segoe UI, sans-serif" font-size="15" font-weight="bold" fill="#FFFFFF" text-anchor="middle">LAYER 1</text>
    <text x="130" y="62" font-family="Segoe UI, sans-serif" font-size="13" font-weight="bold" fill="#94A3B8" text-anchor="middle">Southbound Sync &amp; Hardware</text>
    <text x="130" y="82" font-family="Segoe UI, sans-serif" font-size="11" fill="#64748B" text-anchor="middle">RESTCONF, NETCONF, gNMI</text>

    <!-- Sub-blocks -->
    <rect x="280" y="18" width="240" height="74" rx="6" fill="#1E293B" stroke="#475569" stroke-width="1"/>
    <text x="400" y="42" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#F8FAFC" text-anchor="middle">Physical Ceragon Elements</text>
    <text x="400" y="62" font-family="Segoe UI, sans-serif" font-size="10" fill="#94A3B8" text-anchor="middle">MultiHaul TG MH-T261, N366, IP-50</text>
    <text x="400" y="78" font-family="Segoe UI, sans-serif" font-size="10" fill="#CBD5E1" text-anchor="middle">Ethernet Ports, 60GHz Phased Arrays</text>

    <rect x="540" y="18" width="250" height="74" rx="6" fill="#1E293B" stroke="#475569" stroke-width="1"/>
    <text x="665" y="42" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#F8FAFC" text-anchor="middle">RFC 8040 RESTCONF 2PC</text>
    <text x="665" y="62" font-family="Segoe UI, sans-serif" font-size="10" fill="#94A3B8" text-anchor="middle">/restconf/ds/ietf-datastores:candidate</text>
    <text x="665" y="78" font-family="Segoe UI, sans-serif" font-size="10" fill="#CBD5E1" text-anchor="middle">51 YANG Models Extracted</text>

    <rect x="810" y="18" width="250" height="74" rx="6" fill="#1E293B" stroke="#475569" stroke-width="1"/>
    <text x="935" y="42" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#F8FAFC" text-anchor="middle">Real-Time Telemetry Feed</text>
    <text x="935" y="62" font-family="Segoe UI, sans-serif" font-size="10" fill="#94A3B8" text-anchor="middle">RSL, SNR, MCS, ATPC Tx Power</text>
    <text x="935" y="78" font-family="Segoe UI, sans-serif" font-size="10" fill="#CBD5E1" text-anchor="middle">Modem Temperature, Octet Counters</text>
  </g>
</svg>
"""

with open(os.path.join(FIGURES_DIR, "telecom_ndt_5layer_architecture.svg"), "w", encoding="utf-8") as f:
    f.write(FIG2_SVG)


# ==============================================================================
# FIGURE 3: 3GPP TS 28.561 NDTI Instance Lifecycle State Machine
# ==============================================================================
FIG3_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 600" width="100%" height="100%">
  <defs>
    <linearGradient id="stateGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1E293B"/><stop offset="100%" stop-color="#0F172A"/>
    </linearGradient>
    <linearGradient id="syncGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#065F46"/><stop offset="100%" stop-color="#047857"/>
    </linearGradient>
    <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#38BDF8"/>
    </marker>
    <marker id="arrowGreen" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#34D399"/>
    </marker>
    <marker id="arrowOrange" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#FB923C"/>
    </marker>
  </defs>

  <rect width="1000" height="600" fill="#0B0F19"/>

  <text x="500" y="45" font-family="Segoe UI, sans-serif" font-size="22" font-weight="bold" fill="#F8FAFC" text-anchor="middle">
    3GPP TS 28.561 (RELEASE 19 SA5) NDTI LIFECYCLE STATE MACHINE
  </text>
  <text x="500" y="70" font-family="Segoe UI, sans-serif" font-size="13" fill="#94A3B8" text-anchor="middle">
    Standardized Lifecycle Management of Network Digital Twin Instances (NDTI) via NDTMF
  </text>

  <!-- STATE: NULL -->
  <g transform="translate(410, 100)">
    <rect width="180" height="50" rx="8" fill="url(#stateGrad)" stroke="#64748B" stroke-width="2"/>
    <text x="90" y="32" font-family="Segoe UI, sans-serif" font-size="14" font-weight="bold" fill="#94A3B8" text-anchor="middle">NULL</text>
  </g>

  <!-- TRANSITION: CreateNDTI -->
  <line x1="500" y1="150" x2="500" y2="200" stroke="#38BDF8" stroke-width="2.5" marker-end="url(#arrow)"/>
  <text x="515" y="180" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#38BDF8">CreateNDTI</text>

  <!-- STATE: INITIALIZING -->
  <g transform="translate(400, 205)">
    <rect width="200" height="55" rx="8" fill="url(#stateGrad)" stroke="#38BDF8" stroke-width="2"/>
    <text x="100" y="34" font-family="Segoe UI, sans-serif" font-size="14" font-weight="bold" fill="#38BDF8" text-anchor="middle">INITIALIZING</text>
  </g>

  <!-- TRANSITION: InitializeNDTI -->
  <line x1="500" y1="260" x2="500" y2="310" stroke="#34D399" stroke-width="2.5" marker-end="url(#arrowGreen)"/>
  <text x="515" y="290" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#34D399">InitializeNDTI</text>

  <!-- STATE: SYNCHRONIZED (Core Operating State) -->
  <g transform="translate(370, 315)">
    <rect width="260" height="65" rx="10" fill="url(#syncGrad)" stroke="#34D399" stroke-width="2.5"/>
    <text x="130" y="35" font-family="Segoe UI, sans-serif" font-size="15" font-weight="bold" fill="#FFFFFF" text-anchor="middle">SYNCHRONIZED</text>
    <text x="130" y="52" font-family="Segoe UI, sans-serif" font-size="11" fill="#A7F3D0" text-anchor="middle">Shadow Reconciled with Physical Hardware</text>
  </g>

  <!-- LOOP: UPDATING (SyncNDTI) on the Left -->
  <g transform="translate(100, 315)">
    <rect width="180" height="65" rx="8" fill="url(#stateGrad)" stroke="#F59E0B" stroke-width="2"/>
    <text x="90" y="35" font-family="Segoe UI, sans-serif" font-size="14" font-weight="bold" fill="#F59E0B" text-anchor="middle">UPDATING</text>
    <text x="90" y="52" font-family="Segoe UI, sans-serif" font-size="11" fill="#FCD34D" text-anchor="middle">Telemetry Sync</text>
  </g>
  <!-- SyncNDTI Arrow to UPDATING -->
  <path d="M 370,335 L 280,335" stroke="#F59E0B" stroke-width="2" marker-end="url(#arrowOrange)"/>
  <text x="325" y="325" font-family="Segoe UI, sans-serif" font-size="10" font-weight="bold" fill="#F59E0B" text-anchor="middle">SyncNDTI</text>
  <!-- Return Arrow from UPDATING -->
  <path d="M 280,360 L 370,360" stroke="#34D399" stroke-width="2" marker-end="url(#arrowGreen)"/>
  <text x="325" y="375" font-family="Segoe UI, sans-serif" font-size="10" font-weight="bold" fill="#34D399" text-anchor="middle">Updated</text>

  <!-- LOOP: EXECUTING_EXPERIMENT (What-If Scenarios) on the Right -->
  <g transform="translate(720, 315)">
    <rect width="210" height="65" rx="8" fill="url(#stateGrad)" stroke="#A855F7" stroke-width="2"/>
    <text x="105" y="32" font-family="Segoe UI, sans-serif" font-size="13" font-weight="bold" fill="#C084FC" text-anchor="middle">EXECUTING_EXPERIMENT</text>
    <text x="105" y="50" font-family="Segoe UI, sans-serif" font-size="11" fill="#E9D5FF" text-anchor="middle">NS-3 / ITU-R P.838 Sandbox</text>
  </g>
  <!-- ExecuteExperiment Arrow -->
  <path d="M 630,335 L 720,335" stroke="#C084FC" stroke-width="2" marker-end="url(#arrow)"/>
  <text x="675" y="325" font-family="Segoe UI, sans-serif" font-size="10" font-weight="bold" fill="#C084FC" text-anchor="middle">ExecuteExperiment</text>
  <!-- RetrieveResults Return Arrow -->
  <path d="M 720,360 L 630,360" stroke="#34D399" stroke-width="2" marker-end="url(#arrowGreen)"/>
  <text x="675" y="375" font-family="Segoe UI, sans-serif" font-size="10" font-weight="bold" fill="#34D399" text-anchor="middle">RetrieveResults</text>

  <!-- TRANSITION: TerminateNDTI -->
  <line x1="500" y1="380" x2="500" y2="470" stroke="#EF4444" stroke-width="2.5" marker-end="url(#arrow)"/>
  <text x="515" y="430" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#EF4444">TerminateNDTI</text>

  <!-- STATE: TERMINATED -->
  <g transform="translate(400, 475)">
    <rect width="200" height="55" rx="8" fill="url(#stateGrad)" stroke="#EF4444" stroke-width="2"/>
    <text x="100" y="34" font-family="Segoe UI, sans-serif" font-size="14" font-weight="bold" fill="#EF4444" text-anchor="middle">TERMINATED</text>
  </g>
</svg>
"""

with open(os.path.join(FIGURES_DIR, "3gpp_ts28561_ndti_lifecycle.svg"), "w", encoding="utf-8") as f:
    f.write(FIG3_SVG)


# ==============================================================================
# FIGURE 4: Technical Closed-Loop Sequence Diagram (SVG)
# ==============================================================================
FIG4_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 700" width="100%" height="100%">
  <defs>
    <marker id="seqArrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#38BDF8"/>
    </marker>
    <marker id="seqArrowGreen" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#10B981"/>
    </marker>
    <marker id="seqArrowOrange" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#F59E0B"/>
    </marker>
  </defs>

  <rect width="1100" height="700" fill="#0B0F19"/>

  <text x="550" y="40" font-family="Segoe UI, sans-serif" font-size="22" font-weight="bold" fill="#F8FAFC" text-anchor="middle">
    CLOSED-LOOP TELECOM DIGITAL TWIN ACTUATION WORKFLOW
  </text>
  <text x="550" y="65" font-family="Segoe UI, sans-serif" font-size="13" fill="#94A3B8" text-anchor="middle">
    From Declarative SLA Intent &amp; What-If Evaluation to Hardware 2PC Commit
  </text>

  <!-- Lifelines -->
  <!-- 1. AI Orchestrator -->
  <g transform="translate(100, 90)">
    <rect width="140" height="40" rx="6" fill="#1E293B" stroke="#8B5CF6" stroke-width="2"/>
    <text x="70" y="25" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#DDD6FE" text-anchor="middle">AI Orchestrator</text>
    <line x1="70" y1="40" x2="70" y2="570" stroke="#334155" stroke-width="1.5" stroke-dasharray="4 4"/>
  </g>

  <!-- 2. CAPIF Gateway -->
  <g transform="translate(300, 90)">
    <rect width="140" height="40" rx="6" fill="#1E293B" stroke="#3B82F6" stroke-width="2"/>
    <text x="70" y="25" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#BFDBFE" text-anchor="middle">3GPP CAPIF (L5)</text>
    <line x1="70" y1="40" x2="70" y2="570" stroke="#334155" stroke-width="1.5" stroke-dasharray="4 4"/>
  </g>

  <!-- 3. Digital Twin (DTI) -->
  <g transform="translate(500, 90)">
    <rect width="140" height="40" rx="6" fill="#1E293B" stroke="#10B981" stroke-width="2"/>
    <text x="70" y="25" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#A7F3D0" text-anchor="middle">Digital Twin (DTI)</text>
    <line x1="70" y1="40" x2="70" y2="570" stroke="#334155" stroke-width="1.5" stroke-dasharray="4 4"/>
  </g>

  <!-- 4. NS-3 Simulator -->
  <g transform="translate(700, 90)">
    <rect width="140" height="40" rx="6" fill="#1E293B" stroke="#F59E0B" stroke-width="2"/>
    <text x="70" y="25" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#FDE68A" text-anchor="middle">NS-3 Simulator</text>
    <line x1="70" y1="40" x2="70" y2="570" stroke="#334155" stroke-width="1.5" stroke-dasharray="4 4"/>
  </g>

  <!-- 5. TFS & Ceragon HW -->
  <g transform="translate(900, 90)">
    <rect width="150" height="40" rx="6" fill="#1E293B" stroke="#EF4444" stroke-width="2"/>
    <text x="75" y="25" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#FECACA" text-anchor="middle">TFS / Ceragon HW</text>
    <line x1="75" y1="40" x2="75" y2="570" stroke="#334155" stroke-width="1.5" stroke-dasharray="4 4"/>
  </g>

  <!-- Sequence Messages -->
  <!-- Step 1: Discover via CAPIF -->
  <line x1="170" y1="160" x2="370" y2="160" stroke="#8B5CF6" stroke-width="2" marker-end="url(#seqArrow)"/>
  <text x="270" y="152" font-family="Segoe UI, sans-serif" font-size="11" fill="#DDD6FE" text-anchor="middle">1. GET /capif/service-apis (Discover DTI)</text>

  <!-- Step 2: Ingest TMF921 Intent -->
  <line x1="170" y1="210" x2="570" y2="210" stroke="#3B82F6" stroke-width="2" marker-end="url(#seqArrow)"/>
  <text x="370" y="202" font-family="Segoe UI, sans-serif" font-size="11" fill="#BFDBFE" text-anchor="middle">2. POST /tmf921/intent (SLA: Latency &lt; 1.5ms)</text>

  <!-- Step 3: Layer 1 Background Sync -->
  <line x1="975" y1="260" x2="570" y2="260" stroke="#10B981" stroke-width="2" stroke-dasharray="4 3" marker-end="url(#seqArrowGreen)"/>
  <text x="770" y="252" font-family="Segoe UI, sans-serif" font-size="11" fill="#A7F3D0" text-anchor="middle">3. Real-Time Telemetry Sync (RSL, MCS 8, Freq)</text>

  <!-- Step 4: What-If Perturbation -->
  <line x1="170" y1="310" x2="570" y2="310" stroke="#F59E0B" stroke-width="2" marker-end="url(#seqArrowOrange)"/>
  <text x="370" y="302" font-family="Segoe UI, sans-serif" font-size="11" fill="#FDE68A" text-anchor="middle">4. POST /dti/scenarios (Rain 55mm/hr Perturbation)</text>

  <!-- Step 5: Simulation Execution in NS-3 -->
  <line x1="570" y1="360" x2="770" y2="360" stroke="#F59E0B" stroke-width="2" marker-end="url(#seqArrowOrange)"/>
  <text x="670" y="352" font-family="Segoe UI, sans-serif" font-size="11" fill="#FDE68A" text-anchor="middle">5. Run Discrete-Event Simulation</text>

  <!-- Step 6: NS-3 Prediction Result -->
  <line x1="770" y1="410" x2="570" y2="410" stroke="#EF4444" stroke-width="2" marker-end="url(#seqArrow)"/>
  <text x="670" y="402" font-family="Segoe UI, sans-serif" font-size="11" fill="#FCA5A5" text-anchor="middle">6. Predicted Breach (MCS 0, Loss 8%, Latency 6.8ms)</text>

  <!-- Step 7: Mitigation Computed & Validated -->
  <rect x="530" y="435" width="80" height="30" rx="4" fill="#065F46" stroke="#34D399" stroke-width="1.5"/>
  <text x="570" y="454" font-family="Segoe UI, sans-serif" font-size="10" font-weight="bold" fill="#FFFFFF" text-anchor="middle">Safety Check</text>

  <!-- Step 8: Closed Loop TFS 2PC Commit -->
  <line x1="570" y1="490" x2="975" y2="490" stroke="#10B981" stroke-width="2.5" marker-end="url(#seqArrowGreen)"/>
  <text x="770" y="482" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#34D399" text-anchor="middle">8. 2PC Commit: /modulation/acm_floor &amp; /radio/tuning</text>

  <!-- Step 9: Hardware Reconfigured & Verified -->
  <line x1="975" y1="540" x2="170" y2="540" stroke="#10B981" stroke-width="2" stroke-dasharray="6 4" marker-end="url(#seqArrowGreen)"/>
  <text x="570" y="532" font-family="Segoe UI, sans-serif" font-size="11" fill="#A7F3D0" text-anchor="middle">9. Closed-Loop Success: Physical HW Reconfigured, SLA Preserved</text>
</svg>
"""

with open(os.path.join(FIGURES_DIR, "closed_loop_sequence_diagram.svg"), "w", encoding="utf-8") as f:
    f.write(FIG4_SVG)


# ==============================================================================
# FIGURE 5: Scientific Propagation & Modulation Curves (Matplotlib PNG)
# ==============================================================================
fig, axes = plt.subplots(2, 2, figsize=(14, 10), facecolor="#0B132B")
plt.subplots_adjust(hspace=0.35, wspace=0.3)

for ax in axes.flat:
    ax.set_facecolor("#1C2541")
    ax.tick_params(colors="#94A3B8", labelsize=10)
    for spine in ax.spines.values():
        spine.set_color("#334155")
    ax.grid(True, linestyle="--", alpha=0.3, color="#64748B")

# Subplot 1: ITU-R P.838 Rain Attenuation vs Rain Rate
r_rates = np.linspace(1, 100, 200) # mm/hr
# ITU-R P.838: gamma_R = k * R^alpha
# 60 GHz (V-band): k=0.85, alpha=0.80
# 73 GHz (E-band): k=1.05, alpha=0.76
# 18 GHz (Microwave): k=0.07, alpha=1.08
atten_60 = 0.85 * (r_rates ** 0.80)
atten_73 = 1.05 * (r_rates ** 0.76)
atten_18 = 0.07 * (r_rates ** 1.08)

ax1 = axes[0, 0]
ax1.plot(r_rates, atten_60, color="#38BDF8", linewidth=2.5, label="60 GHz V-Band (MultiHaul TG)")
ax1.plot(r_rates, atten_73, color="#F59E0B", linewidth=2.5, label="73 GHz E-Band (EtherHaul)")
ax1.plot(r_rates, atten_18, color="#10B981", linewidth=2.5, label="18 GHz Microwave (IP-50)")
ax1.axvline(x=55, color="#EF4444", linestyle=":", linewidth=2, label="Simulated Storm (55 mm/hr)")
ax1.set_title("ITU-R P.838-3 Specific Rain Attenuation", color="#F8FAFC", fontsize=12, fontweight="bold")
ax1.set_xlabel("Rain Rate (mm/hr)", color="#CBD5E1", fontsize=10)
ax1.set_ylabel("Specific Attenuation (dB/km)", color="#CBD5E1", fontsize=10)
ax1.legend(facecolor="#0B132B", edgecolor="#334155", labelcolor="#F8FAFC", fontsize=9)

# Subplot 2: SINR vs Distance under 55 mm/hr Rain Fade
dists = np.linspace(0.1, 2.0, 200) # km
# Free Space Path Loss (60 GHz) + Oxygen Absorption (~15 dB/km) + Rain Attenuation (19.9 dB/km)
fspl_60 = 20 * np.log10(dists * 1000) + 20 * np.log10(60000) - 147.55
total_loss_clean = fspl_60 + (15.0 * dists)
total_loss_rain = total_loss_clean + (21.0 * dists)

# EIRP=40 dBm, Rx Gain=30 dBi, Noise Floor=-85 dBm
sinr_clean = 40 + 30 - total_loss_clean - (-85)
sinr_rain = 40 + 30 - total_loss_rain - (-85)

ax2 = axes[0, 1]
ax2.plot(dists, sinr_clean, color="#10B981", linewidth=2.5, label="Clear Air SINR")
ax2.plot(dists, sinr_rain, color="#EF4444", linewidth=2.5, label="55 mm/hr Rain Faded SINR")
ax2.axhline(y=14.0, color="#F59E0B", linestyle="--", linewidth=1.5, label="Min QPSK MCS 2 Threshold")
ax2.set_title("mmWave Carrier SINR Degradation vs Path Distance", color="#F8FAFC", fontsize=12, fontweight="bold")
ax2.set_xlabel("Link Distance (km)", color="#CBD5E1", fontsize=10)
ax2.set_ylabel("Effective SINR (dB)", color="#CBD5E1", fontsize=10)
ax2.legend(facecolor="#0B132B", edgecolor="#334155", labelcolor="#F8FAFC", fontsize=9)

# Subplot 3: Ceragon Hitless ACM MCS Modulation & Throughput
mcs_indices = np.arange(0, 10)
mcs_rates = np.array([50, 180, 260, 380, 500, 650, 800, 920, 1000, 1200]) # Mbps
mcs_colors = ["#EF4444" if r < 500 else "#10B981" for r in mcs_rates]

ax3 = axes[1, 0]
bars = ax3.bar(mcs_indices, mcs_rates, color=mcs_colors, edgecolor="#0B132B", width=0.6)
ax3.axhline(y=500, color="#F59E0B", linestyle="--", linewidth=2, label="SLA 500 Mbps Threshold")
ax3.set_title("Ceragon Hitless ACM Modulation vs Capacity", color="#F8FAFC", fontsize=12, fontweight="bold")
ax3.set_xlabel("ACM Modulation Index (MCS)", color="#CBD5E1", fontsize=10)
ax3.set_ylabel("Physical Throughput (Mbps)", color="#CBD5E1", fontsize=10)
ax3.set_xticks(mcs_indices)
ax3.set_xticklabels([f"MCS {i}" for i in mcs_indices])
ax3.legend(facecolor="#0B132B", edgecolor="#334155", labelcolor="#F8FAFC", fontsize=9)

# Subplot 4: NS-3 Queueing Delay & SLA Violation Simulation
snr_sweep = np.linspace(2, 28, 100)
# Latency model: Base propagation (0.85ms) + queue congestion delay
latency_sim = 0.85 + (32.0 / (snr_sweep + 0.5))

ax4 = axes[1, 1]
ax4.plot(snr_sweep, latency_sim, color="#38BDF8", linewidth=2.5, label="NS-3 Simulated Latency")
ax4.axhline(y=1.5, color="#EF4444", linestyle="--", linewidth=2, label="TMF921 Intent SLA Limit (1.5ms)")
ax4.fill_between(snr_sweep, 1.5, 8.0, where=(latency_sim >= 1.5), color="#EF4444", alpha=0.15, label="SLA Breach Zone")
ax4.set_title("NS-3 Discrete-Event Packet Latency vs RF SINR", color="#F8FAFC", fontsize=12, fontweight="bold")
ax4.set_xlabel("Link SINR (dB)", color="#CBD5E1", fontsize=10)
ax4.set_ylabel("One-Way Latency (ms)", color="#CBD5E1", fontsize=10)
ax4.legend(facecolor="#0B132B", edgecolor="#334155", labelcolor="#F8FAFC", fontsize=9)

fig.suptitle("TELECOM DIGITAL TWIN (NDT) MULTI-FIDELITY PROPAGATION & PERFORMANCE MODELS", 
             color="#F8FAFC", fontsize=15, fontweight="bold", y=0.98)

plt.savefig(os.path.join(FIGURES_DIR, "rain_attenuation_and_acm_curves.png"), dpi=200, bbox_inches="tight")
plt.close()

# ==============================================================================
# FIGURE 6: Generic Telecom Simulation Taxonomy (Multi-Domain Platform)
# ==============================================================================
FIG6_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 780" width="100%" height="100%">
  <defs>
    <linearGradient id="centerGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0F172A"/><stop offset="100%" stop-color="#1E293B"/>
    </linearGradient>
    <linearGradient id="cardGrad1" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#1E3A8A"/><stop offset="100%" stop-color="#2563EB"/>
    </linearGradient>
    <linearGradient id="cardGrad2" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#7C2D12"/><stop offset="100%" stop-color="#EA580C"/>
    </linearGradient>
    <linearGradient id="cardGrad3" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#065F46"/><stop offset="100%" stop-color="#059669"/>
    </linearGradient>
    <linearGradient id="cardGrad4" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#4C1D95"/><stop offset="100%" stop-color="#7C3AED"/>
    </linearGradient>
    <linearGradient id="cardGrad5" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#831843"/><stop offset="100%" stop-color="#DB2777"/>
    </linearGradient>
    <linearGradient id="cardGrad6" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#14532D"/><stop offset="100%" stop-color="#16A34A"/>
    </linearGradient>
    <filter id="glowCenter" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="8" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>

  <rect width="1200" height="780" fill="#0B0F19"/>

  <text x="600" y="42" font-family="Segoe UI, sans-serif" font-size="24" font-weight="bold" fill="#F8FAFC" text-anchor="middle" letter-spacing="1">
    GENERIC TELECOM NETWORK DIGITAL TWIN SIMULATION TAXONOMY
  </text>
  <text x="600" y="68" font-family="Segoe UI, sans-serif" font-size="13" fill="#94A3B8" text-anchor="middle">
    Universal Multi-Domain Evaluation Engine Powered by NS-3 Co-Simulation, IETF DTI, and ETSI TeraFlowSDN
  </text>

  <!-- CENTRAL HUB: THE UNIVERSAL DIGITAL TWIN CORE -->
  <g transform="translate(450, 270)">
    <rect width="300" height="210" rx="16" fill="url(#centerGrad)" stroke="#38BDF8" stroke-width="2.5" filter="url(#glowCenter)"/>
    <circle cx="150" cy="55" r="28" fill="#0284C7" stroke="#38BDF8" stroke-width="2"/>
    <path d="M140,55 L160,55 M150,45 L150,65" stroke="#FFFFFF" stroke-width="2.5"/>
    <text x="150" y="110" font-family="Segoe UI, sans-serif" font-size="16" font-weight="bold" fill="#F8FAFC" text-anchor="middle">
      UNIVERSAL NDT CORE
    </text>
    <text x="150" y="130" font-family="Segoe UI, sans-serif" font-size="12" font-weight="bold" fill="#38BDF8" text-anchor="middle">
      NS-3 C++ Discrete-Event Engine
    </text>
    <text x="150" y="152" font-family="Segoe UI, sans-serif" font-size="11" fill="#94A3B8" text-anchor="middle">
      3GPP TS 28.561 NDTI Lifecycle
    </text>
    <text x="150" y="172" font-family="Segoe UI, sans-serif" font-size="11" fill="#94A3B8" text-anchor="middle">
      IETF NMRG DTI Scenario Dispatcher
    </text>
    <text x="150" y="192" font-family="Segoe UI, sans-serif" font-size="11" fill="#34D399" text-anchor="middle">
      ETSI TeraFlowSDN 2PC Closed Loop
    </text>
  </g>

  <!-- DOMAIN 1: TRAFFIC & CONGESTION DYNAMICS (Top Left) -->
  <g transform="translate(50, 100)">
    <rect width="350" height="175" rx="12" fill="#0F172A" stroke="#2563EB" stroke-width="2"/>
    <rect width="350" height="38" rx="12" fill="url(#cardGrad1)"/>
    <text x="175" y="24" font-family="Segoe UI, sans-serif" font-size="14" font-weight="bold" fill="#FFFFFF" text-anchor="middle">
      1. Traffic &amp; Congestion Engineering
    </text>
    <text x="20" y="65" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Flash-Crowd Surges &amp; Stadium Bursts (3-5x traffic)</text>
    <text x="20" y="87" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Bufferbloat, Queue Overflow &amp; Active Queue Mgmt</text>
    <text x="20" y="109" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• CoDel / RED / PIE AQM Discipline Optimization</text>
    <text x="20" y="131" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• TCP BBR vs Cubic vs Paced UDP Video Workloads</text>
    <text x="20" y="153" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#60A5FA">→ Predicts: Latency spikes, Jitter, Packet Drop %</text>
  </g>

  <!-- DOMAIN 2: TOPOLOGY RESILIENCE & FAILOVERS (Top Right) -->
  <g transform="translate(800, 100)">
    <rect width="350" height="175" rx="12" fill="#0F172A" stroke="#EA580C" stroke-width="2"/>
    <rect width="350" height="38" rx="12" fill="url(#cardGrad2)"/>
    <text x="175" y="24" font-family="Segoe UI, sans-serif" font-size="14" font-weight="bold" fill="#FFFFFF" text-anchor="middle">
      2. Topology Resilience &amp; Failover
    </text>
    <text x="20" y="65" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Fiber Cuts &amp; Core Transport Disconnections</text>
    <text x="20" y="87" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Carrier-Grade Sub-50ms Protection Switching</text>
    <text x="20" y="109" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Topology-Independent LFA (TI-LFA) Fast Reroute</text>
    <text x="20" y="131" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Routing Storms &amp; IGP/BGP Convergence Delay</text>
    <text x="20" y="153" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#F97316">→ Predicts: Switchover time, Backup capacity surge</text>
  </g>

  <!-- DOMAIN 3: QOS SLICING & MULTI-TENANCY (Middle Left) -->
  <g transform="translate(50, 310)">
    <rect width="350" height="175" rx="12" fill="#0F172A" stroke="#059669" stroke-width="2"/>
    <rect width="350" height="38" rx="12" fill="url(#cardGrad3)"/>
    <text x="175" y="24" font-family="Segoe UI, sans-serif" font-size="14" font-weight="bold" fill="#FFFFFF" text-anchor="middle">
      3. 5G/6G QoS &amp; Multi-Tenant Slicing
    </text>
    <text x="20" y="65" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Multi-Slice Admission Control (Pre-flight test)</text>
    <text x="20" y="87" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• URLLC vs eMBB vs mMTC Slice Isolation</text>
    <text x="20" y="109" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Packet Delay Budget (PDB) &amp; PER Verification</text>
    <text x="20" y="131" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Token-Bucket CBS/EBS Dynamic Policing</text>
    <text x="20" y="153" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#34D399">→ Predicts: Slice starvation, SLA compliance</text>
  </g>

  <!-- DOMAIN 4: GREEN TELCO & ENERGY OPTIMIZATION (Middle Right) -->
  <g transform="translate(800, 310)">
    <rect width="350" height="175" rx="12" fill="#0F172A" stroke="#16A34A" stroke-width="2"/>
    <rect width="350" height="38" rx="12" fill="url(#cardGrad6)"/>
    <text x="175" y="24" font-family="Segoe UI, sans-serif" font-size="14" font-weight="bold" fill="#FFFFFF" text-anchor="middle">
      4. Green Telco &amp; Energy Optimization
    </text>
    <text x="20" y="65" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Dynamic Carrier Sleep Modes (Off-peak windows)</text>
    <text x="20" y="87" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Redundant Radio Sector Power-Down (Watts saved)</text>
    <text x="20" y="109" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Traffic Steering to Low-Power Concentrators</text>
    <text x="20" y="131" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Verification that Sleep Modes Do Not Breach SLAs</text>
    <text x="20" y="153" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#4ADE80">→ Predicts: kWh savings, Residual headroom</text>
  </g>

  <!-- DOMAIN 5: PHYSICAL PROPAGATION & OBSTACLES (Bottom Left) -->
  <g transform="translate(50, 520)">
    <rect width="350" height="175" rx="12" fill="#0F172A" stroke="#7C3AED" stroke-width="2"/>
    <rect width="350" height="38" rx="12" fill="url(#cardGrad4)"/>
    <text x="175" y="24" font-family="Segoe UI, sans-serif" font-size="14" font-weight="bold" fill="#FFFFFF" text-anchor="middle">
      5. Physical Propagation &amp; Obstacles
    </text>
    <text x="20" y="65" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Urban Line-of-Sight Blockage (Cranes, Buildings)</text>
    <text x="20" y="87" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Atmospheric Rain Fade (ITU-R P.838 mmWave)</text>
    <text x="20" y="109" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Oxygen Peak Absorption (~15 dB/km @ 60 GHz)</text>
    <text x="20" y="131" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Hitless ACM Adaptive Coding &amp; Modulation Steps</text>
    <text x="20" y="153" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#A78BFA">→ Predicts: SNR degradation, MCS stepdown, Capacity</text>
  </g>

  <!-- DOMAIN 6: MOBILITY & HANDOVER DYNAMICS (Bottom Right) -->
  <g transform="translate(800, 520)">
    <rect width="350" height="175" rx="12" fill="#0F172A" stroke="#DB2777" stroke-width="2"/>
    <rect width="350" height="38" rx="12" fill="url(#cardGrad5)"/>
    <text x="175" y="24" font-family="Segoe UI, sans-serif" font-size="14" font-weight="bold" fill="#FFFFFF" text-anchor="middle">
      6. Mobility &amp; Radio Handover Dynamics
    </text>
    <text x="20" y="65" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• High-Speed Train &amp; Vehicular V2X Trajectories</text>
    <text x="20" y="87" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Inter-gNB Xn / X2 Handover Interruption Time</text>
    <text x="20" y="109" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Phased Array Beam Tracking &amp; Mispointing Drift</text>
    <text x="20" y="131" font-family="Segoe UI, sans-serif" font-size="11" fill="#E2E8F0">• Multi-Connectivity &amp; Dual-Carrier Aggregation</text>
    <text x="20" y="153" font-family="Segoe UI, sans-serif" font-size="11" font-weight="bold" fill="#F472B6">→ Predicts: Handover success rate, Packet drops</text>
  </g>

  <!-- Connecting Lines from Hub to Domains -->
  <line x1="450" y1="330" x2="400" y2="240" stroke="#38BDF8" stroke-width="2" stroke-dasharray="4 4"/>
  <line x1="750" y1="330" x2="800" y2="240" stroke="#38BDF8" stroke-width="2" stroke-dasharray="4 4"/>
  <line x1="450" y1="390" x2="400" y2="390" stroke="#38BDF8" stroke-width="2" stroke-dasharray="4 4"/>
  <line x1="750" y1="390" x2="800" y2="390" stroke="#38BDF8" stroke-width="2" stroke-dasharray="4 4"/>
  <line x1="450" y1="440" x2="400" y2="540" stroke="#38BDF8" stroke-width="2" stroke-dasharray="4 4"/>
  <line x1="750" y1="440" x2="800" y2="540" stroke="#38BDF8" stroke-width="2" stroke-dasharray="4 4"/>
</svg>
"""

with open(os.path.join(FIGURES_DIR, "generic_telecom_simulation_taxonomy.svg"), "w", encoding="utf-8") as f:
    f.write(FIG6_SVG)

print("All figures successfully created including generic taxonomy in:", FIGURES_DIR)

