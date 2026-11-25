"""
Radio hop arithmetic for the intent manager
===========================================
A fast analytic screen that runs before the digital twin is asked. It mirrors
the twin's radio model (contrib/ceragon in the NS-3 module):

  * ACM table      IEEE 802.11ad SC PHY rates and the link-adaptation SNR
                   thresholds the twin uses for the 60 GHz radios
  * payload        0.4 x the carrier rate, capped at the 1 GbE port, as the
                   twin's MAC model delivers
  * rain           ITU-R P.838-3 specific attenuation (k, alpha by frequency
                   and polarisation)
  * statistics     ITU-R P.530-18 section 2.4.1: distance factor r (at most
                   2.5), A0.01 = gamma(R0.01) d r, and
                   A_p / A0.01 = C1 p^-(C2 + C3 log10 p) for 0.001% <= p <= 1%,
                   C0 = 0.12 + 0.4 [log10(f/10)]^0.8 above 10 GHz,
                   C1 = 0.07^C0 0.12^(1-C0), C2 = 0.855 C0 + 0.546 (1-C0),
                   C3 = 0.139 C0 + 0.043 (1-C0)

Availability of a slice on a hop is the share of the year the hop holds the
modulation the slice needs: the MCS whose payload carries the total load on
the hop, or the slice's floor when that is higher. The twin's pre-flight stays
the authority on whether a slice fits; this screen answers instantly, ranks
alternatives, and gives availability, which a few seconds of simulation cannot.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# name, SNR threshold (dB), carrier rate (Mbps)
MCS_TABLE: List[Tuple[str, float, float]] = [
    ("MCS1", 1.0, 385.0), ("MCS2", 3.0, 770.0), ("MCS3", 4.5, 962.5), ("MCS4", 5.5, 1155.0),
    ("MCS5", 6.5, 1251.25), ("MCS6", 7.5, 1540.0), ("MCS7", 9.0, 1925.0), ("MCS8", 10.5, 2310.0),
    ("MCS9", 12.0, 2502.5), ("MCS10", 14.5, 3080.0), ("MCS11", 17.0, 3850.0), ("MCS12", 19.0, 4620.0),
]
PAYLOAD_SHARE = 0.4
PORT_MBPS = 1000.0
GAS_DB_PER_KM_60 = 15.0          # oxygen absorption near 60 GHz at sea level (ITU-R P.676)

# ITU-R P.838-3 coefficients: f (GHz), kH, alphaH, kV, alphaV (the twin's subset)
P838: List[Tuple[float, float, float, float, float]] = [
    (10, 0.01217, 1.2571, 0.01129, 1.2156), (20, 0.09164, 1.0568, 0.09611, 0.9847),
    (30, 0.2403, 0.9485, 0.2291, 0.9129), (40, 0.4431, 0.8673, 0.4274, 0.8421),
    (50, 0.6600, 0.8084, 0.6472, 0.7871), (55, 0.7630, 0.7853, 0.7525, 0.7650),
    (60, 0.8606, 0.7656, 0.8515, 0.7486), (70, 1.0315, 0.7345, 1.0253, 0.7215),
    (80, 1.1704, 0.7115, 1.1668, 0.7021), (90, 1.2807, 0.6944, 1.2795, 0.6876),
    (100, 1.3671, 0.6815, 1.3680, 0.6765),
]


def mcs_index(name: Any) -> Optional[int]:
    if name is None:
        return None
    s = str(name).upper().replace(" ", "")
    if s.startswith("MCS") and s[3:].isdigit():
        return int(s[3:])
    return None


def capacity_mbps(mcs: Any) -> float:
    i = mcs_index(mcs)
    if not i:
        return 0.0
    return min(PORT_MBPS, PAYLOAD_SHARE * MCS_TABLE[i - 1][2])


def threshold_db(mcs: Any) -> Optional[float]:
    i = mcs_index(mcs)
    return MCS_TABLE[i - 1][1] if i else None


def mcs_for_snr(snr_db: float) -> Optional[str]:
    best = None
    for name, thr, _ in MCS_TABLE:
        if snr_db >= thr:
            best = name
    return best


def mcs_for_load(load_mbps: float) -> Optional[str]:
    """The lowest MCS whose payload carries this load; None when no MCS does."""
    for name, _, _ in MCS_TABLE:
        if capacity_mbps(name) >= load_mbps - 1e-9:
            return name
    return None


def max_capacity_mbps() -> float:
    return max(capacity_mbps(n) for n, _, _ in MCS_TABLE)


# ── ITU-R rain ─────────────────────────────────────────────────────────────────

def p838(freq_ghz: float, vertical: bool = False) -> Tuple[float, float]:
    f = min(max(freq_ghz, P838[0][0]), P838[-1][0])
    for (f0, kh0, ah0, kv0, av0), (f1, kh1, ah1, kv1, av1) in zip(P838, P838[1:]):
        if f0 <= f <= f1:
            t = (math.log10(f) - math.log10(f0)) / (math.log10(f1) - math.log10(f0))
            k0, k1 = (kv0, kv1) if vertical else (kh0, kh1)
            a0, a1 = (av0, av1) if vertical else (ah0, ah1)
            k = 10 ** (math.log10(k0) + t * (math.log10(k1) - math.log10(k0)))
            return k, a0 + t * (a1 - a0)
    row = P838[-1]
    return (row[3], row[4]) if vertical else (row[1], row[2])


def specific_attenuation(freq_ghz: float, rain_mmh: float, vertical: bool = False) -> float:
    if rain_mmh <= 0:
        return 0.0
    k, a = p838(freq_ghz, vertical)
    return k * rain_mmh ** a


def distance_factor(d_km: float, freq_ghz: float, r001: float, alpha: float) -> float:
    """ITU-R P.530-18 eq. 32, at most 2.5."""
    if d_km <= 0 or r001 <= 0:
        return 1.0
    denom = (0.477 * d_km ** 0.633 * r001 ** (0.073 * alpha) * freq_ghz ** 0.123
             - 10.579 * (1 - math.exp(-0.024 * d_km)))
    return 2.5 if denom <= 0 else min(2.5, 1.0 / denom)


def a001(freq_ghz: float, d_km: float, r001: float, vertical: bool = False) -> float:
    _, alpha = p838(freq_ghz, vertical)
    return specific_attenuation(freq_ghz, r001, vertical) * d_km * distance_factor(d_km, freq_ghz, r001, alpha)


def _coeffs(freq_ghz: float) -> Tuple[float, float, float]:
    c0 = 0.12 if freq_ghz < 10 else 0.12 + 0.4 * math.log10(freq_ghz / 10.0) ** 0.8
    c1 = 0.07 ** c0 * 0.12 ** (1 - c0)
    c2 = 0.855 * c0 + 0.546 * (1 - c0)
    c3 = 0.139 * c0 + 0.043 * (1 - c0)
    return c1, c2, c3


def exceedance_ratio(p_pct: float, freq_ghz: float) -> float:
    c1, c2, c3 = _coeffs(freq_ghz)
    return c1 * p_pct ** -(c2 + c3 * math.log10(p_pct))


def unavailability_pct(margin_db: float, freq_ghz: float, d_km: float, r001: float,
                       vertical: bool = False) -> Tuple[float, str]:
    """Share of the year (%) rain attenuation exceeds this fade margin, and how the value was bounded."""
    if margin_db <= 0:
        return 100.0, "no margin in clear sky"
    a0 = a001(freq_ghz, d_km, r001, vertical)
    if a0 <= 0:
        return 0.0, "no rain on this hop"
    lo, hi = -3.0, 0.0                       # log10 p over the method's range 0.001 % .. 1 %
    if a0 * exceedance_ratio(10 ** lo, freq_ghz) <= margin_db:
        return 10 ** lo, "below 0.001 % (bounded)"
    if a0 * exceedance_ratio(10 ** hi, freq_ghz) >= margin_db:
        return 10 ** hi, "above 1 % (bounded)"
    for _ in range(60):                       # attenuation falls as p grows
        mid = (lo + hi) / 2
        if a0 * exceedance_ratio(10 ** mid, freq_ghz) > margin_db:
            lo = mid
        else:
            hi = mid
    return 10 ** ((lo + hi) / 2), "ITU-R P.530-18"


# ── a radio hop ────────────────────────────────────────────────────────────────

@dataclass
class Hop:
    a: str
    b: str
    distance_m: float = 250.0
    freq_ghz: float = 60.48
    vertical: bool = False
    clear_sky_snr_db: float = 15.85          # the twin's clear-sky SINR at the reference distance
    reference_m: float = 250.0
    r001_mmh: float = 42.0                   # rain rate exceeded 0.01 % of the year (ITU-R P.837)
    design_rain_mmh: float = 60.0            # the rain the twin stresses a slice with
    port_mbps: float = PORT_MBPS
    acm_margin_db: float = 1.0               # link adaptation holds about 1 dB above each threshold
                                             # (fading and hysteresis), as the twin's NS-3 runs show

    @property
    def name(self) -> str:
        return f"{self.a}|{self.b}"

    def snr_db(self, rain_mmh: float = 0.0) -> float:
        """Clear-sky SNR moved to this distance (spreading and oxygen), less rain on the whole hop (the twin's instantaneous cell)."""
        d0, d = self.reference_m / 1000.0, self.distance_m / 1000.0
        snr = self.clear_sky_snr_db - 20 * math.log10(max(d, 1e-3) / max(d0, 1e-3))
        if 55 <= self.freq_ghz <= 66:
            snr -= GAS_DB_PER_KM_60 * (d - d0)
        if rain_mmh > 0:
            _, alpha = p838(self.freq_ghz, self.vertical)
            r = min(1.0, distance_factor(d, self.freq_ghz, rain_mmh, alpha))
            snr -= specific_attenuation(self.freq_ghz, rain_mmh, self.vertical) * d * r
        return snr

    def mcs(self, rain_mmh: float = 0.0) -> Optional[str]:
        return mcs_for_snr(self.snr_db(rain_mmh) - self.acm_margin_db)

    def capacity(self, rain_mmh: float = 0.0) -> float:
        m = self.mcs(rain_mmh)
        return min(self.port_mbps, capacity_mbps(m)) if m else 0.0

    def availability(self, mcs: str) -> Dict[str, Any]:
        thr = threshold_db(mcs)
        clear = self.snr_db(0.0)
        margin = clear - ((thr + self.acm_margin_db) if thr is not None else clear)
        p, how = unavailability_pct(margin, self.freq_ghz, self.distance_m / 1000.0, self.r001_mmh, self.vertical)
        return {"hop": self.name, "mcs": mcs, "threshold_db": thr, "clear_sky_db": round(clear, 2),
                "margin_db": round(margin, 2), "unavailability_pct": p, "availability_pct": 100.0 - p,
                "minutes_per_year": round(p / 100.0 * 525960, 1), "bound": how,
                "method": "ITU-R P.838-3 + P.530-18", "r001_mmh": self.r001_mmh}

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def needed_mcs(load_mbps: float, floor: Optional[str] = None) -> Optional[str]:
    """The MCS the hop must hold for this load, or the floor when that is higher."""
    m = mcs_for_load(load_mbps)
    if m is None:
        return None
    if floor and (mcs_index(floor) or 0) > (mcs_index(m) or 0):
        return floor
    return m


def availability_for(hop: Hop, load_mbps: float, floor: Optional[str] = None) -> Dict[str, Any]:
    m = needed_mcs(load_mbps, floor)
    if m is None:
        return {"hop": hop.name, "mcs": None, "availability_pct": 0.0,
                "note": f"{load_mbps:g} Mbps is more than the hop carries at any modulation ({max_capacity_mbps():g} Mbps)"}
    out = hop.availability(m)
    out["load_mbps"] = load_mbps
    return out


def pct(p: float) -> str:
    """An availability with as many decimals as its nines need: 99.9783 -> '99.978 %'."""
    if p >= 100:
        return "100 %"
    if p <= 0:
        return "0 %"
    decimals = max(1, min(5, int(math.ceil(-math.log10(max(1e-9, 100.0 - p)))) + 1))
    return f"{p:.{decimals}f} %"


@dataclass
class HopScreen:
    """What the analytic screen says about a load on a hop."""
    hop: str
    load_mbps: float
    clear_mcs: Optional[str]
    clear_capacity_mbps: float
    rain_mmh: float
    rain_mcs: Optional[str]
    rain_capacity_mbps: float
    fits_clear: bool
    fits_rain: bool
    floor: Optional[str] = None
    floor_holds_in_rain: Optional[bool] = None
    availability: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def screen(hop: Hop, load_mbps: float, floor: Optional[str] = None, rain_mmh: Optional[float] = None) -> HopScreen:
    rain = hop.design_rain_mmh if rain_mmh is None else rain_mmh
    cm, rm = hop.mcs(0.0), hop.mcs(rain)
    cc, rc = hop.capacity(0.0), hop.capacity(rain)
    holds = None
    if floor:
        holds = rm is not None and (mcs_index(rm) or 0) >= (mcs_index(floor) or 0)
    return HopScreen(hop=hop.name, load_mbps=load_mbps, clear_mcs=cm, clear_capacity_mbps=cc, rain_mmh=rain,
                     rain_mcs=rm, rain_capacity_mbps=rc, fits_clear=load_mbps <= cc + 1e-9,
                     fits_rain=load_mbps <= rc + 1e-9, floor=floor, floor_holds_in_rain=holds,
                     availability=availability_for(hop, load_mbps, floor))
