/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#include "ceragon-oran-xhaul.h"

#include <map>

namespace ns3
{

uint32_t
CeragonOranXhaul::NumPrb(uint32_t bandwidthMhz, uint32_t numerology)
{
    static const std::map<uint32_t, uint32_t> mu0{{5, 25},   {10, 52},  {15, 79},  {20, 106},
                                                  {25, 133}, {30, 160}, {40, 216}, {50, 270}};
    static const std::map<uint32_t, uint32_t> mu1{{5, 11},   {10, 24},  {15, 38},  {20, 51},
                                                  {25, 65},  {30, 78},  {40, 106}, {50, 133},
                                                  {60, 162}, {80, 217}, {90, 245}, {100, 273}};
    static const std::map<uint32_t, uint32_t> mu2{{10, 11},  {15, 18},  {20, 24},  {25, 31},
                                                  {30, 38},  {40, 51},  {50, 65},  {60, 79},
                                                  {80, 107}, {90, 121}, {100, 135}};
    const auto& t = (numerology == 0) ? mu0 : (numerology == 1 ? mu1 : mu2);
    auto it = t.lower_bound(bandwidthMhz);
    if (it == t.end())
    {
        return t.rbegin()->second;
    }
    return it->second;
}

double
CeragonOranXhaul::BitsPerComponent(const std::string& compression)
{
    // Block floating point: N-bit mantissa per component + 4-bit exponent per PRB
    // (12 subcarriers x 2 components) -> +4/24 bit per component.
    if (compression == "bfp-9bit")
    {
        return 9.0 + 4.0 / 24.0;
    }
    if (compression == "bfp-8bit" || compression == "mu-law-8bit")
    {
        return 8.0 + 4.0 / 24.0;
    }
    if (compression == "bfp-14bit")
    {
        return 14.0 + 4.0 / 24.0;
    }
    return 16.0; // uncompressed
}

double
CeragonOranXhaul::EcpriBitRate(uint32_t bandwidthMhz,
                               uint32_t numerology,
                               uint32_t layers,
                               const std::string& compression)
{
    const double prb = NumPrb(bandwidthMhz, numerology);
    const double symbolsPerSecond = 14.0 * 1000.0 * (1U << numerology);
    const double iqBits = prb * 12.0 * 2.0 * BitsPerComponent(compression);
    const double transportOverhead = 1.06; // eCPRI + Ethernet/VLAN headers
    return layers * iqBits * symbolsPerSecond * transportOverhead;
}

double
CeragonOranXhaul::DelayBudgetUs(const std::string& transportClass)
{
    if (transportClass == "high-25us")
    {
        return 25.0;
    }
    if (transportClass == "medium-275us")
    {
        return 275.0;
    }
    if (transportClass == "low-500us")
    {
        return 500.0;
    }
    return 100.0; // "high-100us" (default for Split 7.2x)
}

} // namespace ns3
