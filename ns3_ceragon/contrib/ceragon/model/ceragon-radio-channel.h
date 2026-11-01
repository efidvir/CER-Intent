/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef CERAGON_RADIO_CHANNEL_H
#define CERAGON_RADIO_CHANNEL_H

#include "ceragon-propagation.h"

#include "ns3/channel.h"
#include "ns3/nstime.h"
#include "ns3/packet.h"
#include "ns3/ptr.h"
#include "ns3/random-variable-stream.h"

namespace ns3
{

class CeragonRadioNetDevice;

/**
 * @ingroup ceragon
 * Point-to-point radio hop between two Ceragon radios.
 *
 * The channel owns the hop geometry (distance from the mobility models or the
 * "Distance" attribute), the propagation impairments (free space, gaseous,
 * rain from a shared CeragonWeatherModel, multipath fading, external
 * interference) and the frame delivery (propagation delay).
 */
class CeragonRadioChannel : public Channel
{
  public:
    static TypeId GetTypeId();
    CeragonRadioChannel();
    ~CeragonRadioChannel() override;

    /// Attach a device (max 2)
    void Attach(Ptr<CeragonRadioNetDevice> device);
    /**
     * Start the transmission of a frame.
     * @param p the frame
     * @param src the transmitting device
     * @param txTime the serialization time
     * @param corrupted true if the frame will be received in error
     * @return true on success
     */
    bool TransmitStart(Ptr<const Packet> p,
                       Ptr<CeragonRadioNetDevice> src,
                       Time txTime,
                       bool corrupted);

    std::size_t GetNDevices() const override;
    Ptr<NetDevice> GetDevice(std::size_t i) const override;
    /// @return the device at the other end of the hop
    Ptr<CeragonRadioNetDevice> GetPeer(Ptr<const CeragonRadioNetDevice> device) const;

    /// Hop length (km)
    double GetDistanceKm() const;
    /// Set hop length (m); 0 = use mobility models
    void SetDistance(double meters);
    /// One-way propagation delay
    Time GetPropagationDelay() const;
    /// Total path loss incl. gaseous and rain attenuation (dB)
    double GetPathLossDb(double freqGhz, bool verticalPol) const;
    /// Rain attenuation only (dB)
    double GetRainAttenuationDb(double freqGhz, bool verticalPol) const;
    /// Gaseous attenuation only (dB)
    double GetGaseousAttenuationDb(double freqGhz) const;
    /// Current rain rate seen by the hop (mm/h)
    double GetRainRate() const;

    void SetWeatherModel(Ptr<CeragonWeatherModel> weather);
    Ptr<CeragonWeatherModel> GetWeatherModel() const;

    /// External co-channel interference power at the receiver (dBm)
    void SetInterferenceDbm(double dbm);
    double GetInterferenceDbm() const;

    /// Draw a multipath / scintillation fading sample (dB)
    double SampleFadingDb();

    /// Assign RNG streams; @return number of streams used
    int64_t AssignStreams(int64_t stream);

  protected:
    void DoDispose() override;

  private:
    Ptr<CeragonRadioNetDevice> m_dev[2];
    std::size_t m_nDevices;
    double m_distanceM;
    double m_interferenceDbm;
    double m_fadingStdDb;
    double m_miscLossDb;
    bool m_usePathReduction;
    Ptr<CeragonWeatherModel> m_weather;
    Ptr<NormalRandomVariable> m_fading;
};

} // namespace ns3

#endif /* CERAGON_RADIO_CHANNEL_H */
