/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Radio protection twin: three IP-20C hops (unprotected 1+0, 1+1 HSB and
 * 1+1 Space Diversity) carry the same 500 Mb/s UDP stream. At t = 2 s the
 * main radio unit of every hop fails; at t = 4 s it is repaired. The report
 * shows lost packets, outage time and switchover counts per scheme.
 *
 *   ./ns3 run "ceragon-protection-switchover --model=IP-20C"
 */

#include "ns3/applications-module.h"
#include "ns3/ceragon-module.h"
#include "ns3/core-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"

#include <iomanip>
#include <iostream>

using namespace ns3;

int
main(int argc, char* argv[])
{
    std::string model = "IP-20C";
    double simTime = 6.0;
    double fading = 2.0;

    CommandLine cmd(__FILE__);
    cmd.AddValue("model", "Ceragon product", model);
    cmd.AddValue("simTime", "Simulation time (s)", simTime);
    cmd.AddValue("fading", "Multipath fading std-dev (dB) - shows the SD diversity gain", fading);
    cmd.Parse(argc, argv);

    CeragonHelper helper;
    helper.SetChannelAttribute("FadingStdDb", DoubleValue(fading));
    InternetStackHelper internet;
    Ipv4AddressHelper addr("10.30.0.0", "255.255.255.252");

    const std::vector<std::pair<std::string, CeragonProtectionMode>> schemes{
        {"1+0", CeragonProtectionMode::NONE},
        {"1+1 HSB", CeragonProtectionMode::HSB_1PLUS1},
        {"1+1 SD", CeragonProtectionMode::SPACE_DIVERSITY}};
    std::vector<Ptr<CeragonRadioNetDevice>> devs;
    uint16_t port = 8000;
    for (const auto& [name, mode] : schemes)
    {
        NodeContainer n;
        n.Create(2);
        internet.Install(n);
        CeragonLinkConfig cfg;
        cfg.modelA = model;
        cfg.distanceM = 8000.0;
        cfg.protection = mode;
        NetDeviceContainer d = helper.Install(n.Get(0), n.Get(1), cfg);
        Ipv4InterfaceContainer ifs = addr.Assign(d);
        addr.NewNetwork();
        auto dev = DynamicCast<CeragonRadioNetDevice>(d.Get(0));
        devs.push_back(dev);

        PacketSinkHelper sink("ns3::UdpSocketFactory", InetSocketAddress(Ipv4Address::GetAny(), port));
        sink.Install(n.Get(1));
        OnOffHelper onoff("ns3::UdpSocketFactory", InetSocketAddress(ifs.GetAddress(1), port));
        onoff.SetConstantRate(DataRate("500Mbps"), 1400);
        onoff.Install(n.Get(0)).Start(Seconds(0.5));
        ++port;

        Simulator::Schedule(Seconds(2.0), &CeragonRadioNetDevice::FailRadioUnit, dev, 0U);
        Simulator::Schedule(Seconds(4.0), &CeragonRadioNetDevice::RestoreRadioUnit, dev, 0U);
    }

    FlowMonitorHelper fmh;
    Ptr<FlowMonitor> mon = fmh.InstallAll();
    Simulator::Stop(Seconds(simTime));
    Simulator::Run();
    mon->CheckForLostPackets();
    auto cls = DynamicCast<Ipv4FlowClassifier>(fmh.GetClassifier());

    std::cout << std::fixed << std::setprecision(3) << "\nProtection twin (" << model
              << ", 8 km, main radio unit fails at 2 s, repaired at 4 s)\n";
    for (const auto& [id, s] : mon->GetFlowStats())
    {
        const auto t = cls->FindFlow(id);
        if (t.destinationPort < 8000 || t.destinationPort > 8002)
        {
            continue;
        }
        const uint32_t i = t.destinationPort - 8000;
        std::cout << "  " << std::left << std::setw(9) << schemes[i].first << std::right
                  << " lost=" << std::setw(7) << (s.txPackets - s.rxPackets)
                  << " pkts  outage=" << devs[i]->GetOutageTime().GetSeconds()
                  << " s  switchovers=" << devs[i]->GetProtectionSwitchCount()
                  << "  active unit=" << devs[i]->GetActiveRadioUnit()
                  << "  ACM changes=" << devs[i]->GetModulationChangeCount() << "\n";
    }
    Simulator::Destroy();
    return 0;
}
