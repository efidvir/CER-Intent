/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#include "ceragon-radio-net-device.h"

#include "ceragon-propagation.h"
#include "ceragon-radio-channel.h"
#include "ceragon-radio-header.h"

#include "ns3/boolean.h"
#include "ns3/double.h"
#include "ns3/log.h"
#include "ns3/node.h"
#include "ns3/pointer.h"
#include "ns3/simulator.h"
#include "ns3/string.h"
#include "ns3/trace-source-accessor.h"
#include "ns3/uinteger.h"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <sstream>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("CeragonRadioNetDevice");
NS_OBJECT_ENSURE_REGISTERED(CeragonRadioNetDevice);

namespace
{
double
DbmSum(double aDbm, double bDbm)
{
    return 10.0 * std::log10(std::pow(10.0, aDbm / 10.0) + std::pow(10.0, bDbm / 10.0));
}
} // namespace

TypeId
CeragonRadioNetDevice::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::CeragonRadioNetDevice")
            .SetParent<NetDevice>()
            .SetGroupName("Ceragon")
            .AddConstructor<CeragonRadioNetDevice>()
            .AddAttribute("Mtu",
                          "MAC-level MTU",
                          UintegerValue(1500),
                          MakeUintegerAccessor(&CeragonRadioNetDevice::SetMtu,
                                               &CeragonRadioNetDevice::GetMtu),
                          MakeUintegerChecker<uint16_t>())
            .AddAttribute("Address",
                          "MAC address of the radio",
                          Mac48AddressValue(Mac48Address("ff:ff:ff:ff:ff:ff")),
                          MakeMac48AddressAccessor(&CeragonRadioNetDevice::m_address),
                          MakeMac48AddressChecker())
            .AddAttribute("ProductModel",
                          "Ceragon product model (IP-20C, IP-50EX, EH-8010FX, MH-N366, ...)",
                          StringValue(""),
                          MakeStringAccessor(&CeragonRadioNetDevice::SetProductModel,
                                             &CeragonRadioNetDevice::GetProductModel),
                          MakeStringChecker())
            .AddAttribute("TxQueue",
                          "Transmit queue of the radio",
                          PointerValue(),
                          MakePointerAccessor(&CeragonRadioNetDevice::m_queue),
                          MakePointerChecker<Queue<Packet>>())
            .AddAttribute("LinkUpdateInterval",
                          "Period of the RF/ACM/ATPC evaluation",
                          TimeValue(MilliSeconds(10)),
                          MakeTimeAccessor(&CeragonRadioNetDevice::m_updateInterval),
                          MakeTimeChecker())
            .AddAttribute("RadioLatency",
                          "Modem + framing latency added per hop",
                          TimeValue(MicroSeconds(30)),
                          MakeTimeAccessor(&CeragonRadioNetDevice::m_radioLatency),
                          MakeTimeChecker())
            .AddAttribute("AntennaGain",
                          "Antenna gain (dBi) when beamforming is disabled",
                          DoubleValue(35.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_antennaGainDbi),
                          MakeDoubleChecker<double>())
            .AddAttribute("NoiseFigure",
                          "Receiver noise figure (dB)",
                          DoubleValue(6.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_noiseFigureDb),
                          MakeDoubleChecker<double>())
            .AddAttribute("MinTxPower",
                          "Minimum transmit power (dBm)",
                          DoubleValue(-10.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_minTxPowerDbm),
                          MakeDoubleChecker<double>())
            .AddAttribute("MaxTxPower",
                          "Maximum transmit power (dBm)",
                          DoubleValue(24.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_maxTxPowerDbm),
                          MakeDoubleChecker<double>())
            .AddAttribute("AtpcEnabled",
                          "Automatic Transmit Power Control",
                          BooleanValue(false),
                          MakeBooleanAccessor(&CeragonRadioNetDevice::m_atpc),
                          MakeBooleanChecker())
            .AddAttribute("AtpcTargetRsl",
                          "ATPC / Green-ATPC target receive level (dBm)",
                          DoubleValue(-45.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_atpcTargetRslDbm),
                          MakeDoubleChecker<double>())
            .AddAttribute("XpicEnabled",
                          "Cross-Polarization Interference Canceller on H/V carrier pairs",
                          BooleanValue(true),
                          MakeBooleanAccessor(&CeragonRadioNetDevice::m_xpicEnabled),
                          MakeBooleanChecker())
            .AddAttribute("XpicImprovement",
                          "XPIC cancellation improvement factor (dB)",
                          DoubleValue(20.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_xpicImprovementDb),
                          MakeDoubleChecker<double>(0.0))
            .AddAttribute("TddShare",
                          "Air-time share of this direction on TDD products",
                          DoubleValue(0.5),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_tddShare),
                          MakeDoubleChecker<double>(0.05, 1.0))
            .AddAttribute("CapacityLimit",
                          "Aggregate capacity cap (bit/s); 0 = product capacity",
                          DoubleValue(0.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_capacityLimitBps),
                          MakeDoubleChecker<double>(0.0))
            .AddAttribute("AcmHysteresis",
                          "ACM upshift hysteresis (dB)",
                          DoubleValue(1.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_acmHysteresisDb),
                          MakeDoubleChecker<double>(0.0))
            .AddAttribute("L1OverheadBytes",
                          "Per-frame air-interface framing overhead (bytes)",
                          UintegerValue(8),
                          MakeUintegerAccessor(&CeragonRadioNetDevice::m_l1OverheadBytes),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("HsbSwitchoverTime",
                          "1+1 HSB switchover time",
                          TimeValue(MilliSeconds(50)),
                          MakeTimeAccessor(&CeragonRadioNetDevice::m_hsbSwitchoverTime),
                          MakeTimeChecker())
            .AddAttribute("ActiveBackupSwitchoverTime",
                          "MultiHaul TG active-backup bond failover time",
                          TimeValue(MilliSeconds(100)),
                          MakeTimeAccessor(&CeragonRadioNetDevice::m_activeBackupSwitchoverTime),
                          MakeTimeChecker())
            .AddAttribute("BeamResidualError",
                          "Pointing error after beam training (deg)",
                          DoubleValue(0.2),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_residualErrorDeg),
                          MakeDoubleChecker<double>(0.0))
            .AddAttribute("BeamTrackingRange",
                          "Max pointing error recoverable by beam tracking (deg)",
                          DoubleValue(8.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_trackingRangeDeg),
                          MakeDoubleChecker<double>(0.0))
            .AddAttribute("BeamTrackingInterval",
                          "Beam tracking period",
                          TimeValue(MilliSeconds(100)),
                          MakeTimeAccessor(&CeragonRadioNetDevice::m_beamTrackingInterval),
                          MakeTimeChecker())
            .AddAttribute("TopologyScanDuration",
                          "Duration of a Terragraph topology scan",
                          TimeValue(MilliSeconds(500)),
                          MakeTimeAccessor(&CeragonRadioNetDevice::m_scanDuration),
                          MakeTimeChecker())
            .AddAttribute("MacsecOverhead",
                          "IEEE 802.1AE SecTAG + ICV overhead (bytes)",
                          UintegerValue(32),
                          MakeUintegerAccessor(&CeragonRadioNetDevice::m_macsecOverheadBytes),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("HeaderCompressionSaving",
                          "Bytes saved per frame by header de-duplication",
                          UintegerValue(40),
                          MakeUintegerAccessor(
                              &CeragonRadioNetDevice::m_headerCompressionSavedBytes),
                          MakeUintegerChecker<uint32_t>())
            .AddAttribute("BasePower",
                          "Base DC power consumption (W)",
                          DoubleValue(25.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_basePowerW),
                          MakeDoubleChecker<double>(0.0))
            .AddAttribute("CarrierPower",
                          "Per active carrier DC power excluding the PA (W)",
                          DoubleValue(10.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_carrierPowerW),
                          MakeDoubleChecker<double>(0.0))
            .AddAttribute("PaEfficiency",
                          "Power amplifier DC-to-RF efficiency",
                          DoubleValue(0.08),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_paEfficiency),
                          MakeDoubleChecker<double>(0.001, 1.0))
            .AddAttribute("CarrierSleepLoadFraction",
                          "Secondary carriers sleep below this fraction of primary capacity",
                          DoubleValue(0.3),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_sleepLoadFraction),
                          MakeDoubleChecker<double>(0.0, 1.0))
            .AddAttribute("ConstantTimeErrorNs",
                          "Per-node constant time error cTE (ns), G.8273.2 class",
                          DoubleValue(20.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_cteNs),
                          MakeDoubleChecker<double>())
            .AddAttribute("DynamicTimeErrorSigmaNs",
                          "Dynamic time error dTE standard deviation (ns)",
                          DoubleValue(5.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_dteSigmaNs),
                          MakeDoubleChecker<double>(0.0))
            .AddAttribute("HoldoverDriftNsPerS",
                          "Time error accumulation in holdover (ns/s)",
                          DoubleValue(50.0),
                          MakeDoubleAccessor(&CeragonRadioNetDevice::m_holdoverDriftNsPerS),
                          MakeDoubleChecker<double>(0.0))
            .AddTraceSource("MacTx",
                            "Packet accepted for transmission",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_macTxTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("MacTxDrop",
                            "Packet dropped before transmission",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_macTxDropTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("MacRx",
                            "Packet received and passed up",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_macRxTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("PhyTxBegin",
                            "Frame transmission started",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_phyTxBeginTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("PhyTxEnd",
                            "Frame transmission completed",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_phyTxEndTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("PhyTxDrop",
                            "Frame dropped by the radio (link outage)",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_phyTxDropTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("PhyRxDrop",
                            "Frame received in error (BER) or during switchover",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_phyRxDropTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource("Sniffer",
                            "Packet sniffer",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_snifferTrace),
                            "ns3::Packet::TracedCallback")
            .AddTraceSource(
                "ModulationChange",
                "ACM profile change on a carrier",
                MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_modulationChangeTrace),
                "ns3::CeragonRadioNetDevice::ModulationChangeTracedCallback")
            .AddTraceSource("RfSample",
                            "Per-carrier RSL / SINR sample",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_rfSampleTrace),
                            "ns3::CeragonRadioNetDevice::RfSampleTracedCallback")
            .AddTraceSource(
                "ProtectionSwitch",
                "Radio protection switchover",
                MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_protectionSwitchTrace),
                "ns3::CeragonRadioNetDevice::ProtectionSwitchTracedCallback")
            .AddTraceSource("LinkState",
                            "Radio link up/down",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_linkStateTrace),
                            "ns3::TracedValueCallback::Bool")
            .AddTraceSource("Capacity",
                            "Aggregate radio capacity (bit/s)",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_capacityTrace),
                            "ns3::TracedValueCallback::Double")
            .AddTraceSource("PowerConsumption",
                            "DC power consumption (W)",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_powerTrace),
                            "ns3::TracedValueCallback::Double")
            .AddTraceSource("TimeError",
                            "PTP time error (ns)",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_timeErrorTrace),
                            "ns3::TracedValueCallback::Double")
            .AddTraceSource("BeamMisalignment",
                            "60 GHz beam pointing error (deg)",
                            MakeTraceSourceAccessor(&CeragonRadioNetDevice::m_misalignmentTrace),
                            "ns3::TracedValueCallback::Double");
    return tid;
}

CeragonRadioNetDevice::CeragonRadioNetDevice()
    : m_ifIndex(0),
      m_mtu(1500),
      m_linkUp(false),
      m_txState(READY),
      m_spec(nullptr),
      m_useMcs(false),
      m_adaptive(true),
      m_antennaGainDbi(35.0),
      m_noiseFigureDb(6.0),
      m_minTxPowerDbm(-10.0),
      m_maxTxPowerDbm(24.0),
      m_atpc(false),
      m_atpcTargetRslDbm(-45.0),
      m_xpicEnabled(true),
      m_xpicImprovementDb(20.0),
      m_tddShare(0.5),
      m_capacityLimitBps(0.0),
      m_acmHysteresisDb(1.0),
      m_aggregateBps(0.0),
      m_l1OverheadBytes(8),
      m_protection(CeragonProtectionMode::NONE),
      m_unitHealthy{true, true},
      m_activeUnit(0),
      m_switchoverEnd(Seconds(0)),
      m_switchCount(0),
      m_beamforming(false),
      m_arrayGainDbi(22.5),
      m_beamwidthDeg(2.8),
      m_misalignmentDeg(0.0),
      m_residualErrorDeg(0.2),
      m_trackingRangeDeg(8.0),
      m_beamTracking(true),
      m_scanning(false),
      m_macsec(false),
      m_cipherSuite("gcm-aes-256"),
      m_macsecOverheadBytes(32),
      m_headerCompression(false),
      m_headerCompressionSavedBytes(40),
      m_basePowerW(25.0),
      m_carrierPowerW(10.0),
      m_paEfficiency(0.08),
      m_carrierSleep(false),
      m_sleepLoadFraction(0.3),
      m_powerW(0.0),
      m_energyJ(0.0),
      m_bytesOfferedInterval(0),
      m_lowLoadIntervals(0),
      m_lastUpdate(Seconds(0)),
      m_syncMode(CeragonSyncMode::NONE),
      m_cteNs(20.0),
      m_dteSigmaNs(5.0),
      m_holdoverDriftNsPerS(50.0),
      m_timeErrorNs(0.0),
      m_txPackets(0),
      m_rxPackets(0),
      m_txBytes(0),
      m_rxBytes(0),
      m_drops(0),
      m_corrupted(0),
      m_modChanges(0),
      m_outageTime(Seconds(0)),
      m_capacityTrace(0.0),
      m_powerTrace(0.0),
      m_timeErrorTrace(0.0),
      m_misalignmentTrace(0.0)
{
    NS_LOG_FUNCTION(this);
    m_uniform = CreateObject<UniformRandomVariable>();
    m_normal = CreateObject<NormalRandomVariable>();
    m_normal->SetAttribute("Mean", DoubleValue(0.0));
    m_normal->SetAttribute("Variance", DoubleValue(1.0));
}

CeragonRadioNetDevice::~CeragonRadioNetDevice()
{
    NS_LOG_FUNCTION(this);
}

void
CeragonRadioNetDevice::DoInitialize()
{
    NS_LOG_FUNCTION(this);
    m_lastUpdate = Simulator::Now();
    ScheduleUpdate();
    if (m_beamforming && m_beamTracking)
    {
        m_trackingEvent = Simulator::Schedule(m_beamTrackingInterval,
                                              &CeragonRadioNetDevice::BeamTrackingTick,
                                              this);
    }
    NetDevice::DoInitialize();
}

void
CeragonRadioNetDevice::DoDispose()
{
    NS_LOG_FUNCTION(this);
    m_updateEvent.Cancel();
    m_trackingEvent.Cancel();
    m_node = nullptr;
    m_channel = nullptr;
    m_queue = nullptr;
    m_currentPkt = nullptr;
    m_uniform = nullptr;
    m_normal = nullptr;
    NetDevice::DoDispose();
}

// ---------------------------------------------------------------- wiring ----

bool
CeragonRadioNetDevice::Attach(Ptr<CeragonRadioChannel> channel)
{
    NS_LOG_FUNCTION(this << channel);
    m_channel = channel;
    m_channel->Attach(this);
    m_linkUp = true; // re-evaluated at the first link update
    return true;
}

void
CeragonRadioNetDevice::SetQueue(Ptr<Queue<Packet>> queue)
{
    m_queue = queue;
}

Ptr<Queue<Packet>>
CeragonRadioNetDevice::GetQueue() const
{
    return m_queue;
}

// --------------------------------------------------------------- product ----

void
CeragonRadioNetDevice::SetProductModel(std::string model)
{
    m_model = model;
    m_spec = CeragonPortfolio::Resolve(model);
    if (m_spec)
    {
        m_useMcs = (m_spec->flavor == CeragonApiFlavor::SIKLU_TG);
    }
}

std::string
CeragonRadioNetDevice::GetProductModel() const
{
    return m_spec ? m_spec->model : m_model;
}

const CeragonProductSpec*
CeragonRadioNetDevice::GetSpec() const
{
    return m_spec;
}

// -------------------------------------------------------------- carriers ----

uint32_t
CeragonRadioNetDevice::AddCarrier(double frequencyMhz,
                                  double bandwidthMhz,
                                  bool verticalPol,
                                  const std::string& maxModulation,
                                  const std::string& minModulation)
{
    CeragonCarrier c;
    c.frequencyMhz = frequencyMhz;
    c.bandwidthMhz = bandwidthMhz;
    c.verticalPol = verticalPol;
    c.txPowerDbm = m_maxTxPowerDbm;
    const auto& table = m_useMcs ? CeragonAcm::GetMcsTable() : CeragonAcm::GetQamTable();
    int maxIdx = CeragonAcm::FindIndex(table, maxModulation);
    int minIdx = CeragonAcm::FindIndex(table, minModulation);
    if (maxIdx < 0)
    {
        maxIdx = static_cast<int>(table.size()) - 1;
    }
    if (minIdx < 0)
    {
        minIdx = m_useMcs ? 0 : 1; // MCS1 / QPSK
    }
    c.acm.Configure(m_useMcs, minIdx, maxIdx);
    c.acm.SetAdaptive(m_adaptive);
    c.acm.SetHysteresis(m_acmHysteresisDb);
    m_carriers.push_back(c);
    return static_cast<uint32_t>(m_carriers.size() - 1);
}

void
CeragonRadioNetDevice::ClearCarriers()
{
    m_carriers.clear();
}

uint32_t
CeragonRadioNetDevice::GetNCarriers() const
{
    return static_cast<uint32_t>(m_carriers.size());
}

const CeragonCarrier&
CeragonRadioNetDevice::GetCarrier(uint32_t i) const
{
    NS_ASSERT(i < m_carriers.size());
    return m_carriers[i];
}

void
CeragonRadioNetDevice::SetCarrierFrequency(uint32_t i, double frequencyMhz)
{
    NS_ASSERT(i < m_carriers.size());
    m_carriers[i].frequencyMhz = frequencyMhz;
}

void
CeragonRadioNetDevice::SetCarrierBandwidth(uint32_t i, double bandwidthMhz)
{
    NS_ASSERT(i < m_carriers.size());
    m_carriers[i].bandwidthMhz = bandwidthMhz;
}

void
CeragonRadioNetDevice::SetCarrierTxPower(uint32_t i, double dbm)
{
    NS_ASSERT(i < m_carriers.size());
    m_carriers[i].txPowerDbm = std::clamp(dbm, m_minTxPowerDbm, m_maxTxPowerDbm);
}

void
CeragonRadioNetDevice::SetCarrierEnabled(uint32_t i, bool enabled)
{
    NS_ASSERT(i < m_carriers.size());
    m_carriers[i].enabled = enabled;
}

bool
CeragonRadioNetDevice::SetCarrierModulationRange(uint32_t i,
                                                 const std::string& minModulation,
                                                 const std::string& maxModulation)
{
    NS_ASSERT(i < m_carriers.size());
    const auto& table = m_carriers[i].acm.GetTable();
    int minIdx = CeragonAcm::FindIndex(table, minModulation);
    int maxIdx = CeragonAcm::FindIndex(table, maxModulation);
    if (minIdx < 0 || maxIdx < 0)
    {
        return false;
    }
    m_carriers[i].acm.SetRange(minIdx, maxIdx);
    return true;
}

void
CeragonRadioNetDevice::SetAdaptiveModulation(bool adaptive)
{
    m_adaptive = adaptive;
    for (auto& c : m_carriers)
    {
        c.acm.SetAdaptive(adaptive);
    }
}

std::string
CeragonRadioNetDevice::GetCarrierModulation(uint32_t i) const
{
    NS_ASSERT(i < m_carriers.size());
    return m_carriers[i].acm.GetCurrentName();
}

void
CeragonRadioNetDevice::SetUseMcsTable(bool mcs)
{
    m_useMcs = mcs;
}

bool
CeragonRadioNetDevice::GetUseMcsTable() const
{
    return m_useMcs;
}

// ----------------------------------------------------------- link budget ----

void
CeragonRadioNetDevice::SetAntennaGainDbi(double dbi)
{
    m_antennaGainDbi = dbi;
}

double
CeragonRadioNetDevice::GetAntennaGainDbi() const
{
    if (!m_beamforming)
    {
        return m_antennaGainDbi;
    }
    const double x = m_misalignmentDeg / std::max(0.1, m_beamwidthDeg);
    return m_arrayGainDbi - std::min(12.0 * x * x, 25.0); // Gaussian main lobe, -25 dB sidelobe floor
}

void
CeragonRadioNetDevice::SetNoiseFigureDb(double db)
{
    m_noiseFigureDb = db;
}

double
CeragonRadioNetDevice::GetNoiseFigureDb() const
{
    return m_noiseFigureDb;
}

void
CeragonRadioNetDevice::SetTxPowerLimits(double minDbm, double maxDbm)
{
    m_minTxPowerDbm = minDbm;
    m_maxTxPowerDbm = std::max(minDbm, maxDbm);
    for (auto& c : m_carriers)
    {
        c.txPowerDbm = std::clamp(c.txPowerDbm, m_minTxPowerDbm, m_maxTxPowerDbm);
    }
}

void
CeragonRadioNetDevice::SetAtpc(bool enabled, double targetRslDbm)
{
    m_atpc = enabled;
    m_atpcTargetRslDbm = targetRslDbm;
}

Time
CeragonRadioNetDevice::GetRadioLatency() const
{
    return m_radioLatency;
}

// ------------------------------------------------------------ protection ----

void
CeragonRadioNetDevice::SetProtectionMode(CeragonProtectionMode mode)
{
    m_protection = mode;
}

CeragonProtectionMode
CeragonRadioNetDevice::GetProtectionMode() const
{
    return m_protection;
}

bool
CeragonRadioNetDevice::ForceSwitchover()
{
    NS_LOG_FUNCTION(this);
    const uint32_t other = 1 - m_activeUnit;
    if (m_protection == CeragonProtectionMode::NONE || !m_unitHealthy[other])
    {
        return false;
    }
    Time t = Seconds(0);
    if (m_protection == CeragonProtectionMode::HSB_1PLUS1)
    {
        t = m_hsbSwitchoverTime;
    }
    else if (m_protection == CeragonProtectionMode::ACTIVE_BACKUP)
    {
        t = m_activeBackupSwitchoverTime;
    }
    const uint32_t from = m_activeUnit;
    m_activeUnit = other;
    m_switchoverEnd = Simulator::Now() + t;
    m_switchCount++;
    m_protectionSwitchTrace(from, other);
    NS_LOG_INFO("Protection switchover " << from << " -> " << other << " (" << t.As(Time::MS)
                                         << ")");
    UpdateLinkState();
    if (t.IsStrictlyPositive())
    {
        Simulator::Schedule(t, &CeragonRadioNetDevice::UpdateLinkState, this);
    }
    return true;
}

void
CeragonRadioNetDevice::FailRadioUnit(uint32_t unit)
{
    NS_LOG_FUNCTION(this << unit);
    NS_ASSERT(unit < 2);
    m_unitHealthy[unit] = false;
    if (unit == m_activeUnit)
    {
        if (!ForceSwitchover())
        {
            UpdateLinkState();
        }
    }
    else
    {
        UpdateLinkState();
    }
}

void
CeragonRadioNetDevice::RestoreRadioUnit(uint32_t unit)
{
    NS_LOG_FUNCTION(this << unit);
    NS_ASSERT(unit < 2);
    m_unitHealthy[unit] = true;
    UpdateLinkState();
}

uint32_t
CeragonRadioNetDevice::GetActiveRadioUnit() const
{
    return m_activeUnit;
}

uint32_t
CeragonRadioNetDevice::GetProtectionSwitchCount() const
{
    return m_switchCount;
}

// ----------------------------------------------------------- beamforming ----

void
CeragonRadioNetDevice::SetBeamforming(bool enabled, double arrayGainDbi, double beamwidthDeg)
{
    m_beamforming = enabled;
    m_arrayGainDbi = arrayGainDbi;
    m_beamwidthDeg = beamwidthDeg;
}

bool
CeragonRadioNetDevice::IsBeamformingEnabled() const
{
    return m_beamforming;
}

void
CeragonRadioNetDevice::SetMisalignmentDeg(double deg)
{
    m_misalignmentDeg = std::abs(deg);
    m_misalignmentTrace = m_misalignmentDeg;
}

void
CeragonRadioNetDevice::ApplyPoleSway(double deg)
{
    NS_LOG_FUNCTION(this << deg);
    SetMisalignmentDeg(m_misalignmentDeg + std::abs(deg));
    UpdateLinkState();
}

double
CeragonRadioNetDevice::GetMisalignmentDeg() const
{
    return m_misalignmentDeg;
}

void
CeragonRadioNetDevice::StartTopologyScan()
{
    NS_LOG_FUNCTION(this);
    if (m_scanning)
    {
        return;
    }
    m_scanning = true;
    Simulator::Schedule(m_scanDuration, &CeragonRadioNetDevice::EndTopologyScan, this);
}

void
CeragonRadioNetDevice::EndTopologyScan()
{
    m_scanning = false;
    SetMisalignmentDeg(m_residualErrorDeg);
    UpdateLinkState();
}

bool
CeragonRadioNetDevice::IsScanning() const
{
    return m_scanning;
}

void
CeragonRadioNetDevice::SetBeamTracking(bool enabled)
{
    m_beamTracking = enabled;
    if (enabled && m_beamforming && IsInitialized() && !m_trackingEvent.IsPending())
    {
        m_trackingEvent = Simulator::Schedule(m_beamTrackingInterval,
                                              &CeragonRadioNetDevice::BeamTrackingTick,
                                              this);
    }
}

void
CeragonRadioNetDevice::BeamTrackingTick()
{
    if (!m_beamTracking || !m_beamforming)
    {
        return;
    }
    if (!m_scanning && m_misalignmentDeg > m_residualErrorDeg &&
        m_misalignmentDeg <= m_trackingRangeDeg)
    {
        SetMisalignmentDeg(m_residualErrorDeg); // re-train to the best codebook beam
    }
    m_trackingEvent =
        Simulator::Schedule(m_beamTrackingInterval, &CeragonRadioNetDevice::BeamTrackingTick, this);
}

// -------------------------------------------------------------- security ----

void
CeragonRadioNetDevice::SetMacsec(bool enabled, const std::string& cipherSuite)
{
    m_macsec = enabled;
    m_cipherSuite = cipherSuite;
}

bool
CeragonRadioNetDevice::IsMacsecEnabled() const
{
    return m_macsec;
}

void
CeragonRadioNetDevice::SetHeaderCompression(bool enabled)
{
    m_headerCompression = enabled;
}

// ---------------------------------------------------------------- energy ----

void
CeragonRadioNetDevice::SetCarrierSleep(bool enabled, double sleepLoadFraction)
{
    m_carrierSleep = enabled;
    m_sleepLoadFraction = sleepLoadFraction;
    if (!enabled)
    {
        for (auto& c : m_carriers)
        {
            c.sleeping = false;
        }
    }
}

double
CeragonRadioNetDevice::GetPowerConsumptionW() const
{
    return m_powerW;
}

double
CeragonRadioNetDevice::GetEnergyConsumedJ() const
{
    return m_energyJ;
}

// ------------------------------------------------------------------ sync ----

void
CeragonRadioNetDevice::SetSyncMode(CeragonSyncMode mode)
{
    m_syncMode = mode;
    switch (mode)
    {
    case CeragonSyncMode::PTP_BOUNDARY_CLOCK:
        m_cteNs = 20.0; // G.8273.2 class B
        break;
    case CeragonSyncMode::PTP_TRANSPARENT_CLOCK:
        m_cteNs = 10.0;
        break;
    case CeragonSyncMode::SYNCE_PTP:
        m_cteNs = 10.0; // class C with SyncE frequency assist
        m_holdoverDriftNsPerS = 5.0;
        break;
    default:
        break;
    }
    m_timeErrorNs = m_cteNs;
}

CeragonSyncMode
CeragonRadioNetDevice::GetSyncMode() const
{
    return m_syncMode;
}

double
CeragonRadioNetDevice::GetTimeErrorNs() const
{
    return m_timeErrorNs;
}

// ------------------------------------------------------------- telemetry ----

DataRate
CeragonRadioNetDevice::GetCurrentDataRate() const
{
    return DataRate(static_cast<uint64_t>(m_aggregateBps));
}

double
CeragonRadioNetDevice::GetAggregateCapacityBps() const
{
    return m_aggregateBps;
}

uint64_t
CeragonRadioNetDevice::GetTxPackets() const
{
    return m_txPackets;
}

uint64_t
CeragonRadioNetDevice::GetRxPackets() const
{
    return m_rxPackets;
}

uint64_t
CeragonRadioNetDevice::GetTxBytes() const
{
    return m_txBytes;
}

uint64_t
CeragonRadioNetDevice::GetRxBytes() const
{
    return m_rxBytes;
}

uint64_t
CeragonRadioNetDevice::GetDroppedPackets() const
{
    return m_drops;
}

uint64_t
CeragonRadioNetDevice::GetCorruptedPackets() const
{
    return m_corrupted;
}

uint32_t
CeragonRadioNetDevice::GetModulationChangeCount() const
{
    return m_modChanges;
}

Time
CeragonRadioNetDevice::GetOutageTime() const
{
    return m_outageTime;
}

std::string
CeragonRadioNetDevice::ProtectionModeToString(CeragonProtectionMode m)
{
    switch (m)
    {
    case CeragonProtectionMode::HSB_1PLUS1:
        return "1+1_HSB";
    case CeragonProtectionMode::SPACE_DIVERSITY:
        return "1+1_SD";
    case CeragonProtectionMode::ACTIVE_BACKUP:
        return "active-backup";
    default:
        return "none";
    }
}

std::string
CeragonRadioNetDevice::SyncModeToString(CeragonSyncMode m)
{
    switch (m)
    {
    case CeragonSyncMode::PTP_BOUNDARY_CLOCK:
        return "ptp-bc";
    case CeragonSyncMode::PTP_TRANSPARENT_CLOCK:
        return "ptp-tc";
    case CeragonSyncMode::SYNCE_PTP:
        return "synce+ptp";
    default:
        return "none";
    }
}

std::string
CeragonRadioNetDevice::GetStatusJson() const
{
    std::ostringstream os;
    os << std::fixed << std::setprecision(3);
    os << "{\"node\":" << (m_node ? m_node->GetId() : 0) << ",\"ifindex\":" << m_ifIndex
       << ",\"model\":\"" << GetProductModel() << "\""
       << ",\"family\":\"" << (m_spec ? m_spec->family : "unknown") << "\""
       << ",\"api_flavor\":\"" << (m_spec ? m_spec->FlavorString() : "") << "\""
       << ",\"link_up\":" << (m_linkUp ? "true" : "false")
       << ",\"capacity_mbps\":" << m_aggregateBps / 1e6
       << ",\"rain_mmh\":" << (m_channel ? m_channel->GetRainRate() : 0.0)
       << ",\"distance_km\":" << (m_channel ? m_channel->GetDistanceKm() : 0.0)
       << ",\"protection\":\"" << ProtectionModeToString(m_protection) << "\""
       << ",\"active_unit\":" << m_activeUnit << ",\"switchovers\":" << m_switchCount
       << ",\"macsec\":" << (m_macsec ? "true" : "false") << ",\"atpc\":"
       << (m_atpc ? "true" : "false") << ",\"power_w\":" << m_powerW
       << ",\"energy_j\":" << m_energyJ << ",\"sync\":\"" << SyncModeToString(m_syncMode)
       << "\",\"time_error_ns\":" << m_timeErrorNs
       << ",\"beam_misalignment_deg\":" << m_misalignmentDeg << ",\"tx_packets\":" << m_txPackets
       << ",\"rx_packets\":" << m_rxPackets << ",\"dropped\":" << m_drops
       << ",\"corrupted\":" << m_corrupted << ",\"modulation_changes\":" << m_modChanges
       << ",\"outage_s\":" << m_outageTime.GetSeconds() << ",\"carriers\":[";
    for (size_t i = 0; i < m_carriers.size(); ++i)
    {
        const auto& c = m_carriers[i];
        os << (i ? "," : "") << "{\"freq_mhz\":" << c.frequencyMhz
           << ",\"bw_mhz\":" << c.bandwidthMhz << ",\"pol\":\"" << (c.verticalPol ? "V" : "H")
           << "\",\"modulation\":\"" << c.acm.GetCurrentName() << "\""
           << ",\"rsl_dbm\":" << c.rslDbm << ",\"sinr_db\":" << c.sinrDb
           << ",\"tx_power_dbm\":" << c.txPowerDbm << ",\"rate_mbps\":" << c.rateBps / 1e6
           << ",\"rain_att_db\":" << c.rainAttDb << ",\"xpd_db\":" << c.xpdDb
           << ",\"sleeping\":" << (c.sleeping ? "true" : "false")
           << ",\"up\":" << (c.up ? "true" : "false") << "}";
    }
    os << "]}";
    return os.str();
}

int64_t
CeragonRadioNetDevice::AssignStreams(int64_t stream)
{
    m_uniform->SetStream(stream);
    m_normal->SetStream(stream + 1);
    return 2;
}

// --------------------------------------------------------- link engine ----

void
CeragonRadioNetDevice::ScheduleUpdate()
{
    UpdateLinkState();
    m_updateEvent =
        Simulator::Schedule(m_updateInterval, &CeragonRadioNetDevice::ScheduleUpdate, this);
}

void
CeragonRadioNetDevice::UpdateLinkState()
{
    const Time now = Simulator::Now();
    const double dt = (now - m_lastUpdate).GetSeconds();
    double offeredBps = 0.0;
    if (dt > 0.0)
    {
        m_energyJ += m_powerW * dt;
        if (!m_linkUp)
        {
            m_outageTime += now - m_lastUpdate;
        }
        offeredBps = static_cast<double>(m_bytesOfferedInterval) * 8.0 / dt;
        m_bytesOfferedInterval = 0;
        m_lastUpdate = now;
    }

    Ptr<CeragonRadioNetDevice> peer = m_channel ? m_channel->GetPeer(this) : nullptr;
    const bool unitAvailable = m_unitHealthy[m_activeUnit] && now >= m_switchoverEnd;
    const bool diversity = (m_protection == CeragonProtectionMode::SPACE_DIVERSITY) &&
                           m_unitHealthy[0] && m_unitHealthy[1];
    const bool tdd = m_spec && m_spec->IsTdd();

    double total = 0.0;
    for (uint32_t i = 0; i < m_carriers.size(); ++i)
    {
        CeragonCarrier& c = m_carriers[i];
        const std::string oldMod = c.acm.GetCurrentName();
        if (!peer || !c.enabled || c.sleeping || !unitAvailable)
        {
            c.up = false;
            c.rateBps = 0.0;
            continue;
        }
        const double fGhz = c.frequencyMhz / 1000.0;
        const double pathLoss = m_channel->GetPathLossDb(fGhz, c.verticalPol);
        c.rainAttDb = m_channel->GetRainAttenuationDb(fGhz, c.verticalPol);
        double fading = m_channel->SampleFadingDb();
        if (diversity)
        {
            fading = std::max(fading, m_channel->SampleFadingDb()); // selection diversity
        }
        // Same (dual-band) aperture on both ends: gain scales with 20log10(f/f0)
        const double apertureAdjDb =
            (!m_beamforming && i > 0)
                ? 20.0 * std::log10(c.frequencyMhz / m_carriers[0].frequencyMhz)
                : 0.0;
        c.rslDbm = c.txPowerDbm + GetAntennaGainDbi() + peer->GetAntennaGainDbi() +
                   2.0 * apertureAdjDb - pathLoss + fading;
        const double noise =
            CeragonItuPropagation::NoiseFloorDbm(c.bandwidthMhz, peer->GetNoiseFigureDb());
        double sinr = c.rslDbm - DbmSum(noise, m_channel->GetInterferenceDbm());

        // XPIC: co-channel carrier on the orthogonal polarization
        c.xpdDb = 40.0;
        for (uint32_t j = 0; j < m_carriers.size(); ++j)
        {
            const CeragonCarrier& o = m_carriers[j];
            if (j != i && o.enabled && !o.sleeping &&
                std::abs(o.frequencyMhz - c.frequencyMhz) < 1.0 && o.verticalPol != c.verticalPol)
            {
                c.xpdDb = CeragonItuPropagation::XpdDb(fGhz, c.rainAttDb);
                const double xpi = c.xpdDb + (m_xpicEnabled ? m_xpicImprovementDb : 0.0);
                sinr = -10.0 * std::log10(std::pow(10.0, -sinr / 10.0) +
                                          std::pow(10.0, -xpi / 10.0));
                break;
            }
        }
        c.sinrDb = sinr;

        // ATPC: converge towards the target RSL (1 dB/step), effective next interval
        if (m_atpc)
        {
            const double step = std::clamp(m_atpcTargetRslDbm - c.rslDbm, -1.0, 1.0);
            c.txPowerDbm = std::clamp(c.txPowerDbm + step, m_minTxPowerDbm, m_maxTxPowerDbm);
        }

        const int idx = c.acm.Update(sinr);
        if (idx < 0)
        {
            c.up = false;
            c.rateBps = 0.0;
        }
        else
        {
            c.up = true;
            c.rateBps =
                CeragonAcm::CarrierRateBps(c.acm.GetTable()[idx], c.bandwidthMhz, m_useMcs);
            if (tdd)
            {
                c.rateBps *= m_tddShare;
            }
        }
        const std::string newMod = c.acm.GetCurrentName();
        if (newMod != oldMod)
        {
            m_modChanges++;
            m_modulationChangeTrace(i, oldMod, newMod);
            NS_LOG_INFO("Node " << (m_node ? m_node->GetId() : 0) << " carrier " << i << " "
                                << oldMod << " -> " << newMod << " (SINR " << sinr << " dB)");
        }
        m_rfSampleTrace(i, c.rslDbm, c.sinrDb);
        total += c.rateBps;
    }

    const double cap = (m_capacityLimitBps > 0.0) ? m_capacityLimitBps
                                                  : (m_spec ? m_spec->maxCapacityGbps * 1e9 : 0.0);
    if (cap > 0.0)
    {
        total = std::min(total, cap);
    }
    m_aggregateBps = total;
    m_capacityTrace = total;

    // Energy: low-load secondary-carrier sleep (Green mode)
    if (m_carrierSleep && m_carriers.size() > 1)
    {
        const double primary = m_carriers[0].up ? m_carriers[0].rateBps : 0.0;
        bool anySleeping = false;
        for (size_t i = 1; i < m_carriers.size(); ++i)
        {
            anySleeping |= m_carriers[i].sleeping;
        }
        if (!anySleeping)
        {
            if (primary > 0.0 && offeredBps < m_sleepLoadFraction * primary)
            {
                if (++m_lowLoadIntervals >= 10)
                {
                    for (size_t i = 1; i < m_carriers.size(); ++i)
                    {
                        m_carriers[i].sleeping = true;
                    }
                    m_lowLoadIntervals = 0;
                }
            }
            else
            {
                m_lowLoadIntervals = 0;
            }
        }
        else if (primary <= 0.0 || offeredBps > 0.8 * primary)
        {
            for (size_t i = 1; i < m_carriers.size(); ++i)
            {
                m_carriers[i].sleeping = false;
            }
        }
    }

    double power = m_basePowerW;
    uint32_t active = 0;
    for (const auto& c : m_carriers)
    {
        if (c.enabled && !c.sleeping)
        {
            power += m_carrierPowerW + std::pow(10.0, c.txPowerDbm / 10.0) / 1000.0 / m_paEfficiency;
            active++;
        }
    }
    if (m_protection != CeragonProtectionMode::NONE && m_unitHealthy[1 - m_activeUnit])
    {
        power += 0.6 * m_carrierPowerW * active; // powered standby radio unit
    }
    m_powerW = power;
    m_powerTrace = power;

    SetLinkUp(total > 0.0);

    if (m_syncMode != CeragonSyncMode::NONE)
    {
        if (m_linkUp)
        {
            m_timeErrorNs = m_cteNs + m_dteSigmaNs * m_normal->GetValue();
        }
        else
        {
            m_timeErrorNs += m_holdoverDriftNsPerS * std::max(dt, 0.0);
        }
        m_timeErrorTrace = m_timeErrorNs;
    }
}

void
CeragonRadioNetDevice::SetLinkUp(bool up)
{
    if (up == m_linkUp)
    {
        return;
    }
    m_linkUp = up;
    NS_LOG_INFO("Node " << (m_node ? m_node->GetId() : 0) << " radio link "
                        << (up ? "UP" : "DOWN") << " at " << Simulator::Now().As(Time::S));
    m_linkStateTrace(up);
    m_linkChangeCallbacks();
    if (up)
    {
        StartNextTransmission();
    }
    else if (m_queue && m_txState == READY)
    {
        while (Ptr<Packet> p = m_queue->Dequeue())
        {
            m_phyTxDropTrace(p);
            m_drops++;
        }
    }
}

// ------------------------------------------------------------- tx / rx ----

uint32_t
CeragonRadioNetDevice::AirBytes(uint32_t size) const
{
    uint32_t air = size + m_l1OverheadBytes;
    if (m_macsec)
    {
        air += m_macsecOverheadBytes;
    }
    if (m_headerCompression && size > 64)
    {
        air -= std::min(m_headerCompressionSavedBytes, size - 64);
    }
    return air;
}

bool
CeragonRadioNetDevice::DrawCorruption(uint32_t airBytes)
{
    double sumRates = 0.0;
    for (const auto& c : m_carriers)
    {
        if (c.up)
        {
            sumRates += c.rateBps;
        }
    }
    if (sumRates <= 0.0)
    {
        return true;
    }
    double success = 1.0;
    for (const auto& c : m_carriers)
    {
        if (!c.up)
        {
            continue;
        }
        const int idx = c.acm.GetCurrentIndex();
        const double margin = c.sinrDb - c.acm.GetTable()[idx].requiredSnrDb;
        const double ber = CeragonAcm::BitErrorRate(margin);
        const auto bytes = static_cast<uint32_t>(std::ceil(airBytes * c.rateBps / sumRates));
        success *= 1.0 - CeragonAcm::PacketErrorRate(ber, bytes);
    }
    return m_uniform->GetValue() > success;
}

bool
CeragonRadioNetDevice::TransmitStart(Ptr<Packet> p)
{
    NS_LOG_FUNCTION(this << p);
    m_txState = BUSY;
    m_currentPkt = p;
    m_phyTxBeginTrace(p);
    const uint32_t air = AirBytes(p->GetSize());
    const Time txTime = GetCurrentDataRate().CalculateBytesTxTime(air);
    Simulator::Schedule(txTime, &CeragonRadioNetDevice::TransmitComplete, this);
    const bool corrupted = DrawCorruption(air);
    const bool ok = m_channel->TransmitStart(p, this, txTime, corrupted);
    if (!ok)
    {
        m_phyTxDropTrace(p);
    }
    m_txPackets++;
    m_txBytes += p->GetSize();
    return ok;
}

void
CeragonRadioNetDevice::TransmitComplete()
{
    NS_LOG_FUNCTION(this);
    NS_ASSERT(m_txState == BUSY);
    m_txState = READY;
    m_phyTxEndTrace(m_currentPkt);
    m_currentPkt = nullptr;
    StartNextTransmission();
}

void
CeragonRadioNetDevice::StartNextTransmission()
{
    if (m_txState != READY || !m_queue)
    {
        return;
    }
    Ptr<Packet> p = m_queue->Dequeue();
    while (p && (!m_linkUp || m_aggregateBps <= 0.0))
    {
        m_phyTxDropTrace(p);
        m_drops++;
        p = m_queue->Dequeue();
    }
    if (!p)
    {
        return;
    }
    m_snifferTrace(p);
    TransmitStart(p);
}

void
CeragonRadioNetDevice::Receive(Ptr<Packet> packet, bool corrupted)
{
    NS_LOG_FUNCTION(this << packet << corrupted);
    const bool unitAvailable =
        m_unitHealthy[m_activeUnit] && Simulator::Now() >= m_switchoverEnd;
    if (corrupted || !unitAvailable)
    {
        m_phyRxDropTrace(packet);
        m_corrupted++;
        return;
    }
    m_snifferTrace(packet);
    CeragonRadioHeader h;
    packet->RemoveHeader(h);
    m_rxPackets++;
    m_rxBytes += packet->GetSize();
    if (!m_promiscCallback.IsNull())
    {
        m_promiscCallback(this,
                          packet,
                          h.GetProtocol(),
                          GetRemote(),
                          GetAddress(),
                          NetDevice::PACKET_HOST);
    }
    m_macRxTrace(packet);
    if (!m_rxCallback.IsNull())
    {
        m_rxCallback(this, packet, h.GetProtocol(), GetRemote());
    }
}

// ------------------------------------------------------- NetDevice API ----

void
CeragonRadioNetDevice::SetIfIndex(const uint32_t index)
{
    m_ifIndex = index;
}

uint32_t
CeragonRadioNetDevice::GetIfIndex() const
{
    return m_ifIndex;
}

Ptr<Channel>
CeragonRadioNetDevice::GetChannel() const
{
    return m_channel;
}

void
CeragonRadioNetDevice::SetAddress(Address address)
{
    m_address = Mac48Address::ConvertFrom(address);
}

Address
CeragonRadioNetDevice::GetAddress() const
{
    return m_address;
}

bool
CeragonRadioNetDevice::SetMtu(const uint16_t mtu)
{
    m_mtu = mtu;
    return true;
}

uint16_t
CeragonRadioNetDevice::GetMtu() const
{
    return m_mtu;
}

bool
CeragonRadioNetDevice::IsLinkUp() const
{
    return m_linkUp;
}

void
CeragonRadioNetDevice::AddLinkChangeCallback(Callback<void> callback)
{
    m_linkChangeCallbacks.ConnectWithoutContext(callback);
}

bool
CeragonRadioNetDevice::IsBroadcast() const
{
    return true;
}

Address
CeragonRadioNetDevice::GetBroadcast() const
{
    return Mac48Address::GetBroadcast();
}

bool
CeragonRadioNetDevice::IsMulticast() const
{
    return true;
}

Address
CeragonRadioNetDevice::GetMulticast(Ipv4Address multicastGroup) const
{
    return Mac48Address("01:00:5e:00:00:00");
}

Address
CeragonRadioNetDevice::GetMulticast(Ipv6Address addr) const
{
    return Mac48Address("33:33:00:00:00:00");
}

bool
CeragonRadioNetDevice::IsPointToPoint() const
{
    return true;
}

bool
CeragonRadioNetDevice::IsBridge() const
{
    return false;
}

bool
CeragonRadioNetDevice::Send(Ptr<Packet> packet, const Address& dest, uint16_t protocolNumber)
{
    NS_LOG_FUNCTION(this << packet << dest << protocolNumber);
    m_bytesOfferedInterval += packet->GetSize();
    if (!m_linkUp)
    {
        m_macTxDropTrace(packet);
        m_drops++;
        return false;
    }
    CeragonRadioHeader h;
    h.SetProtocol(protocolNumber);
    uint8_t flags = 0;
    if (m_macsec)
    {
        flags |= CeragonRadioHeader::FLAG_MACSEC;
    }
    if (m_headerCompression)
    {
        flags |= CeragonRadioHeader::FLAG_COMPRESSED;
    }
    h.SetFlags(flags);
    packet->AddHeader(h);
    m_macTxTrace(packet);
    if (m_queue->Enqueue(packet))
    {
        if (m_txState == READY)
        {
            StartNextTransmission();
        }
        return true;
    }
    m_macTxDropTrace(packet);
    m_drops++;
    return false;
}

bool
CeragonRadioNetDevice::SendFrom(Ptr<Packet> packet,
                                const Address& source,
                                const Address& dest,
                                uint16_t protocolNumber)
{
    return false;
}

Ptr<Node>
CeragonRadioNetDevice::GetNode() const
{
    return m_node;
}

void
CeragonRadioNetDevice::SetNode(Ptr<Node> node)
{
    m_node = node;
}

bool
CeragonRadioNetDevice::NeedsArp() const
{
    return false;
}

void
CeragonRadioNetDevice::SetReceiveCallback(NetDevice::ReceiveCallback cb)
{
    m_rxCallback = cb;
}

void
CeragonRadioNetDevice::SetPromiscReceiveCallback(PromiscReceiveCallback cb)
{
    m_promiscCallback = cb;
}

bool
CeragonRadioNetDevice::SupportsSendFrom() const
{
    return false;
}

Address
CeragonRadioNetDevice::GetRemote() const
{
    if (m_channel)
    {
        Ptr<CeragonRadioNetDevice> peer = m_channel->GetPeer(this);
        if (peer)
        {
            return peer->GetAddress();
        }
    }
    return Mac48Address::GetBroadcast();
}

} // namespace ns3
