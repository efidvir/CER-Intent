/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Functional twin of a Ceragon / Siklu radio (FibeAir IP-20, IP-50, IP-100,
 * EtherHaul, MultiHaul TG).
 */
#ifndef CERAGON_RADIO_NET_DEVICE_H
#define CERAGON_RADIO_NET_DEVICE_H

#include "ceragon-acm.h"
#include "ceragon-portfolio.h"

#include "ns3/data-rate.h"
#include "ns3/event-id.h"
#include "ns3/mac48-address.h"
#include "ns3/net-device.h"
#include "ns3/nstime.h"
#include "ns3/queue.h"
#include "ns3/random-variable-stream.h"
#include "ns3/traced-callback.h"
#include "ns3/traced-value.h"

#include <string>
#include <vector>

namespace ns3
{

class CeragonRadioChannel;

/**
 * @ingroup ceragon
 * Radio protection schemes.
 */
enum class CeragonProtectionMode : uint8_t
{
    NONE,            //!< unprotected (1+0)
    HSB_1PLUS1,      //!< 1+1 Hot-Standby (equipment protection, ~50 ms switchover)
    SPACE_DIVERSITY, //!< 1+1 Space Diversity (two antennas, hitless, diversity gain)
    ACTIVE_BACKUP    //!< MultiHaul TG active-backup bond (radio-bridge-tg-bond)
};

/**
 * @ingroup ceragon
 * Synchronization (timing) modes.
 */
enum class CeragonSyncMode : uint8_t
{
    NONE,                  //!< no timing transport
    PTP_BOUNDARY_CLOCK,    //!< IEEE 1588v2 boundary clock (G.8275.1)
    PTP_TRANSPARENT_CLOCK, //!< IEEE 1588v2 transparent clock
    SYNCE_PTP              //!< SyncE (G.8262) assisted PTP BC
};

/**
 * @ingroup ceragon
 * State of one radio carrier (channel) of a Ceragon radio.
 */
struct CeragonCarrier
{
    double frequencyMhz{23000.0};
    double bandwidthMhz{56.0};
    bool verticalPol{false};
    CeragonAcmController acm;
    double txPowerDbm{20.0};
    bool enabled{true};
    bool sleeping{false};
    bool up{false};
    double rslDbm{-200.0};
    double sinrDb{-100.0};
    double rateBps{0.0};
    double rainAttDb{0.0};
    double xpdDb{40.0};
};

/**
 * @ingroup ceragon
 * Functional twin of a Ceragon radio terminal.
 *
 * Each device represents one end of a radio hop and owns:
 *  - N carriers (multi-carrier ABC, XPIC H/V pairs or Multi-Band E-band + MW)
 *  - per-carrier hitless ACM (QAM table or 802.11ad MCS table)
 *  - ATPC / Green-ATPC transmit power control
 *  - L1 carrier bonding (aggregate capacity = sum of carriers, capped by product)
 *  - 1+1 HSB / Space-Diversity / active-backup radio protection
 *  - 60 GHz beamforming (MultiHaul TG): misalignment, beam tracking, topology scan
 *  - MACsec overhead, header de-duplication
 *  - energy model (base + per-carrier + PA power) with low-load carrier sleep
 *  - PTP / SyncE time-error model with holdover
 */
class CeragonRadioNetDevice : public NetDevice
{
  public:
    static TypeId GetTypeId();
    CeragonRadioNetDevice();
    ~CeragonRadioNetDevice() override;

    // ---- wiring ---------------------------------------------------------
    bool Attach(Ptr<CeragonRadioChannel> channel);
    void SetQueue(Ptr<Queue<Packet>> queue);
    Ptr<Queue<Packet>> GetQueue() const;
    /// Called by the channel when a frame has been received
    void Receive(Ptr<Packet> packet, bool corrupted);

    // ---- product -------------------------------------------------------
    void SetProductModel(std::string model);
    std::string GetProductModel() const;
    const CeragonProductSpec* GetSpec() const;

    // ---- carriers / radio tuning (domain: radio, acm, multiband, xpic) --
    /**
     * Add a radio carrier.
     * @param frequencyMhz centre frequency
     * @param bandwidthMhz channel bandwidth
     * @param verticalPol polarization (XPIC pairs use H + V on the same channel)
     * @param maxModulation ACM ceiling ("4096QAM", "MCS12")
     * @param minModulation ACM floor ("QPSK", "MCS1")
     * @return carrier index
     */
    uint32_t AddCarrier(double frequencyMhz,
                        double bandwidthMhz,
                        bool verticalPol,
                        const std::string& maxModulation,
                        const std::string& minModulation);
    void ClearCarriers();
    uint32_t GetNCarriers() const;
    const CeragonCarrier& GetCarrier(uint32_t i) const;
    void SetCarrierFrequency(uint32_t i, double frequencyMhz);
    void SetCarrierBandwidth(uint32_t i, double bandwidthMhz);
    void SetCarrierTxPower(uint32_t i, double dbm);
    void SetCarrierEnabled(uint32_t i, bool enabled);
    /// ACM floor / ceiling by name; @return false if a name is unknown
    bool SetCarrierModulationRange(uint32_t i,
                                   const std::string& minModulation,
                                   const std::string& maxModulation);
    void SetAdaptiveModulation(bool adaptive);
    std::string GetCarrierModulation(uint32_t i) const;
    void SetUseMcsTable(bool mcs);
    bool GetUseMcsTable() const;

    // ---- link budget ----------------------------------------------------
    void SetAntennaGainDbi(double dbi);
    /// Effective antenna gain incl. beam-misalignment loss
    double GetAntennaGainDbi() const;
    void SetNoiseFigureDb(double db);
    double GetNoiseFigureDb() const;
    void SetTxPowerLimits(double minDbm, double maxDbm);
    void SetAtpc(bool enabled, double targetRslDbm);
    Time GetRadioLatency() const;

    // ---- protection -----------------------------------------------------
    void SetProtectionMode(CeragonProtectionMode mode);
    CeragonProtectionMode GetProtectionMode() const;
    /// Inject a radio-unit (ODU/RFU) failure; unit 0 = main, 1 = protection
    void FailRadioUnit(uint32_t unit);
    void RestoreRadioUnit(uint32_t unit);
    /// Manual (forced) switchover to the other radio unit
    bool ForceSwitchover();
    uint32_t GetActiveRadioUnit() const;
    uint32_t GetProtectionSwitchCount() const;

    // ---- beamforming (MultiHaul TG) -------------------------------------
    void SetBeamforming(bool enabled, double arrayGainDbi, double beamwidthDeg);
    bool IsBeamformingEnabled() const;
    void SetMisalignmentDeg(double deg);
    /// Pole sway / wind: add pointing error
    void ApplyPoleSway(double deg);
    double GetMisalignmentDeg() const;
    /// radio-bridge-tg-radio-dn:start-topo-scan equivalent
    void StartTopologyScan();
    bool IsScanning() const;
    void SetBeamTracking(bool enabled);

    // ---- security -------------------------------------------------------
    void SetMacsec(bool enabled, const std::string& cipherSuite);
    bool IsMacsecEnabled() const;
    void SetHeaderCompression(bool enabled);

    // ---- energy ---------------------------------------------------------
    void SetCarrierSleep(bool enabled, double sleepLoadFraction);
    double GetPowerConsumptionW() const;
    double GetEnergyConsumedJ() const;

    // ---- sync -----------------------------------------------------------
    void SetSyncMode(CeragonSyncMode mode);
    CeragonSyncMode GetSyncMode() const;
    double GetTimeErrorNs() const;

    // ---- telemetry ------------------------------------------------------
    DataRate GetCurrentDataRate() const;
    double GetAggregateCapacityBps() const;
    uint64_t GetTxPackets() const;
    uint64_t GetRxPackets() const;
    uint64_t GetTxBytes() const;
    uint64_t GetRxBytes() const;
    uint64_t GetDroppedPackets() const;
    uint64_t GetCorruptedPackets() const;
    uint32_t GetModulationChangeCount() const;
    Time GetOutageTime() const;
    /// Force an immediate link evaluation (normally periodic)
    void UpdateLinkState();
    /// One-line JSON status (for CER-Intent / TFS telemetry)
    std::string GetStatusJson() const;
    static std::string ProtectionModeToString(CeragonProtectionMode m);
    static std::string SyncModeToString(CeragonSyncMode m);
    int64_t AssignStreams(int64_t stream);

    // ---- NetDevice API ----------------------------------------------------
    void SetIfIndex(const uint32_t index) override;
    uint32_t GetIfIndex() const override;
    Ptr<Channel> GetChannel() const override;
    void SetAddress(Address address) override;
    Address GetAddress() const override;
    bool SetMtu(const uint16_t mtu) override;
    uint16_t GetMtu() const override;
    bool IsLinkUp() const override;
    void AddLinkChangeCallback(Callback<void> callback) override;
    bool IsBroadcast() const override;
    Address GetBroadcast() const override;
    bool IsMulticast() const override;
    Address GetMulticast(Ipv4Address multicastGroup) const override;
    Address GetMulticast(Ipv6Address addr) const override;
    bool IsPointToPoint() const override;
    bool IsBridge() const override;
    bool Send(Ptr<Packet> packet, const Address& dest, uint16_t protocolNumber) override;
    bool SendFrom(Ptr<Packet> packet,
                  const Address& source,
                  const Address& dest,
                  uint16_t protocolNumber) override;
    Ptr<Node> GetNode() const override;
    void SetNode(Ptr<Node> node) override;
    bool NeedsArp() const override;
    void SetReceiveCallback(NetDevice::ReceiveCallback cb) override;
    void SetPromiscReceiveCallback(PromiscReceiveCallback cb) override;
    bool SupportsSendFrom() const override;

    /// TracedCallback signature for modulation changes
    typedef void (*ModulationChangeTracedCallback)(uint32_t carrier,
                                                   std::string oldMod,
                                                   std::string newMod);
    /// TracedCallback signature for per-carrier RF samples
    typedef void (*RfSampleTracedCallback)(uint32_t carrier, double rslDbm, double sinrDb);
    /// TracedCallback signature for protection switchovers
    typedef void (*ProtectionSwitchTracedCallback)(uint32_t fromUnit, uint32_t toUnit);

  protected:
    void DoInitialize() override;
    void DoDispose() override;

  private:
    enum TxState
    {
        READY,
        BUSY
    };

    bool TransmitStart(Ptr<Packet> p);
    void TransmitComplete();
    void StartNextTransmission();
    uint32_t AirBytes(uint32_t size) const;
    bool DrawCorruption(uint32_t airBytes);
    void ScheduleUpdate();
    void SetLinkUp(bool up);
    void BeamTrackingTick();
    void EndTopologyScan();
    Address GetRemote() const;

    // NetDevice plumbing
    Ptr<Node> m_node;
    Ptr<CeragonRadioChannel> m_channel;
    Ptr<Queue<Packet>> m_queue;
    Mac48Address m_address;
    uint32_t m_ifIndex;
    uint16_t m_mtu;
    bool m_linkUp;
    TxState m_txState;
    Ptr<Packet> m_currentPkt;
    NetDevice::ReceiveCallback m_rxCallback;
    NetDevice::PromiscReceiveCallback m_promiscCallback;
    TracedCallback<> m_linkChangeCallbacks;

    // Product & radio
    std::string m_model;
    const CeragonProductSpec* m_spec;
    std::vector<CeragonCarrier> m_carriers;
    bool m_useMcs;
    bool m_adaptive;
    double m_antennaGainDbi;
    double m_noiseFigureDb;
    double m_minTxPowerDbm;
    double m_maxTxPowerDbm;
    bool m_atpc;
    double m_atpcTargetRslDbm;
    bool m_xpicEnabled;
    double m_xpicImprovementDb;
    double m_tddShare;
    double m_capacityLimitBps;
    double m_acmHysteresisDb;
    Time m_radioLatency;
    Time m_updateInterval;
    EventId m_updateEvent;
    double m_aggregateBps;
    uint32_t m_l1OverheadBytes;

    // Protection
    CeragonProtectionMode m_protection;
    bool m_unitHealthy[2];
    uint32_t m_activeUnit;
    Time m_switchoverEnd;
    Time m_hsbSwitchoverTime;
    Time m_activeBackupSwitchoverTime;
    uint32_t m_switchCount;

    // Beamforming
    bool m_beamforming;
    double m_arrayGainDbi;
    double m_beamwidthDeg;
    double m_misalignmentDeg;
    double m_residualErrorDeg;
    double m_trackingRangeDeg;
    bool m_beamTracking;
    Time m_beamTrackingInterval;
    Time m_scanDuration;
    bool m_scanning;
    EventId m_trackingEvent;

    // Security
    bool m_macsec;
    std::string m_cipherSuite;
    uint32_t m_macsecOverheadBytes;
    bool m_headerCompression;
    uint32_t m_headerCompressionSavedBytes;

    // Energy
    double m_basePowerW;
    double m_carrierPowerW;
    double m_paEfficiency;
    bool m_carrierSleep;
    double m_sleepLoadFraction;
    double m_powerW;
    double m_energyJ;
    uint64_t m_bytesOfferedInterval;
    uint32_t m_lowLoadIntervals;
    Time m_lastUpdate;

    // Sync
    CeragonSyncMode m_syncMode;
    double m_cteNs;
    double m_dteSigmaNs;
    double m_holdoverDriftNsPerS;
    double m_timeErrorNs;

    // Stats
    uint64_t m_txPackets;
    uint64_t m_rxPackets;
    uint64_t m_txBytes;
    uint64_t m_rxBytes;
    uint64_t m_drops;
    uint64_t m_corrupted;
    uint32_t m_modChanges;
    Time m_outageTime;

    Ptr<UniformRandomVariable> m_uniform;
    Ptr<NormalRandomVariable> m_normal;

    // Trace sources
    TracedCallback<Ptr<const Packet>> m_macTxTrace;
    TracedCallback<Ptr<const Packet>> m_macTxDropTrace;
    TracedCallback<Ptr<const Packet>> m_macRxTrace;
    TracedCallback<Ptr<const Packet>> m_phyTxBeginTrace;
    TracedCallback<Ptr<const Packet>> m_phyTxEndTrace;
    TracedCallback<Ptr<const Packet>> m_phyTxDropTrace;
    TracedCallback<Ptr<const Packet>> m_phyRxDropTrace;
    TracedCallback<Ptr<const Packet>> m_snifferTrace;
    TracedCallback<uint32_t, std::string, std::string> m_modulationChangeTrace;
    TracedCallback<uint32_t, double, double> m_rfSampleTrace;
    TracedCallback<uint32_t, uint32_t> m_protectionSwitchTrace;
    TracedCallback<bool> m_linkStateTrace;
    TracedValue<double> m_capacityTrace;
    TracedValue<double> m_powerTrace;
    TracedValue<double> m_timeErrorTrace;
    TracedValue<double> m_misalignmentTrace;
};

} // namespace ns3

#endif /* CERAGON_RADIO_NET_DEVICE_H */
