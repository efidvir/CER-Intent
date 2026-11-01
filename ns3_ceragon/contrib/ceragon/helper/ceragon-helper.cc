/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#include "ceragon-helper.h"

#include "ns3/ceragon-qos-queue-disc.h"
#include "ns3/ceragon-radio-channel.h"
#include "ns3/double.h"
#include "ns3/drop-tail-queue.h"
#include "ns3/log.h"
#include "ns3/mac48-address.h"
#include "ns3/net-device-queue-interface.h"
#include "ns3/node.h"
#include "ns3/traffic-control-helper.h"
#include "ns3/traffic-control-layer.h"
#include "ns3/uinteger.h"

#include <algorithm>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("CeragonHelper");

CeragonHelper::CeragonHelper()
    : m_queueSize("100p"),
      m_model("IP-20C")
{
    m_deviceFactory.SetTypeId("ns3::CeragonRadioNetDevice");
    m_channelFactory.SetTypeId("ns3::CeragonRadioChannel");
}

void
CeragonHelper::SetProduct(const std::string& model)
{
    m_model = model;
}

void
CeragonHelper::SetDeviceAttribute(std::string name, const AttributeValue& value)
{
    m_deviceFactory.Set(name, value);
}

void
CeragonHelper::SetChannelAttribute(std::string name, const AttributeValue& value)
{
    m_channelFactory.Set(name, value);
}

void
CeragonHelper::SetQueueSize(const std::string& size)
{
    m_queueSize = size;
}

void
CeragonHelper::SetWeatherModel(Ptr<CeragonWeatherModel> weather)
{
    m_weather = weather;
}

Ptr<CeragonWeatherModel>
CeragonHelper::GetWeatherModel() const
{
    return m_weather;
}

NetDeviceContainer
CeragonHelper::Install(Ptr<Node> a, Ptr<Node> b)
{
    return Install(a, b, CeragonLinkConfig());
}

NetDeviceContainer
CeragonHelper::Install(const NodeContainer& pair)
{
    NS_ASSERT_MSG(pair.GetN() == 2, "CeragonHelper::Install needs exactly two nodes");
    return Install(pair.Get(0), pair.Get(1));
}

NetDeviceContainer
CeragonHelper::Install(Ptr<Node> a, Ptr<Node> b, const CeragonLinkConfig& cfg)
{
    const std::string modelA = cfg.modelA.empty() ? m_model : cfg.modelA;
    const std::string modelB = cfg.modelB.empty() ? modelA : cfg.modelB;

    Ptr<CeragonRadioChannel> channel = m_channelFactory.Create<CeragonRadioChannel>();
    if (m_weather)
    {
        channel->SetWeatherModel(m_weather);
    }
    if (cfg.distanceM > 0.0)
    {
        channel->SetDistance(cfg.distanceM);
    }

    NetDeviceContainer devices;
    const std::pair<Ptr<Node>, std::string> ends[2] = {{a, modelA}, {b, modelB}};
    for (const auto& [node, model] : ends)
    {
        Ptr<CeragonRadioNetDevice> dev = m_deviceFactory.Create<CeragonRadioNetDevice>();
        dev->SetAddress(Mac48Address::Allocate());
        dev->SetProductModel(model);
        Ptr<Queue<Packet>> queue = CreateObject<DropTailQueue<Packet>>();
        queue->SetMaxSize(QueueSize(m_queueSize));
        dev->SetQueue(queue);
        node->AddDevice(dev);
        ConfigureDevice(dev, cfg);
        dev->Attach(channel);

        Ptr<NetDeviceQueueInterface> ndqi = CreateObject<NetDeviceQueueInterface>();
        ndqi->GetTxQueue(0)->ConnectQueueTraces(queue);
        dev->AggregateObject(ndqi);
        devices.Add(dev);
    }
    return devices;
}

void
CeragonHelper::ConfigureDevice(Ptr<CeragonRadioNetDevice> dev, const CeragonLinkConfig& cfg)
{
    const CeragonProductSpec* spec = dev->GetSpec();
    dev->ClearCarriers();
    if (!spec)
    {
        NS_LOG_WARN("Unknown product '" << dev->GetProductModel()
                                        << "': generic 23 GHz / 56 MHz microwave radio");
        dev->AddCarrier(cfg.frequencyMhz > 0 ? cfg.frequencyMhz : 23000.0,
                        cfg.bandwidthMhz > 0 ? cfg.bandwidthMhz : 56.0,
                        false,
                        cfg.maxModulation.empty() ? "4096QAM" : cfg.maxModulation,
                        cfg.minModulation.empty() ? "QPSK" : cfg.minModulation);
        return;
    }

    const bool tg = (spec->flavor == CeragonApiFlavor::SIKLU_TG);
    const std::string& band = spec->PrimaryBand().name;
    dev->SetUseMcsTable(tg);

    const double freq = cfg.frequencyMhz > 0.0 ? cfg.frequencyMhz : spec->DefaultFrequencyMhz();
    const double bw = cfg.bandwidthMhz > 0.0 ? cfg.bandwidthMhz : spec->MaxChannelBandwidthMhz();
    const double fGhz = freq / 1000.0;

    // ---- RF front-end per band / product line ---------------------------
    double maxTx = 24.0;
    double nf = 6.0;
    double diameter = 0.3;
    double basePower = 25.0;
    double carrierPower = 12.0;
    Time latency = MicroSeconds(50);
    if (band == "V-band")
    {
        nf = 9.0;
        carrierPower = 5.0;
        latency = MicroSeconds(tg ? 150 : 20);
        if (tg)
        {
            const bool dn = spec->topology == "mesh";
            maxTx = 15.0;
            // Phased arrays: DN sector ~28 dBi / 2.8 deg, CN ~25 dBi / 5 deg
            dev->SetBeamforming(true, dn ? 28.0 : 25.0, dn ? 2.8 : 5.0);
            basePower = (spec->radioCarriers > 1) ? 35.0 : 12.0;
        }
        else
        {
            maxTx = 5.0;
            diameter = 0.2;
            basePower = 18.0;
        }
    }
    else if (band == "E-band")
    {
        nf = 8.0;
        maxTx = (spec->family == "IP-100") ? 18.0 : 17.0;
        carrierPower = 15.0;
        latency = MicroSeconds(10);
        basePower = (spec->family == "IP-100") ? 45.0 : 30.0;
    }
    else if (band == "MW-LH")
    {
        nf = 4.5;
        maxTx = 30.0;
        diameter = 1.8;
        latency = MicroSeconds(80);
        basePower = 40.0;
    }
    else // MW short haul
    {
        maxTx = (spec->model.find("-HP") != std::string::npos) ? 30.0 : 24.0;
        latency = MicroSeconds(bw >= 112.0 ? 40 : 80);
        basePower = (spec->family == "IP-50") ? 30.0 : 25.0;
    }
    if (spec->family == "EtherHaul")
    {
        basePower = 30.0;
        latency = MicroSeconds(15);
    }
    if (cfg.antennaDiameterM > 0.0)
    {
        diameter = cfg.antennaDiameterM;
    }
    if (!dev->IsBeamformingEnabled())
    {
        dev->SetAntennaGainDbi(CeragonItuPropagation::ParabolicAntennaGainDbi(diameter, fGhz));
    }
    dev->SetNoiseFigureDb(nf);
    dev->SetTxPowerLimits(maxTx - 30.0, maxTx);
    dev->SetAttribute("RadioLatency", TimeValue(latency));
    dev->SetAttribute("BasePower", DoubleValue(basePower));
    dev->SetAttribute("CarrierPower", DoubleValue(carrierPower));

    // ---- carriers -------------------------------------------------------
    const std::string maxMod =
        !cfg.maxModulation.empty() ? cfg.maxModulation : (tg ? "MCS12" : spec->maxModulation);
    const std::string minMod =
        !cfg.minModulation.empty()
            ? cfg.minModulation
            : (tg ? "MCS1" : (spec->flavor == CeragonApiFlavor::SIKLU_EH ? "BPSK" : "QPSK"));

    bool hasE = false;
    bool hasMw = false;
    for (const auto& b : spec->bands)
    {
        hasE |= (b.name == "E-band");
        hasMw |= (b.name == "MW");
    }
    std::string reason;
    bool multiband = (cfg.multiband == 1) || (cfg.multiband == -1 && hasE && hasMw);
    if (multiband && !CeragonPortfolio::CheckConfigSupport(spec, "multiband", reason))
    {
        NS_LOG_WARN(reason);
        multiband = false;
    }

    uint32_t n;
    if (tg || spec->topology == "mesh" || spec->topology == "ptmp")
    {
        n = 1;
    }
    else if (cfg.carriers > 0)
    {
        n = std::min(cfg.carriers, std::max<uint32_t>(spec->radioCarriers, 1));
    }
    else
    {
        n = std::min<uint32_t>(spec->radioCarriers, 2);
    }

    if (multiband)
    {
        if (band == "E-band")
        {
            dev->AddCarrier(freq, bw, false, maxMod, minMod);
            dev->AddCarrier(18000.0, 112.0, false, "4096QAM", "QPSK"); // MW anchor carrier
        }
        else
        {
            dev->AddCarrier(freq, bw, false, maxMod, minMod);
            dev->AddCarrier(73500.0, 1000.0, false, "256QAM", "QPSK"); // E-band boost
        }
    }
    else
    {
        bool xpic = (cfg.xpic == 1) || (cfg.xpic == -1 && spec->Supports(CeragonFeature::XPIC));
        if (xpic && !spec->Supports(CeragonFeature::XPIC))
        {
            NS_LOG_WARN(spec->model << " does not support XPIC; using adjacent channels");
            xpic = false;
        }
        for (uint32_t i = 0; i < n; ++i)
        {
            if (xpic && n >= 2)
            {
                // H/V co-channel pairs on consecutive channels
                const double f = freq + static_cast<double>(i / 2) * bw;
                dev->AddCarrier(f, bw, (i % 2) == 1, maxMod, minMod);
            }
            else
            {
                dev->AddCarrier(freq + static_cast<double>(i) * bw, bw, false, maxMod, minMod);
            }
        }
    }

    // ---- features (gated by the portfolio, exactly like the TFS adapter) ----
    if (cfg.protection != CeragonProtectionMode::NONE)
    {
        if (CeragonPortfolio::CheckConfigSupport(spec, "protection", reason))
        {
            CeragonProtectionMode mode = cfg.protection;
            if (tg && mode != CeragonProtectionMode::NONE)
            {
                mode = CeragonProtectionMode::ACTIVE_BACKUP; // radio-bridge-tg-bond
            }
            dev->SetProtectionMode(mode);
        }
        else
        {
            NS_LOG_WARN(reason);
        }
    }
    if (cfg.macsec)
    {
        if (CeragonPortfolio::CheckConfigSupport(spec, "security", reason))
        {
            dev->SetMacsec(true, "gcm-aes-256");
        }
        else
        {
            NS_LOG_WARN(reason);
        }
    }
    if (cfg.atpc)
    {
        dev->SetAtpc(true, cfg.atpcTargetRslDbm);
    }
    if (cfg.sync != CeragonSyncMode::NONE)
    {
        if (CeragonPortfolio::CheckConfigSupport(spec, "sync", reason))
        {
            dev->SetSyncMode(cfg.sync);
        }
        else
        {
            NS_LOG_WARN(reason);
        }
    }
    dev->SetHeaderCompression(cfg.headerCompression);
    if (cfg.carrierSleep)
    {
        if (CeragonPortfolio::CheckConfigSupport(spec, "energy", reason))
        {
            dev->SetCarrierSleep(true, 0.3);
        }
        else
        {
            NS_LOG_WARN(reason);
        }
    }
}

QueueDiscContainer
CeragonHelper::InstallQos(const NetDeviceContainer& devices, uint32_t strictQueues)
{
    QueueDiscContainer qdiscs;
    TrafficControlHelper tch;
    tch.SetRootQueueDisc("ns3::CeragonQosQueueDisc",
                         "StrictPriorityQueues",
                         UintegerValue(strictQueues));
    for (uint32_t i = 0; i < devices.GetN(); ++i)
    {
        Ptr<NetDevice> nd = devices.Get(i);
        Ptr<TrafficControlLayer> tc = nd->GetNode()->GetObject<TrafficControlLayer>();
        NS_ASSERT_MSG(tc, "Install the InternetStack before CeragonHelper::InstallQos");
        if (tc->GetRootQueueDiscOnDevice(nd))
        {
            tc->DeleteRootQueueDiscOnDevice(nd);
        }
        QueueDiscContainer q = tch.Install(nd);
        Ptr<CeragonQosQueueDisc> qd = DynamicCast<CeragonQosQueueDisc>(q.Get(0));
        Ptr<CeragonRadioNetDevice> dev = DynamicCast<CeragonRadioNetDevice>(nd);
        if (dev)
        {
            qd->SetDevice(dev);
            // Small device FIFO so that scheduling happens in the CoS queues
            dev->GetQueue()->SetMaxSize(QueueSize("4p"));
        }
        qdiscs.Add(q);
    }
    return qdiscs;
}

int64_t
CeragonHelper::AssignStreams(const NetDeviceContainer& devices, int64_t stream)
{
    int64_t current = stream;
    for (uint32_t i = 0; i < devices.GetN(); ++i)
    {
        Ptr<CeragonRadioNetDevice> dev = DynamicCast<CeragonRadioNetDevice>(devices.Get(i));
        if (!dev)
        {
            continue;
        }
        current += dev->AssignStreams(current);
        Ptr<CeragonRadioChannel> ch = DynamicCast<CeragonRadioChannel>(dev->GetChannel());
        if (ch && i % 2 == 0)
        {
            current += ch->AssignStreams(current);
        }
    }
    return current - stream;
}

} // namespace ns3
