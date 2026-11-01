/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef CERAGON_HELPER_H
#define CERAGON_HELPER_H

#include "ns3/ceragon-propagation.h"
#include "ns3/ceragon-radio-net-device.h"
#include "ns3/net-device-container.h"
#include "ns3/node-container.h"
#include "ns3/object-factory.h"
#include "ns3/queue-disc-container.h"

#include <string>

namespace ns3
{

/**
 * @ingroup ceragon
 * Per-link configuration. Zero / empty / -1 values mean "derive from the
 * product spec" (portfolio defaults).
 */
struct CeragonLinkConfig
{
    std::string modelA;          //!< product of end A (empty = helper default)
    std::string modelB;          //!< product of end B (empty = same as A)
    double frequencyMhz{0.0};    //!< centre frequency of carrier 0
    double bandwidthMhz{0.0};    //!< channel bandwidth
    uint32_t carriers{0};        //!< number of carriers
    int xpic{-1};                //!< -1 auto, 0 off, 1 on (H/V co-channel pair)
    int multiband{-1};           //!< -1 auto, 0 off, 1 on (E-band + MW)
    double distanceM{0.0};       //!< hop length (0 = mobility)
    double antennaDiameterM{0.0}; //!< parabolic antenna diameter (0 = default)
    std::string maxModulation;   //!< ACM ceiling
    std::string minModulation;   //!< ACM floor
    CeragonProtectionMode protection{CeragonProtectionMode::NONE};
    bool macsec{false};
    bool atpc{false};
    double atpcTargetRslDbm{-45.0};
    CeragonSyncMode sync{CeragonSyncMode::NONE};
    bool headerCompression{false};
    bool carrierSleep{false};
};

/**
 * @ingroup ceragon
 * Builds Ceragon radio hops whose RF front-end, carriers, ACM tables,
 * capacities and feature set are taken from the Ceragon portfolio catalog.
 */
class CeragonHelper
{
  public:
    CeragonHelper();

    /// Default product used for both ends of new links
    void SetProduct(const std::string& model);
    void SetDeviceAttribute(std::string name, const AttributeValue& value);
    void SetChannelAttribute(std::string name, const AttributeValue& value);
    /// Device transmit queue size (default 100p)
    void SetQueueSize(const std::string& size);
    /// Shared weather (rain) model applied to all channels created afterwards
    void SetWeatherModel(Ptr<CeragonWeatherModel> weather);
    Ptr<CeragonWeatherModel> GetWeatherModel() const;

    NetDeviceContainer Install(Ptr<Node> a, Ptr<Node> b);
    NetDeviceContainer Install(Ptr<Node> a, Ptr<Node> b, const CeragonLinkConfig& cfg);
    NetDeviceContainer Install(const NodeContainer& pair);

    /**
     * Configure carriers, RF front-end, energy and features of a device
     * from its product spec.
     * @param dev the device (product model already set)
     * @param cfg link configuration
     */
    static void ConfigureDevice(Ptr<CeragonRadioNetDevice> dev, const CeragonLinkConfig& cfg);

    /**
     * Install the CeragonQosQueueDisc (8 CoS, SP + DRR, shapers, 802.1Qbv) on
     * radio devices. The InternetStack must already be installed; an existing
     * root queue disc is replaced.
     * @param devices radio devices
     * @param strictQueues number of strict-priority CoS queues
     * @return the queue discs
     */
    QueueDiscContainer InstallQos(const NetDeviceContainer& devices, uint32_t strictQueues = 2);

    /// Assign RNG streams to devices and channels; @return streams used
    int64_t AssignStreams(const NetDeviceContainer& devices, int64_t stream);

  private:
    ObjectFactory m_deviceFactory;
    ObjectFactory m_channelFactory;
    std::string m_queueSize;
    std::string m_model;
    Ptr<CeragonWeatherModel> m_weather;
};

} // namespace ns3

#endif /* CERAGON_HELPER_H */
