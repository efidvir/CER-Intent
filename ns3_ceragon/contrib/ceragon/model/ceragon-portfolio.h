/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Ceragon / Siklu product portfolio catalog for the ns-3 functional twin.
 * Single source of truth mirrored from ceragon_tfs_adapter/portfolio.py so the
 * simulated devices expose exactly the same models, bands, capacities and
 * feature gating as the TeraFlowSDN RESTCONF adapter.
 */
#ifndef CERAGON_PORTFOLIO_H
#define CERAGON_PORTFOLIO_H

#include <cstdint>
#include <string>
#include <vector>

namespace ns3
{

/**
 * @ingroup ceragon
 * Southbound API flavor (identical to the TFS adapter).
 */
enum class CeragonApiFlavor : uint8_t
{
    SIKLU_TG, //!< MultiHaul TG (Terragraph, 60 GHz, RESTCONF candidate DS)
    SIKLU_EH, //!< EtherHaul PtP (E-band / V-band)
    CERAOS    //!< FibeAir IP-20 / IP-50 / IP-100 (CeraOS)
};

/**
 * @ingroup ceragon
 * Feature bit-mask (vocabulary aligned with cer_intent DeviceConfig.config_type).
 */
namespace CeragonFeature
{
constexpr uint32_t RADIO_TUNING = 1U << 0;
constexpr uint32_t ACM = 1U << 1;
constexpr uint32_t SLICE = 1U << 2;
constexpr uint32_t QOS = 1U << 3;
constexpr uint32_t PROTECTION = 1U << 4;
constexpr uint32_t XPIC = 1U << 5;
constexpr uint32_t MULTIBAND = 1U << 6;
constexpr uint32_t MULTICARRIER = 1U << 7;
constexpr uint32_t BEAMFORMING = 1U << 8;
constexpr uint32_t MESH = 1U << 9;
constexpr uint32_t SYNC = 1U << 10;
constexpr uint32_t SECURITY = 1U << 11;
constexpr uint32_t ENERGY = 1U << 12;
constexpr uint32_t TELEMETRY = 1U << 13;
constexpr uint32_t ROUTING = 1U << 14;

//! Baseline features every Ceragon radio supports
constexpr uint32_t BASE = RADIO_TUNING | ACM | SLICE | QOS | PROTECTION | TELEMETRY;
} // namespace CeragonFeature

/**
 * @ingroup ceragon
 * A radio frequency band.
 */
struct CeragonBand
{
    std::string name;   //!< "V-band", "E-band", "MW", "MW-LH"
    double minGhz;      //!< lower edge (GHz)
    double maxGhz;      //!< upper edge (GHz)

    bool Contains(double freqGhz) const
    {
        return freqGhz >= minGhz && freqGhz <= maxGhz;
    }
};

/**
 * @ingroup ceragon
 * Static description of one Ceragon / Siklu product.
 */
struct CeragonProductSpec
{
    std::string model;
    std::string family;
    std::string productLine;
    CeragonApiFlavor flavor;
    std::vector<CeragonBand> bands;
    double maxCapacityGbps;
    std::string topology;   //!< ptp | ptmp | mesh | nodal
    std::string duplex;     //!< FDD | TDD
    std::string formFactor; //!< all-outdoor | split-mount | indoor-nodal
    uint32_t radioCarriers;
    std::string maxModulation;
    std::vector<uint32_t> channelBandwidthsMhz;
    uint32_t features;
    std::vector<std::string> aliases;
    bool apiVerified{false};
    bool isFamilyFallback{false};
    std::string notes;

    bool Supports(uint32_t feature) const
    {
        return (features & feature) == feature;
    }

    const CeragonBand& PrimaryBand() const
    {
        return bands.front();
    }

    bool IsTdd() const
    {
        return duplex == "TDD";
    }

    /// Default centre frequency (MHz) used when a link does not specify one.
    double DefaultFrequencyMhz() const;
    /// Largest supported channel bandwidth (MHz).
    double MaxChannelBandwidthMhz() const;
    /// Role string published to TFS (/device/capabilities)
    std::string Role() const;
    /// Flavor as string ("siklu_tg", "siklu_eh", "ceraos")
    std::string FlavorString() const;
    /// Comma separated list of features.
    std::string FeatureString() const;
};

/**
 * @ingroup ceragon
 * Catalog accessor & model-string resolution (vendor-string normalisation,
 * alias lookup, longest-prefix match and family fallback).
 */
class CeragonPortfolio
{
  public:
    /// @return every explicit catalog entry
    static const std::vector<CeragonProductSpec>& GetCatalog();
    /// @return the family fallback specs (IP-20, IP-50, IP-100, EtherHaul, MultiHaul TG)
    static const std::vector<CeragonProductSpec>& GetFamilyFallbacks();
    /// Normalise a vendor model string ("FibeAir IP20C" -> "IP-20C")
    static std::string Normalize(const std::string& raw);
    /**
     * Resolve any vendor model string to a product spec.
     * @param raw the model string
     * @return pointer to the spec, or nullptr for non-Ceragon nodes
     */
    static const CeragonProductSpec* Resolve(const std::string& raw);
    /// @return list of family names
    static std::vector<std::string> ListFamilies();
    /**
     * Capability gating for a control domain (slice, radio, acm, qos, tsn,
     * beamforming, multiband, protection, sync, security, oran_xhaul, energy, xpic).
     * @param spec the product (nullptr => permissive)
     * @param domain the control domain
     * @param reason filled with the rejection reason
     * @return true if the domain is supported
     */
    static bool CheckConfigSupport(const CeragonProductSpec* spec,
                                   const std::string& domain,
                                   std::string& reason);
};

} // namespace ns3

#endif /* CERAGON_PORTFOLIO_H */
