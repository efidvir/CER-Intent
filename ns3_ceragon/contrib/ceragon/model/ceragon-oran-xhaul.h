/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * O-RAN xHaul (Split 7.2x eCPRI) dimensioning helpers for the Ceragon twin.
 */
#ifndef CERAGON_ORAN_XHAUL_H
#define CERAGON_ORAN_XHAUL_H

#include <cstdint>
#include <string>

namespace ns3
{

/**
 * @ingroup ceragon
 * O-RAN fronthaul (Split 7.2x, eCPRI) traffic dimensioning.
 */
class CeragonOranXhaul
{
  public:
    /**
     * Number of PRBs for an NR carrier (TS 38.101-1 Table 5.3.2-1, FR1 subset).
     * @param bandwidthMhz carrier bandwidth (5..100 MHz)
     * @param numerology mu (0: 15 kHz, 1: 30 kHz, 2: 60 kHz)
     * @return number of PRBs
     */
    static uint32_t NumPrb(uint32_t bandwidthMhz, uint32_t numerology);
    /**
     * Effective bits per IQ sample component after compression.
     * @param compression "none" (16 bit), "bfp-9bit", "bfp-8bit", "bfp-14bit", "mu-law-8bit"
     * @return bits per I (or Q) component incl. per-PRB exponent overhead
     */
    static double BitsPerComponent(const std::string& compression);
    /**
     * Split 7.2x U-plane bit rate (eCPRI + Ethernet overhead included).
     * @param bandwidthMhz NR carrier bandwidth
     * @param numerology mu
     * @param layers number of spatial layers / eAxC streams
     * @param compression IQ compression scheme
     * @return bit rate (bit/s)
     */
    static double EcpriBitRate(uint32_t bandwidthMhz,
                               uint32_t numerology,
                               uint32_t layers,
                               const std::string& compression);
    /// One-way transport delay budget class (O-RAN WG4 CUS): "high-25us" ... "low-500us"
    static double DelayBudgetUs(const std::string& transportClass);
};

} // namespace ns3

#endif /* CERAGON_ORAN_XHAUL_H */
