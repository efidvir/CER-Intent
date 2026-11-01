/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#include "ceragon-radio-channel.h"

#include "ceragon-radio-net-device.h"

#include "ns3/boolean.h"
#include "ns3/double.h"
#include "ns3/log.h"
#include "ns3/mobility-model.h"
#include "ns3/node.h"
#include "ns3/pointer.h"
#include "ns3/simulator.h"

#include <cmath>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("CeragonRadioChannel");
NS_OBJECT_ENSURE_REGISTERED(CeragonRadioChannel);

TypeId
CeragonRadioChannel::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::CeragonRadioChannel")
            .SetParent<Channel>()
            .SetGroupName("Ceragon")
            .AddConstructor<CeragonRadioChannel>()
            .AddAttribute("Distance",
                          "Hop length in metres (0 = derive from the nodes' mobility models)",
                          DoubleValue(0.0),
                          MakeDoubleAccessor(&CeragonRadioChannel::m_distanceM),
                          MakeDoubleChecker<double>(0.0))
            .AddAttribute("InterferenceDbm",
                          "External co-channel interference power at the receiver (dBm)",
                          DoubleValue(-200.0),
                          MakeDoubleAccessor(&CeragonRadioChannel::m_interferenceDbm),
                          MakeDoubleChecker<double>())
            .AddAttribute("FadingStdDb",
                          "Standard deviation of multipath/scintillation fading (dB)",
                          DoubleValue(0.3),
                          MakeDoubleAccessor(&CeragonRadioChannel::m_fadingStdDb),
                          MakeDoubleChecker<double>(0.0))
            .AddAttribute("MiscLossDb",
                          "Fixed losses: radome, branching, connectors (dB)",
                          DoubleValue(1.0),
                          MakeDoubleAccessor(&CeragonRadioChannel::m_miscLossDb),
                          MakeDoubleChecker<double>(0.0))
            .AddAttribute("UsePathReduction",
                          "Apply ITU-R P.530 rain-cell path reduction on long hops",
                          BooleanValue(true),
                          MakeBooleanAccessor(&CeragonRadioChannel::m_usePathReduction),
                          MakeBooleanChecker())
            .AddAttribute("WeatherModel",
                          "Shared regional weather model",
                          PointerValue(),
                          MakePointerAccessor(&CeragonRadioChannel::m_weather),
                          MakePointerChecker<CeragonWeatherModel>());
    return tid;
}

CeragonRadioChannel::CeragonRadioChannel()
    : m_nDevices(0),
      m_distanceM(0.0),
      m_interferenceDbm(-200.0),
      m_fadingStdDb(0.3),
      m_miscLossDb(1.0),
      m_usePathReduction(true)
{
    NS_LOG_FUNCTION(this);
    m_fading = CreateObject<NormalRandomVariable>();
}

CeragonRadioChannel::~CeragonRadioChannel() = default;

void
CeragonRadioChannel::DoDispose()
{
    m_dev[0] = nullptr;
    m_dev[1] = nullptr;
    m_weather = nullptr;
    m_fading = nullptr;
    Channel::DoDispose();
}

void
CeragonRadioChannel::Attach(Ptr<CeragonRadioNetDevice> device)
{
    NS_LOG_FUNCTION(this << device);
    NS_ASSERT_MSG(m_nDevices < 2, "CeragonRadioChannel supports exactly two radios");
    m_dev[m_nDevices++] = device;
}

bool
CeragonRadioChannel::TransmitStart(Ptr<const Packet> p,
                                   Ptr<CeragonRadioNetDevice> src,
                                   Time txTime,
                                   bool corrupted)
{
    NS_LOG_FUNCTION(this << p << src << txTime << corrupted);
    Ptr<CeragonRadioNetDevice> dst = GetPeer(src);
    if (!dst)
    {
        return false;
    }
    const Time delay = GetPropagationDelay() + src->GetRadioLatency();
    Simulator::ScheduleWithContext(dst->GetNode()->GetId(),
                                   txTime + delay,
                                   &CeragonRadioNetDevice::Receive,
                                   dst,
                                   p->Copy(),
                                   corrupted);
    return true;
}

std::size_t
CeragonRadioChannel::GetNDevices() const
{
    return m_nDevices;
}

Ptr<NetDevice>
CeragonRadioChannel::GetDevice(std::size_t i) const
{
    NS_ASSERT(i < m_nDevices);
    return m_dev[i];
}

Ptr<CeragonRadioNetDevice>
CeragonRadioChannel::GetPeer(Ptr<const CeragonRadioNetDevice> device) const
{
    if (m_nDevices < 2)
    {
        return nullptr;
    }
    return (PeekPointer(m_dev[0]) == PeekPointer(device)) ? m_dev[1] : m_dev[0];
}

double
CeragonRadioChannel::GetDistanceKm() const
{
    if (m_distanceM > 0.0)
    {
        return m_distanceM / 1000.0;
    }
    if (m_nDevices == 2)
    {
        Ptr<MobilityModel> a = m_dev[0]->GetNode()->GetObject<MobilityModel>();
        Ptr<MobilityModel> b = m_dev[1]->GetNode()->GetObject<MobilityModel>();
        if (a && b)
        {
            return std::max(1.0, a->GetDistanceFrom(b)) / 1000.0;
        }
    }
    return 1.0; // default 1 km hop
}

void
CeragonRadioChannel::SetDistance(double meters)
{
    m_distanceM = meters;
}

Time
CeragonRadioChannel::GetPropagationDelay() const
{
    return Seconds(GetDistanceKm() * 1000.0 / 299792458.0);
}

double
CeragonRadioChannel::GetRainRate() const
{
    return m_weather ? m_weather->GetRainRate() : 0.0;
}

double
CeragonRadioChannel::GetRainAttenuationDb(double freqGhz, bool verticalPol) const
{
    return CeragonItuPropagation::RainAttenuationDb(freqGhz,
                                                    GetDistanceKm(),
                                                    GetRainRate(),
                                                    verticalPol,
                                                    m_usePathReduction);
}

double
CeragonRadioChannel::GetGaseousAttenuationDb(double freqGhz) const
{
    return CeragonItuPropagation::GaseousSpecificAttenuationDbPerKm(freqGhz) * GetDistanceKm();
}

double
CeragonRadioChannel::GetPathLossDb(double freqGhz, bool verticalPol) const
{
    const double d = GetDistanceKm();
    return CeragonItuPropagation::FreeSpaceLossDb(freqGhz, d) + GetGaseousAttenuationDb(freqGhz) +
           GetRainAttenuationDb(freqGhz, verticalPol) + m_miscLossDb;
}

void
CeragonRadioChannel::SetWeatherModel(Ptr<CeragonWeatherModel> weather)
{
    m_weather = weather;
}

Ptr<CeragonWeatherModel>
CeragonRadioChannel::GetWeatherModel() const
{
    return m_weather;
}

void
CeragonRadioChannel::SetInterferenceDbm(double dbm)
{
    m_interferenceDbm = dbm;
}

double
CeragonRadioChannel::GetInterferenceDbm() const
{
    return m_interferenceDbm;
}

double
CeragonRadioChannel::SampleFadingDb()
{
    if (m_fadingStdDb <= 0.0)
    {
        return 0.0;
    }
    m_fading->SetAttribute("Mean", DoubleValue(0.0));
    m_fading->SetAttribute("Variance", DoubleValue(m_fadingStdDb * m_fadingStdDb));
    return m_fading->GetValue();
}

int64_t
CeragonRadioChannel::AssignStreams(int64_t stream)
{
    m_fading->SetStream(stream);
    return 1;
}

} // namespace ns3
