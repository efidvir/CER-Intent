/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#include "ceragon-portfolio.h"

#include <algorithm>
#include <cctype>
#include <map>
#include <sstream>

namespace ns3
{

namespace
{

const CeragonBand V_BAND{"V-band", 57.0, 71.0};
const CeragonBand E_BAND{"E-band", 71.0, 86.0};
const CeragonBand MW_SHORT_HAUL{"MW", 6.0, 42.0};
const CeragonBand MW_LONG_HAUL{"MW-LH", 4.0, 13.0};

using namespace CeragonFeature;

const std::vector<uint32_t> MW_CH{7, 14, 28, 40, 56, 80, 112};
const std::string MW_QAM = "4096QAM";

CeragonProductSpec
Spec(const std::string& model,
     const std::string& family,
     const std::string& line,
     CeragonApiFlavor flavor,
     std::vector<CeragonBand> bands,
     double capGbps,
     const std::string& topology,
     const std::string& duplex,
     const std::string& form,
     uint32_t carriers,
     const std::string& maxMod,
     std::vector<uint32_t> channels,
     uint32_t extraFeatures,
     std::vector<std::string> aliases = {},
     bool verified = false,
     const std::string& notes = "")
{
    CeragonProductSpec s;
    s.model = model;
    s.family = family;
    s.productLine = line;
    s.flavor = flavor;
    s.bands = std::move(bands);
    s.maxCapacityGbps = capGbps;
    s.topology = topology;
    s.duplex = duplex;
    s.formFactor = form;
    s.radioCarriers = carriers;
    s.maxModulation = maxMod;
    s.channelBandwidthsMhz = std::move(channels);
    s.features = BASE | extraFeatures;
    s.aliases = std::move(aliases);
    s.apiVerified = verified;
    s.isFamilyFallback = false;
    s.notes = notes;
    return s;
}

std::vector<CeragonProductSpec>
BuildCatalog()
{
    const auto CERAOS = CeragonApiFlavor::CERAOS;
    const auto EH = CeragonApiFlavor::SIKLU_EH;
    const auto TG = CeragonApiFlavor::SIKLU_TG;
    std::vector<CeragonProductSpec> c;

    // ---------------- FibeAir IP-20 (CeraOS) ----------------
    c.push_back(Spec("IP-20C", "IP-20", "FibeAir IP-20", CERAOS, {MW_SHORT_HAUL}, 2.0, "ptp", "FDD",
                     "all-outdoor", 2, MW_QAM, MW_CH,
                     XPIC | MULTICARRIER | MULTIBAND | SYNC | SECURITY | ENERGY,
                     {"FIBEAIR IP-20C"}));
    c.push_back(Spec("IP-20C-HP", "IP-20", "FibeAir IP-20", CERAOS, {MW_SHORT_HAUL}, 2.0, "ptp",
                     "FDD", "all-outdoor", 2, MW_QAM, MW_CH,
                     XPIC | MULTICARRIER | MULTIBAND | SYNC | SECURITY | ENERGY,
                     {"IP-20CHP"}, false, "High-power variant of IP-20C."));
    c.push_back(Spec("IP-20S", "IP-20", "FibeAir IP-20", CERAOS, {MW_SHORT_HAUL}, 1.0, "ptp", "FDD",
                     "all-outdoor", 1, MW_QAM, MW_CH, SYNC | SECURITY | ENERGY));
    c.push_back(Spec("IP-20E", "IP-20", "FibeAir IP-20", CERAOS, {E_BAND}, 2.5, "ptp", "FDD",
                     "all-outdoor", 1, "256QAM", {250, 500, 750, 1000, 2000},
                     MULTIBAND | SYNC | SECURITY));
    c.push_back(Spec("IP-20V", "IP-20", "FibeAir IP-20", CERAOS, {V_BAND}, 1.0, "ptp", "TDD",
                     "all-outdoor", 1, "256QAM", {50, 100, 250, 500}, SYNC | SECURITY));
    c.push_back(Spec("IP-20N", "IP-20", "FibeAir IP-20", CERAOS, {MW_SHORT_HAUL}, 10.0, "nodal",
                     "FDD", "split-mount", 4, MW_QAM, MW_CH,
                     XPIC | MULTICARRIER | MULTIBAND | SYNC | SECURITY | ENERGY | ROUTING, {},
                     false, "Modular nodal IDU; radio carriers depend on installed RMCs."));
    c.push_back(Spec("IP-20A", "IP-20", "FibeAir IP-20", CERAOS, {MW_SHORT_HAUL, MW_LONG_HAUL}, 10.0,
                     "nodal", "FDD", "split-mount", 4, MW_QAM, MW_CH,
                     XPIC | MULTICARRIER | SYNC | SECURITY | ROUTING));
    c.push_back(Spec("IP-20A-LH", "IP-20", "FibeAir IP-20 Evolution LH", CERAOS, {MW_LONG_HAUL},
                     10.0, "ptp", "FDD", "split-mount", 8, "2048QAM", {28, 30, 40, 56, 60, 80},
                     XPIC | MULTICARRIER | SYNC | SECURITY,
                     {"IP-20LH", "EVOLUTION LH", "EVOLUTION-LH", "IP-20 EVOLUTION"}, false,
                     "Long-haul trunk (space/frequency diversity)."));
    c.push_back(Spec("IP-20G", "IP-20", "FibeAir IP-20", CERAOS, {MW_SHORT_HAUL}, 2.0, "nodal", "FDD",
                     "split-mount", 2, MW_QAM, MW_CH, XPIC | SYNC | SECURITY));
    c.push_back(Spec("IP-20GX", "IP-20", "FibeAir IP-20", CERAOS, {MW_SHORT_HAUL}, 4.0, "nodal",
                     "FDD", "split-mount", 2, MW_QAM, MW_CH, XPIC | MULTICARRIER | SYNC | SECURITY));

    // ---------------- IP-50 (CeraOS, disaggregated) ----------------
    c.push_back(Spec("IP-50C", "IP-50", "IP-50", CERAOS, {MW_SHORT_HAUL}, 2.5, "ptp", "FDD",
                     "all-outdoor", 2, MW_QAM, {28, 56, 80, 112},
                     XPIC | MULTICARRIER | MULTIBAND | SYNC | SECURITY | ENERGY));
    c.push_back(Spec("IP-50CX", "IP-50", "IP-50", CERAOS, {MW_SHORT_HAUL}, 5.0, "ptp", "FDD",
                     "all-outdoor", 2, MW_QAM, {28, 56, 80, 112, 224},
                     XPIC | MULTICARRIER | MULTIBAND | SYNC | SECURITY | ENERGY));
    c.push_back(Spec("IP-50E", "IP-50", "IP-50", CERAOS, {E_BAND}, 10.0, "ptp", "FDD", "all-outdoor",
                     1, "512QAM", {250, 500, 750, 1000, 1500, 2000},
                     MULTIBAND | SYNC | SECURITY | ENERGY));
    c.push_back(Spec("IP-50EX", "IP-50", "IP-50", CERAOS, {E_BAND, MW_SHORT_HAUL}, 20.0, "ptp", "FDD",
                     "all-outdoor", 2, "512QAM", {250, 500, 1000, 2000},
                     MULTICARRIER | MULTIBAND | SYNC | SECURITY | ENERGY, {}, false,
                     "E-band with integrated multiband (MW anchor) capability."));
    c.push_back(Spec("IP-50EXA", "IP-50", "IP-50", CERAOS, {E_BAND, MW_SHORT_HAUL}, 20.0, "ptp",
                     "FDD", "all-outdoor", 2, "512QAM", {250, 500, 1000, 2000},
                     MULTICARRIER | MULTIBAND | SYNC | SECURITY | ENERGY));
    c.push_back(Spec("IP-50FX", "IP-50", "IP-50", CERAOS, {MW_SHORT_HAUL}, 25.0, "nodal", "FDD",
                     "indoor-nodal", 4, MW_QAM, MW_CH,
                     XPIC | MULTICARRIER | MULTIBAND | SYNC | SECURITY | ENERGY | ROUTING, {},
                     false, "Disaggregated cell-site gateway / nodal unit."));

    // ---------------- IP-100 (CeraOS, next-gen E-band) ----------------
    c.push_back(Spec("IP-100E", "IP-100", "IP-100", CERAOS, {E_BAND}, 25.0, "ptp", "FDD",
                     "all-outdoor", 2, "1024QAM", {500, 1000, 2000},
                     MULTICARRIER | MULTIBAND | SYNC | SECURITY | ENERGY, {}, false,
                     "Dual-carrier E-band; nominal capacity, validate vs datasheet."));

    // ---------------- EtherHaul (Siklu PtP) ----------------
    c.push_back(Spec("EH-614TX", "EtherHaul", "EtherHaul", EH, {V_BAND}, 1.0, "ptp", "TDD",
                     "all-outdoor", 1, "64QAM", {250, 500}, SYNC | SECURITY));
    c.push_back(Spec("EH-710TX", "EtherHaul", "EtherHaul", EH, {E_BAND}, 1.0, "ptp", "TDD",
                     "all-outdoor", 1, "64QAM", {250, 500}, SYNC | SECURITY));
    c.push_back(Spec("EH-1200TX", "EtherHaul", "EtherHaul", EH, {E_BAND}, 1.0, "ptp", "FDD",
                     "all-outdoor", 1, "64QAM", {250, 500}, SYNC | SECURITY));
    c.push_back(Spec("EH-1200FX", "EtherHaul", "EtherHaul", EH, {E_BAND}, 1.0, "ptp", "FDD",
                     "all-outdoor", 1, "64QAM", {250, 500}, SYNC | SECURITY));
    c.push_back(Spec("EH-2500FX", "EtherHaul", "EtherHaul", EH, {E_BAND}, 2.5, "ptp", "FDD",
                     "all-outdoor", 1, "64QAM", {250, 500}, SYNC | SECURITY));
    c.push_back(Spec("EH-8010FX", "EtherHaul", "EtherHaul", EH, {E_BAND}, 10.0, "ptp", "FDD",
                     "all-outdoor", 1, "64QAM", {500, 1000, 2000}, SYNC | SECURITY, {"EH-8010"}));
    c.push_back(Spec("EH-8020FX", "EtherHaul", "EtherHaul", EH, {E_BAND}, 20.0, "ptp", "FDD",
                     "all-outdoor", 1, "64QAM", {1000, 2000}, SYNC | SECURITY, {"EH-8020"}));

    // ---------------- MultiHaul TG (Siklu Terragraph, 60 GHz) ----------------
    const uint32_t tg = BEAMFORMING | MESH | SYNC | SECURITY;
    c.push_back(Spec("MH-T261", "MultiHaul TG", "MultiHaul TG", TG, {V_BAND}, 1.0, "ptmp", "TDD",
                     "all-outdoor", 1, "16QAM", {2160}, tg, {"T261", "TG-T261"}, true,
                     "Terminal unit; RESTCONF candidate DS verified in lab (192.168.1.225)."));
    c.push_back(Spec("MH-T260", "MultiHaul TG", "MultiHaul TG", TG, {V_BAND}, 1.0, "ptmp", "TDD",
                     "all-outdoor", 1, "16QAM", {2160}, tg, {"T260"}));
    c.push_back(Spec("MH-T265", "MultiHaul TG", "MultiHaul TG", TG, {V_BAND}, 1.8, "ptmp", "TDD",
                     "all-outdoor", 1, "16QAM", {2160}, tg, {"T265", "TG265"}));
    c.push_back(Spec("MH-T280", "MultiHaul TG", "MultiHaul TG", TG, {V_BAND}, 1.8, "ptmp", "TDD",
                     "all-outdoor", 1, "16QAM", {2160}, tg, {"T280"}));
    c.push_back(Spec("MH-N265", "MultiHaul TG", "MultiHaul TG", TG, {V_BAND}, 1.8, "mesh", "TDD",
                     "all-outdoor", 1, "16QAM", {2160}, tg, {"N265"}, false,
                     "Distribution node, 90-degree sector."));
    c.push_back(Spec("MH-N366", "MultiHaul TG", "MultiHaul TG", TG, {V_BAND}, 7.2, "mesh", "TDD",
                     "all-outdoor", 4, "16QAM", {2160}, tg, {"N366"}, false,
                     "360-degree, 4-sector distribution node."));
    c.push_back(Spec("MH-N367", "MultiHaul TG", "MultiHaul TG", TG, {V_BAND}, 7.2, "mesh", "TDD",
                     "all-outdoor", 4, "16QAM", {2160}, tg, {"N367"}));
    return c;
}

std::vector<CeragonProductSpec>
BuildFallbacks(const std::vector<CeragonProductSpec>& cat)
{
    auto find = [&cat](const std::string& m) {
        return *std::find_if(cat.begin(), cat.end(), [&m](const CeragonProductSpec& s) {
            return s.model == m;
        });
    };
    std::vector<std::pair<std::string, std::string>> fb{{"IP-20", "IP-20C"},
                                                        {"IP-50", "IP-50C"},
                                                        {"IP-100", "IP-100E"},
                                                        {"EtherHaul", "EH-8010FX"},
                                                        {"MultiHaul TG", "MH-T261"}};
    std::vector<CeragonProductSpec> out;
    for (const auto& [family, base] : fb)
    {
        CeragonProductSpec s = find(base);
        s.model = (family == "MultiHaul TG") ? "MultiHaul-TG" : family;
        s.aliases.clear();
        s.apiVerified = false;
        s.isFamilyFallback = true;
        s.notes = "Family fallback: unlisted " + family + " variant.";
        out.push_back(s);
    }
    return out;
}

std::string
ReplaceAll(std::string s, const std::string& from, const std::string& to)
{
    size_t pos = 0;
    while ((pos = s.find(from, pos)) != std::string::npos)
    {
        s.replace(pos, from.size(), to);
        pos += to.size();
    }
    return s;
}

bool
StartsWith(const std::string& s, const std::string& p)
{
    return s.size() >= p.size() && s.compare(0, p.size(), p) == 0;
}

} // namespace

double
CeragonProductSpec::DefaultFrequencyMhz() const
{
    const auto& b = PrimaryBand();
    if (b.name == "V-band")
    {
        return 60480.0;
    }
    if (b.name == "E-band")
    {
        return 73500.0;
    }
    if (b.name == "MW-LH")
    {
        return 6000.0;
    }
    return 23000.0;
}

double
CeragonProductSpec::MaxChannelBandwidthMhz() const
{
    if (channelBandwidthsMhz.empty())
    {
        return 0.0;
    }
    return *std::max_element(channelBandwidthsMhz.begin(), channelBandwidthsMhz.end());
}

std::string
CeragonProductSpec::Role() const
{
    if (topology == "nodal")
    {
        return "transport_nodal_aggregation";
    }
    const auto& b = PrimaryBand();
    if (b.name == "V-band")
    {
        return "transport_mmwave_vband";
    }
    if (b.name == "E-band")
    {
        return "transport_mmwave_eband";
    }
    return "transport_microwave";
}

std::string
CeragonProductSpec::FlavorString() const
{
    switch (flavor)
    {
    case CeragonApiFlavor::SIKLU_TG:
        return "siklu_tg";
    case CeragonApiFlavor::SIKLU_EH:
        return "siklu_eh";
    default:
        return "ceraos";
    }
}

std::string
CeragonProductSpec::FeatureString() const
{
    static const std::vector<std::pair<uint32_t, std::string>> names{
        {RADIO_TUNING, "radio_tuning"},
        {ACM, "acm"},
        {SLICE, "slice"},
        {QOS, "qos"},
        {PROTECTION, "protection"},
        {XPIC, "xpic"},
        {MULTIBAND, "multiband"},
        {MULTICARRIER, "multicarrier"},
        {BEAMFORMING, "beamforming"},
        {MESH, "mesh"},
        {SYNC, "sync"},
        {SECURITY, "security"},
        {ENERGY, "energy"},
        {TELEMETRY, "telemetry"},
        {ROUTING, "routing"}};
    std::ostringstream os;
    bool first = true;
    for (const auto& [bit, name] : names)
    {
        if (features & bit)
        {
            os << (first ? "" : ",") << name;
            first = false;
        }
    }
    return os.str();
}

const std::vector<CeragonProductSpec>&
CeragonPortfolio::GetCatalog()
{
    static const std::vector<CeragonProductSpec> catalog = BuildCatalog();
    return catalog;
}

const std::vector<CeragonProductSpec>&
CeragonPortfolio::GetFamilyFallbacks()
{
    static const std::vector<CeragonProductSpec> fallbacks = BuildFallbacks(GetCatalog());
    return fallbacks;
}

std::string
CeragonPortfolio::Normalize(const std::string& raw)
{
    std::string s;
    s.reserve(raw.size());
    for (char ch : raw)
    {
        char u = static_cast<char>(std::toupper(static_cast<unsigned char>(ch)));
        s.push_back((u == '_' || u == ' ') ? '-' : u);
    }
    while (s.find("--") != std::string::npos)
    {
        s = ReplaceAll(s, "--", "-");
    }
    for (const char* prefix : {"CERAGON-", "SIKLU-", "FIBEAIR-"})
    {
        if (StartsWith(s, prefix))
        {
            s = s.substr(std::char_traits<char>::length(prefix));
        }
    }
    if (StartsWith(s, "MULTIHAUL-TG-"))
    {
        s = "MH-" + s.substr(13);
    }
    else if (StartsWith(s, "MULTIHAUL-"))
    {
        s = "MH-" + s.substr(10);
    }
    else if (StartsWith(s, "ETHERHAUL-"))
    {
        s = "EH-" + s.substr(10);
    }
    // IP20C -> IP-20C, EH8010 -> EH-8010, MHT261 -> MH-T261
    if (s.size() > 2 && StartsWith(s, "IP") && std::isdigit(static_cast<unsigned char>(s[2])))
    {
        s.insert(2, "-");
    }
    if (s.size() > 2 && StartsWith(s, "EH") && std::isdigit(static_cast<unsigned char>(s[2])))
    {
        s.insert(2, "-");
    }
    return s;
}

const CeragonProductSpec*
CeragonPortfolio::Resolve(const std::string& raw)
{
    if (raw.empty())
    {
        return nullptr;
    }
    const std::string s = Normalize(raw);
    const auto& cat = GetCatalog();

    // 1. Exact model or alias match
    for (const auto& spec : cat)
    {
        if (s == spec.model)
        {
            return &spec;
        }
        for (const auto& a : spec.aliases)
        {
            if (s == Normalize(a))
            {
                return &spec;
            }
        }
    }
    // 2. Longest-prefix match over models and aliases
    const CeragonProductSpec* best = nullptr;
    size_t bestLen = 0;
    for (const auto& spec : cat)
    {
        std::vector<std::string> keys{spec.model};
        for (const auto& a : spec.aliases)
        {
            keys.push_back(Normalize(a));
        }
        for (const auto& k : keys)
        {
            if (k.size() > bestLen && StartsWith(s, k))
            {
                best = &spec;
                bestLen = k.size();
            }
        }
    }
    if (best)
    {
        return best;
    }
    // 3. Family fallbacks
    const auto& fb = GetFamilyFallbacks();
    if (StartsWith(s, "IP-100"))
    {
        return &fb[2];
    }
    if (StartsWith(s, "IP-20"))
    {
        return &fb[0];
    }
    if (StartsWith(s, "IP-50"))
    {
        return &fb[1];
    }
    if (StartsWith(s, "EH-"))
    {
        return &fb[3];
    }
    if (StartsWith(s, "MH-"))
    {
        return &fb[4];
    }
    return nullptr;
}

std::vector<std::string>
CeragonPortfolio::ListFamilies()
{
    return {"IP-20", "IP-50", "IP-100", "EtherHaul", "MultiHaul TG"};
}

bool
CeragonPortfolio::CheckConfigSupport(const CeragonProductSpec* spec,
                                     const std::string& domain,
                                     std::string& reason)
{
    reason.clear();
    if (!spec)
    {
        return true;
    }
    static const std::map<std::string, uint32_t> required{
        {"slice", SLICE},
        {"vlan", SLICE},
        {"radio", RADIO_TUNING},
        {"operating_parameters", RADIO_TUNING},
        {"acm", ACM},
        {"qos", QOS},
        {"tsn", QOS},
        {"beamforming", BEAMFORMING},
        {"multiband", MULTIBAND},
        {"multicarrier", MULTICARRIER},
        {"protection", PROTECTION},
        {"xpic", XPIC},
        {"sync", SYNC},
        {"security", SECURITY},
        {"energy", ENERGY},
        {"oran_xhaul", QOS | SYNC},
        {"mesh", MESH},
        {"routing", ROUTING}};
    if (domain == "interference")
    {
        if (spec->Supports(XPIC) || spec->Supports(BEAMFORMING))
        {
            return true;
        }
        reason = spec->model + " has no interference mitigation (XPIC/beamforming)";
        return false;
    }
    auto it = required.find(domain);
    if (it == required.end())
    {
        return true;
    }
    if (spec->Supports(it->second))
    {
        return true;
    }
    reason = spec->model + " does not support '" + domain + "'";
    return false;
}

} // namespace ns3
