"""
Ceragon Product Portfolio Catalog
=================================
Single source of truth for which Ceragon / Siklu products the TFS REST adapter
understands, how each one is reached southbound (API flavor), and which
capabilities it declares to TeraFlowSDN.

Coverage strategy
-----------------
1. Explicit model entries for the known catalog (IP-20, IP-50, IP-100,
   EtherHaul, MultiHaul TG).
2. Family-level fallbacks so any *new or unlisted* variant (e.g. "IP-50XYZ",
   "EH-9010FX", "MH-N368") still resolves to the correct API flavor and a
   sane capability baseline instead of being treated as a 60 GHz Terragraph
   node or "Generic".

Data provenance (IMPORTANT)
---------------------------
* ``api_verified=True`` only for models whose southbound API was exercised
  against real hardware in this lab (MH-T261 over RESTCONF candidate DS).
* Every other entry is built from public product-catalog information.
  Capacities, bands and feature flags are *nominal* and must be validated
  against the official datasheets / CeraOS release notes before being used
  for planning or admission control.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, replace
from typing import Dict, List, Optional, Tuple

# ── API flavors ────────────────────────────────────────────────────────────────
# siklu_tg : Siklu/Ceragon MultiHaul TG (Terragraph). RESTCONF NMDA candidate DS,
#            radio-bridge-tg-* YANG modules (bundled in schemas/yang).
# siklu_eh : Siklu/Ceragon EtherHaul PtP. Shares the Siklu radio-bridge heritage;
#            probed with the same RESTCONF datastore paths. NOT lab-verified.
# ceraos   : Ceragon CeraOS (IP-20 / IP-50 / IP-100). RESTCONF /restconf/data.
#            Module paths used by the client are NOT lab-verified.
FLAVOR_SIKLU_TG = "siklu_tg"
FLAVOR_SIKLU_EH = "siklu_eh"
FLAVOR_CERAOS = "ceraos"

# Client-level protocol family (what the RESTCONF client actually speaks)
FLAVOR_TO_PROTOCOL = {
    FLAVOR_SIKLU_TG: "terragraph",
    FLAVOR_SIKLU_EH: "terragraph",
    FLAVOR_CERAOS: "ceraos",
}

# ── Feature vocabulary (aligned with cer_intent DeviceConfig.config_type) ─────
F_RADIO = "radio_tuning"
F_ACM = "acm"
F_SLICE = "slice"
F_QOS = "qos"
F_PROTECTION = "protection"
F_XPIC = "xpic"
F_MULTIBAND = "multiband"
F_MULTICARRIER = "multicarrier"
F_BEAMFORMING = "beamforming"
F_MESH = "mesh"
F_SYNC = "sync"
F_SECURITY = "security"
F_ENERGY = "energy"
F_TELEMETRY = "telemetry"
F_ROUTING = "routing"

BASE_FEATURES = (F_RADIO, F_ACM, F_SLICE, F_QOS, F_PROTECTION, F_TELEMETRY)


@dataclass(frozen=True)
class RadioBand:
    name: str               # "V-band", "E-band", "MW 6-42 GHz", "Sub-6 / LH"
    freq_min_ghz: float
    freq_max_ghz: float

    @property
    def endpoint_type(self) -> str:
        key = self.name.lower().replace(" ", "-").replace("/", "-")
        return f"radio-{key}"


V_BAND = RadioBand("V-band", 57.0, 71.0)
E_BAND = RadioBand("E-band", 71.0, 86.0)
MW_SHORT_HAUL = RadioBand("MW", 6.0, 42.0)
MW_LONG_HAUL = RadioBand("MW-LH", 4.0, 13.0)


@dataclass(frozen=True)
class ProductSpec:
    model: str
    family: str
    product_line: str
    api_flavor: str
    bands: Tuple[RadioBand, ...]
    max_capacity_gbps: float
    topology: str                     # ptp | ptmp | mesh | nodal
    duplex: str                       # FDD | TDD
    form_factor: str                  # all-outdoor | split-mount | indoor-nodal
    radio_carriers: int = 1
    max_modulation: str = ""
    channel_bandwidths_mhz: Tuple[int, ...] = ()
    features: Tuple[str, ...] = BASE_FEATURES
    aliases: Tuple[str, ...] = ()
    api_verified: bool = False
    is_family_fallback: bool = False
    notes: str = ""

    # ── Derived helpers ──────────────────────────────────────────────────────
    @property
    def protocol(self) -> str:
        return FLAVOR_TO_PROTOCOL[self.api_flavor]

    @property
    def primary_band(self) -> RadioBand:
        return self.bands[0]

    @property
    def default_frequency_mhz(self) -> float:
        b = self.primary_band
        if b is V_BAND:
            return 60480.0
        if b is E_BAND:
            return 73500.0
        if b is MW_LONG_HAUL:
            return 6000.0
        return 23000.0

    @property
    def role(self) -> str:
        if self.topology == "nodal":
            return "transport_nodal_aggregation"
        b = self.primary_band
        if b is V_BAND:
            return "transport_mmwave_vband"
        if b is E_BAND:
            return "transport_mmwave_eband"
        return "transport_microwave"

    def supports(self, feature: str) -> bool:
        return feature in self.features

    def to_capabilities(self) -> Dict[str, object]:
        """Capability dict published to TFS under /device/capabilities."""
        return {
            "vendor": "Ceragon Networks" if self.api_flavor == FLAVOR_CERAOS else "Ceragon (Siklu)",
            "model": self.model,
            "family": self.family,
            "product_line": self.product_line,
            "role": self.role,
            "api_flavor": self.api_flavor,
            "api_verified": self.api_verified,
            "catalog_match": "family_fallback" if self.is_family_fallback else "exact",
            "bands": [
                {"name": b.name, "freq_min_ghz": b.freq_min_ghz, "freq_max_ghz": b.freq_max_ghz}
                for b in self.bands
            ],
            "frequency_band_ghz": [self.primary_band.freq_min_ghz, self.primary_band.freq_max_ghz],
            "max_throughput_gbps": self.max_capacity_gbps,
            "radio_carriers": self.radio_carriers,
            "max_modulation": self.max_modulation,
            "channel_bandwidths_mhz": list(self.channel_bandwidths_mhz),
            "topology": self.topology,
            "duplex": self.duplex,
            "form_factor": self.form_factor,
            "beamforming": self.supports(F_BEAMFORMING),
            "xpic": self.supports(F_XPIC),
            "multiband": self.supports(F_MULTIBAND),
            "features": sorted(self.features),
            "spec_provenance": "lab-verified" if self.api_verified else "public-catalog (nominal, validate vs datasheet)",
        }

    def to_dict(self) -> Dict[str, object]:
        d = asdict(self)
        d["bands"] = [asdict(b) for b in self.bands]
        d["role"] = self.role
        d["protocol"] = self.protocol
        return d


def _f(*extra: str) -> Tuple[str, ...]:
    return tuple(dict.fromkeys(BASE_FEATURES + extra))


_MW_QAM = "4096QAM"
_MW_CH = (7, 14, 28, 40, 56, 80, 112)

# ── Explicit catalog ──────────────────────────────────────────────────────────
_CATALOG: List[ProductSpec] = [
    # ---------------- FibeAir IP-20 (CeraOS) ----------------
    ProductSpec("IP-20C", "IP-20", "FibeAir IP-20", FLAVOR_CERAOS, (MW_SHORT_HAUL,), 2.0, "ptp", "FDD",
                "all-outdoor", 2, _MW_QAM, _MW_CH,
                _f(F_PROTECTION, F_XPIC, F_MULTICARRIER, F_MULTIBAND, F_SYNC, F_SECURITY, F_ENERGY),
                aliases=("FIBEAIR IP-20C",)),
    ProductSpec("IP-20C-HP", "IP-20", "FibeAir IP-20", FLAVOR_CERAOS, (MW_SHORT_HAUL,), 2.0, "ptp", "FDD",
                "all-outdoor", 2, _MW_QAM, _MW_CH,
                _f(F_PROTECTION, F_XPIC, F_MULTICARRIER, F_MULTIBAND, F_SYNC, F_SECURITY, F_ENERGY),
                aliases=("IP-20CHP",), notes="High-power variant of IP-20C."),
    ProductSpec("IP-20S", "IP-20", "FibeAir IP-20", FLAVOR_CERAOS, (MW_SHORT_HAUL,), 1.0, "ptp", "FDD",
                "all-outdoor", 1, _MW_QAM, _MW_CH, _f(F_PROTECTION, F_SYNC, F_SECURITY, F_ENERGY)),
    ProductSpec("IP-20E", "IP-20", "FibeAir IP-20", FLAVOR_CERAOS, (E_BAND,), 2.5, "ptp", "FDD",
                "all-outdoor", 1, "256QAM", (250, 500, 750, 1000, 2000),
                _f(F_PROTECTION, F_MULTIBAND, F_SYNC, F_SECURITY)),
    ProductSpec("IP-20V", "IP-20", "FibeAir IP-20", FLAVOR_CERAOS, (V_BAND,), 1.0, "ptp", "TDD",
                "all-outdoor", 1, "256QAM", (50, 100, 250, 500), _f(F_SYNC, F_SECURITY)),
    ProductSpec("IP-20N", "IP-20", "FibeAir IP-20", FLAVOR_CERAOS, (MW_SHORT_HAUL,), 10.0, "nodal", "FDD",
                "split-mount", 4, _MW_QAM, _MW_CH,
                _f(F_PROTECTION, F_XPIC, F_MULTICARRIER, F_MULTIBAND, F_SYNC, F_SECURITY, F_ENERGY, F_ROUTING),
                notes="Modular nodal IDU; radio carriers depend on installed RMCs."),
    ProductSpec("IP-20A", "IP-20", "FibeAir IP-20", FLAVOR_CERAOS, (MW_SHORT_HAUL, MW_LONG_HAUL), 10.0, "nodal",
                "FDD", "split-mount", 4, _MW_QAM, _MW_CH,
                _f(F_PROTECTION, F_XPIC, F_MULTICARRIER, F_SYNC, F_SECURITY, F_ROUTING)),
    ProductSpec("IP-20A-LH", "IP-20", "FibeAir IP-20 Evolution LH", FLAVOR_CERAOS, (MW_LONG_HAUL,), 10.0, "ptp",
                "FDD", "split-mount", 8, "2048QAM", (28, 30, 40, 56, 60, 80),
                _f(F_PROTECTION, F_XPIC, F_MULTICARRIER, F_SYNC, F_SECURITY),
                aliases=("IP-20LH", "EVOLUTION LH", "EVOLUTION-LH", "IP-20 EVOLUTION"),
                notes="Long-haul trunk (space/frequency diversity)."),
    ProductSpec("IP-20G", "IP-20", "FibeAir IP-20", FLAVOR_CERAOS, (MW_SHORT_HAUL,), 2.0, "nodal", "FDD",
                "split-mount", 2, _MW_QAM, _MW_CH, _f(F_PROTECTION, F_XPIC, F_SYNC, F_SECURITY)),
    ProductSpec("IP-20GX", "IP-20", "FibeAir IP-20", FLAVOR_CERAOS, (MW_SHORT_HAUL,), 4.0, "nodal", "FDD",
                "split-mount", 2, _MW_QAM, _MW_CH, _f(F_PROTECTION, F_XPIC, F_MULTICARRIER, F_SYNC, F_SECURITY)),

    # ---------------- IP-50 (CeraOS, disaggregated) ----------------
    ProductSpec("IP-50C", "IP-50", "IP-50", FLAVOR_CERAOS, (MW_SHORT_HAUL,), 2.5, "ptp", "FDD",
                "all-outdoor", 2, _MW_QAM, (28, 56, 80, 112),
                _f(F_PROTECTION, F_XPIC, F_MULTICARRIER, F_MULTIBAND, F_SYNC, F_SECURITY, F_ENERGY)),
    ProductSpec("IP-50CX", "IP-50", "IP-50", FLAVOR_CERAOS, (MW_SHORT_HAUL,), 5.0, "ptp", "FDD",
                "all-outdoor", 2, _MW_QAM, (28, 56, 80, 112, 224),
                _f(F_PROTECTION, F_XPIC, F_MULTICARRIER, F_MULTIBAND, F_SYNC, F_SECURITY, F_ENERGY)),
    ProductSpec("IP-50E", "IP-50", "IP-50", FLAVOR_CERAOS, (E_BAND,), 10.0, "ptp", "FDD",
                "all-outdoor", 1, "512QAM", (250, 500, 750, 1000, 1500, 2000),
                _f(F_PROTECTION, F_MULTIBAND, F_SYNC, F_SECURITY, F_ENERGY)),
    ProductSpec("IP-50EX", "IP-50", "IP-50", FLAVOR_CERAOS, (E_BAND, MW_SHORT_HAUL), 20.0, "ptp", "FDD",
                "all-outdoor", 2, "512QAM", (250, 500, 1000, 2000),
                _f(F_PROTECTION, F_MULTICARRIER, F_MULTIBAND, F_SYNC, F_SECURITY, F_ENERGY),
                notes="E-band with integrated multiband (MW anchor) capability."),
    ProductSpec("IP-50EXA", "IP-50", "IP-50", FLAVOR_CERAOS, (E_BAND, MW_SHORT_HAUL), 20.0, "ptp", "FDD",
                "all-outdoor", 2, "512QAM", (250, 500, 1000, 2000),
                _f(F_PROTECTION, F_MULTICARRIER, F_MULTIBAND, F_SYNC, F_SECURITY, F_ENERGY)),
    ProductSpec("IP-50FX", "IP-50", "IP-50", FLAVOR_CERAOS, (MW_SHORT_HAUL,), 25.0, "nodal", "FDD",
                "indoor-nodal", 4, _MW_QAM, _MW_CH,
                _f(F_PROTECTION, F_XPIC, F_MULTICARRIER, F_MULTIBAND, F_SYNC, F_SECURITY, F_ENERGY, F_ROUTING),
                notes="Disaggregated cell-site gateway / nodal unit."),

    # ---------------- IP-100 (CeraOS, next-gen E-band) ----------------
    ProductSpec("IP-100E", "IP-100", "IP-100", FLAVOR_CERAOS, (E_BAND,), 25.0, "ptp", "FDD",
                "all-outdoor", 2, "1024QAM", (500, 1000, 2000),
                _f(F_PROTECTION, F_MULTICARRIER, F_MULTIBAND, F_SYNC, F_SECURITY, F_ENERGY),
                notes="Dual-carrier E-band; nominal capacity, validate vs datasheet."),

    # ---------------- EtherHaul (Siklu PtP) ----------------
    ProductSpec("EH-614TX", "EtherHaul", "EtherHaul", FLAVOR_SIKLU_EH, (V_BAND,), 1.0, "ptp", "TDD",
                "all-outdoor", 1, "64QAM", (250, 500), _f(F_SYNC, F_SECURITY)),
    ProductSpec("EH-710TX", "EtherHaul", "EtherHaul", FLAVOR_SIKLU_EH, (E_BAND,), 1.0, "ptp", "TDD",
                "all-outdoor", 1, "64QAM", (250, 500), _f(F_SYNC, F_SECURITY)),
    ProductSpec("EH-1200TX", "EtherHaul", "EtherHaul", FLAVOR_SIKLU_EH, (E_BAND,), 1.0, "ptp", "FDD",
                "all-outdoor", 1, "64QAM", (250, 500), _f(F_SYNC, F_SECURITY)),
    ProductSpec("EH-1200FX", "EtherHaul", "EtherHaul", FLAVOR_SIKLU_EH, (E_BAND,), 1.0, "ptp", "FDD",
                "all-outdoor", 1, "64QAM", (250, 500), _f(F_SYNC, F_SECURITY)),
    ProductSpec("EH-2500FX", "EtherHaul", "EtherHaul", FLAVOR_SIKLU_EH, (E_BAND,), 2.5, "ptp", "FDD",
                "all-outdoor", 1, "64QAM", (250, 500), _f(F_SYNC, F_SECURITY)),
    ProductSpec("EH-8010FX", "EtherHaul", "EtherHaul", FLAVOR_SIKLU_EH, (E_BAND,), 10.0, "ptp", "FDD",
                "all-outdoor", 1, "64QAM", (500, 1000, 2000), _f(F_SYNC, F_SECURITY),
                aliases=("EH-8010",)),
    ProductSpec("EH-8020FX", "EtherHaul", "EtherHaul", FLAVOR_SIKLU_EH, (E_BAND,), 20.0, "ptp", "FDD",
                "all-outdoor", 1, "64QAM", (1000, 2000), _f(F_SYNC, F_SECURITY),
                aliases=("EH-8020",)),

    # ---------------- MultiHaul TG (Siklu Terragraph, 60 GHz) ----------------
    ProductSpec("MH-T261", "MultiHaul TG", "MultiHaul TG", FLAVOR_SIKLU_TG, (V_BAND,), 1.0, "ptmp", "TDD",
                "all-outdoor", 1, "16QAM", (2160,), _f(F_BEAMFORMING, F_MESH, F_SYNC, F_SECURITY),
                aliases=("T261", "TG-T261"), api_verified=True,
                notes="Terminal unit; RESTCONF candidate DS verified in lab (192.168.1.225)."),
    ProductSpec("MH-T260", "MultiHaul TG", "MultiHaul TG", FLAVOR_SIKLU_TG, (V_BAND,), 1.0, "ptmp", "TDD",
                "all-outdoor", 1, "16QAM", (2160,), _f(F_BEAMFORMING, F_MESH, F_SYNC, F_SECURITY),
                aliases=("T260",)),
    ProductSpec("MH-T265", "MultiHaul TG", "MultiHaul TG", FLAVOR_SIKLU_TG, (V_BAND,), 1.8, "ptmp", "TDD",
                "all-outdoor", 1, "16QAM", (2160,), _f(F_BEAMFORMING, F_MESH, F_SYNC, F_SECURITY),
                aliases=("T265", "TG265")),
    ProductSpec("MH-T280", "MultiHaul TG", "MultiHaul TG", FLAVOR_SIKLU_TG, (V_BAND,), 1.8, "ptmp", "TDD",
                "all-outdoor", 1, "16QAM", (2160,), _f(F_BEAMFORMING, F_MESH, F_SYNC, F_SECURITY),
                aliases=("T280",)),
    ProductSpec("MH-N265", "MultiHaul TG", "MultiHaul TG", FLAVOR_SIKLU_TG, (V_BAND,), 1.8, "mesh", "TDD",
                "all-outdoor", 1, "16QAM", (2160,), _f(F_BEAMFORMING, F_MESH, F_SYNC, F_SECURITY),
                aliases=("N265",), notes="Distribution node, 90-degree sector."),
    ProductSpec("MH-N366", "MultiHaul TG", "MultiHaul TG", FLAVOR_SIKLU_TG, (V_BAND,), 7.2, "mesh", "TDD",
                "all-outdoor", 4, "16QAM", (2160,), _f(F_BEAMFORMING, F_MESH, F_SYNC, F_SECURITY),
                aliases=("N366",), notes="360-degree, 4-sector distribution node."),
    ProductSpec("MH-N367", "MultiHaul TG", "MultiHaul TG", FLAVOR_SIKLU_TG, (V_BAND,), 7.2, "mesh", "TDD",
                "all-outdoor", 4, "16QAM", (2160,), _f(F_BEAMFORMING, F_MESH, F_SYNC, F_SECURITY),
                aliases=("N367",)),
]

# ── Family fallbacks (used when the exact model is unknown) ───────────────────
_FAMILY_FALLBACKS: Dict[str, ProductSpec] = {
    "IP-20": replace(_CATALOG[0], model="IP-20", aliases=(), is_family_fallback=True,
                     notes="Family fallback: unlisted FibeAir IP-20 variant."),
    "IP-50": replace(next(s for s in _CATALOG if s.model == "IP-50C"), model="IP-50", aliases=(),
                     is_family_fallback=True, notes="Family fallback: unlisted IP-50 variant."),
    "IP-100": replace(next(s for s in _CATALOG if s.model == "IP-100E"), model="IP-100", aliases=(),
                      is_family_fallback=True, notes="Family fallback: unlisted IP-100 variant."),
    "EtherHaul": replace(next(s for s in _CATALOG if s.model == "EH-8010FX"), model="EtherHaul", aliases=(),
                         is_family_fallback=True, notes="Family fallback: unlisted EtherHaul variant."),
    "MultiHaul TG": replace(next(s for s in _CATALOG if s.model == "MH-T261"), model="MultiHaul-TG",
                            aliases=(), api_verified=False, is_family_fallback=True,
                            notes="Family fallback: unlisted MultiHaul TG node."),
}

_BY_MODEL: Dict[str, ProductSpec] = {}
for _s in _CATALOG:
    _BY_MODEL[_s.model] = _s
    for _a in _s.aliases:
        _BY_MODEL[_a] = _s


def normalize_model_string(raw: str) -> str:
    """Normalize vendor strings like 'FibeAir IP20C', 'Siklu EtherHaul-8010FX', 'ip_50cx'."""
    s = (raw or "").upper().strip()
    s = s.replace("_", "-")
    s = re.sub(r"\b(CERAGON|SIKLU|NETWORKS|FIBEAIR)\b", " ", s)
    s = re.sub(r"ETHERHAUL[\s-]*", "EH-", s)
    s = re.sub(r"MULTIHAUL[\s-]*TG[\s-]*", "MH-", s)
    s = re.sub(r"MULTIHAUL[\s-]*", "MH-", s)
    s = re.sub(r"\bIP\s*-?\s*(20|50|100)-?([A-Z]*)", lambda m: f"IP-{m.group(1)}{m.group(2)}", s)
    s = re.sub(r"\bEH\s*-?\s*(\d+)", r"EH-\1", s)
    s = re.sub(r"\bMH\s*-?\s*([A-Z])\s*-?\s*(\d+)", r"MH-\1\2", s)
    s = re.sub(r"\s+", " ", s).strip(" -")
    return s


_TOKEN_RE = re.compile(
    r"(IP-(?:20|50|100)[A-Z]*(?:-(?:HP|LH))?|EH-\d+[A-Z]*|MH-[A-Z]\d+[A-Z]*|MPL-\d+|TG\d+|\b[TN]\d{3}\b|EVOLUTION[ -]LH)"
)


def resolve_model(raw: Optional[str]) -> Optional[ProductSpec]:
    """
    Resolve any model/product/device-name string to a ProductSpec.
    Returns an exact catalog entry, a family fallback, or None if the string
    does not look like a Ceragon/Siklu product at all.
    """
    if not raw:
        return None
    norm = normalize_model_string(raw)
    if norm in _BY_MODEL:
        return _BY_MODEL[norm]

    # Multi-word aliases (e.g. "EVOLUTION LH") anywhere in the string
    for alias in sorted((k for k in _BY_MODEL if " " in k), key=len, reverse=True):
        if alias in norm:
            return _BY_MODEL[alias]

    tokens = [t.replace(" ", "-") for t in _TOKEN_RE.findall(norm)]
    # Exact token matches take precedence over prefix matches and family fallbacks
    for tok in tokens:
        if tok in _BY_MODEL:
            return _BY_MODEL[tok]

    for tok in tokens:
        # Try stripping a trailing suffix letter group (e.g. "EH-8010FXB" -> "EH-8010FX");
        # longest candidate first so "IP-50CXB" resolves to IP-50CX, not IP-50C.
        for cand in sorted(_BY_MODEL, key=len, reverse=True):
            if tok.startswith(cand) and len(tok) - len(cand) <= 2:
                return _BY_MODEL[cand]
        fam = family_of(tok)
        if fam:
            return _FAMILY_FALLBACKS[fam]

    fam = family_of(norm)
    return _FAMILY_FALLBACKS[fam] if fam else None


def family_of(norm: str) -> Optional[str]:
    if re.search(r"IP-100", norm):
        return "IP-100"
    if re.search(r"IP-50", norm):
        return "IP-50"
    if re.search(r"IP-20|EVOLUTION", norm):
        return "IP-20"
    if re.search(r"\bEH-\d", norm):
        return "EtherHaul"
    if re.search(r"\bMH-[TN]\d|\bMPL-\d|\bTG\d|\b[TN]\d{3}\b", norm):
        return "MultiHaul TG"
    return None


def is_ceragon_product(raw: Optional[str]) -> bool:
    return resolve_model(raw) is not None


def list_models(include_fallbacks: bool = False) -> List[ProductSpec]:
    out = list(_CATALOG)
    if include_fallbacks:
        out.extend(_FAMILY_FALLBACKS.values())
    return out


def list_families() -> List[str]:
    return list(_FAMILY_FALLBACKS.keys())


# Mapping cer_intent config_type -> portfolio feature that MUST be present in
# hardware. Config types not listed here are not hardware-gated.
CONFIG_TYPE_HARD_REQUIREMENTS: Dict[str, str] = {
    "beamforming": F_BEAMFORMING,
    "multiband": F_MULTIBAND,
    "interference": F_XPIC,
    "protection": F_PROTECTION,
}


def check_config_support(spec: Optional[ProductSpec], config_type: str) -> Tuple[bool, str]:
    """Return (supported, reason) for a config_type against a product spec."""
    if spec is None:
        return True, "unknown model: not gated"
    req = CONFIG_TYPE_HARD_REQUIREMENTS.get(config_type)
    if req and not spec.supports(req):
        return False, f"{spec.model} ({spec.product_line}) does not support '{req}' required by '{config_type}'"
    return True, "supported"
