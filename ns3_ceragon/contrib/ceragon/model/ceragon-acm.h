/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Adaptive Coding & Modulation (ACM) model for the Ceragon functional twin.
 *  - CeraOS / EtherHaul: BPSK .. 4096QAM profiles (hitless ACM, per-carrier)
 *  - MultiHaul TG: IEEE 802.11ad SC-PHY MCS1..MCS12 (Terragraph link adaptation)
 */
#ifndef CERAGON_ACM_H
#define CERAGON_ACM_H

#include <cstdint>
#include <string>
#include <vector>

namespace ns3
{

/**
 * @ingroup ceragon
 * One ACM profile (modulation + coding operating point).
 */
struct CeragonModulation
{
    std::string name;       //!< "QPSK", "4096QAM", "MCS9" ...
    double bitsPerSymbol;   //!< raw modulation order (log2 M)
    double requiredSnrDb;   //!< SNR needed for BER <= 1e-6 at this profile
    double phyRateMbps;     //!< absolute PHY rate (MCS table only, 2160 MHz channel)
};

/**
 * @ingroup ceragon
 * Modulation tables, rate computation and BER/PER model.
 */
class CeragonAcm
{
  public:
    /// QAM table used by CeraOS (IP-20/50/100) and EtherHaul
    static const std::vector<CeragonModulation>& GetQamTable();
    /// IEEE 802.11ad MCS table used by MultiHaul TG (Terragraph)
    static const std::vector<CeragonModulation>& GetMcsTable();
    /**
     * Look up a profile by name ("256QAM", "qam-4096", "MCS12" ...).
     * @param table the table
     * @param name profile name (case insensitive, "QAM-256" style accepted)
     * @return index or -1 if not found
     */
    static int FindIndex(const std::vector<CeragonModulation>& table, const std::string& name);
    /**
     * Net radio throughput of a single carrier.
     * @param m the modulation profile
     * @param channelBandwidthMhz the channel bandwidth
     * @param mcsTable true for the 802.11ad table
     * @return throughput in bit/s
     */
    static double CarrierRateBps(const CeragonModulation& m,
                                 double channelBandwidthMhz,
                                 bool mcsTable);
    /**
     * Bit error rate as a function of the SINR margin above the profile threshold.
     * BER = 1e-6 at 0 dB margin, waterfall slope of 1.5 decades/dB.
     * @param marginDb SINR minus required SNR (dB)
     * @return BER in [1e-13, 0.5]
     */
    static double BitErrorRate(double marginDb);
    /// Packet error rate for a frame of @p bytes at @p ber
    static double PacketErrorRate(double ber, uint32_t bytes);

    static constexpr double CODE_RATE = 0.90;   //!< average LDPC code rate
    static constexpr double ROLL_OFF = 0.15;    //!< RRC roll-off
    static constexpr double MAC_EFFICIENCY_TG = 0.80; //!< Terragraph MAC efficiency
};

/**
 * @ingroup ceragon
 * Per-carrier ACM state machine with hysteresis (hitless profile switching).
 */
class CeragonAcmController
{
  public:
    CeragonAcmController();
    /**
     * Configure the controller.
     * @param mcsTable use the 802.11ad table
     * @param minIndex lowest allowed profile (ACM floor)
     * @param maxIndex highest allowed profile (ACM ceiling)
     */
    void Configure(bool mcsTable, int minIndex, int maxIndex);
    /// Set ACM bounds (intent: "minimum ACM 256QAM")
    void SetRange(int minIndex, int maxIndex);
    /// Enable/disable adaptation (disabled => fixed at the ceiling profile)
    void SetAdaptive(bool adaptive);
    /// Upshift hysteresis (dB)
    void SetHysteresis(double upDb);
    /**
     * Run one ACM decision.
     * @param sinrDb current SINR
     * @return selected profile index, or -1 when the link is in outage
     */
    int Update(double sinrDb);
    int GetCurrentIndex() const;
    int GetMinIndex() const;
    int GetMaxIndex() const;
    bool IsAdaptive() const;
    bool IsMcsTable() const;
    const std::vector<CeragonModulation>& GetTable() const;
    /// Name of the current profile ("OUTAGE" if none)
    std::string GetCurrentName() const;

  private:
    bool m_mcs;
    int m_min;
    int m_max;
    int m_current;
    bool m_adaptive;
    double m_upHysteresisDb;
    bool m_inOutage; //!< link went below the floor; recovery needs hysteresis
};

} // namespace ns3

#endif /* CERAGON_ACM_H */
