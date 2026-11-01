/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Multi-Band resilience twin: an IP-50EX (E-band + 18 GHz MW anchor, L1 bonded)
 * and an EH-8010FX (E-band only) hop of the same length cross the same storm.
 * Offered traffic: 2 Gbps per hop. The trace shows ACM downshifts, the E-band
 * outage, and how the Multi-Band hop keeps carrying traffic over the MW carrier.
 *
 *   ./ns3 run "ceragon-multiband-rain --distance=3000 --peakRain=120"
 */

#include "ns3/applications-module.h"
#include "ns3/ceragon-module.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"

#include <iomanip>
#include <iostream>

using namespace ns3;

struct Hop
{
    std::string name;
    Ptr<CeragonRadioNetDevice> dev;
    Ptr<PacketSink> sink;
    uint64_t lastRx{0};
};

static std::vector<Hop> g_hops;
static double g_interval = 0.25;

static void
Report(Ptr<CeragonWeatherModel> weather)
{
    std::cout << std::fixed << std::setprecision(2) << std::setw(6)
              << Simulator::Now().GetSeconds() << std::setw(8) << weather->GetRainRate();
    for (auto& h : g_hops)
    {
        const uint64_t rx = h.sink->GetTotalRx();
        const double mbps = (rx - h.lastRx) * 8.0 / g_interval / 1e6;
        h.lastRx = rx;
        std::string mods;
        for (uint32_t i = 0; i < h.dev->GetNCarriers(); ++i)
        {
            mods += (i ? "+" : "") + h.dev->GetCarrierModulation(i);
        }
        std::cout << " | " << std::setw(9) << h.dev->GetAggregateCapacityBps() / 1e6
                  << std::setw(9) << mbps << " " << std::left << std::setw(16) << mods
                  << std::right;
    }
    std::cout << "\n";
    Simulator::Schedule(Seconds(g_interval), &Report, weather);
}

int
main(int argc, char* argv[])
{
    double distance = 3000.0;
    double peakRain = 120.0;
    double simTime = 8.0;
    std::string offered = "2Gbps";

    CommandLine cmd(__FILE__);
    cmd.AddValue("distance", "Hop length (m)", distance);
    cmd.AddValue("peakRain", "Storm peak rain rate (mm/h)", peakRain);
    cmd.AddValue("simTime", "Simulation time (s)", simTime);
    cmd.AddValue("offered", "Offered UDP load per hop", offered);
    cmd.Parse(argc, argv);

    Ptr<CeragonWeatherModel> weather = CreateObject<CeragonWeatherModel>();
    weather->ScheduleRainEvent(Seconds(1.0), Seconds(simTime - 2.0), peakRain);
    CeragonHelper helper;
    helper.SetWeatherModel(weather);

    InternetStackHelper internet;
    Ipv4AddressHelper addr("10.10.0.0", "255.255.255.252");
    uint16_t port = 9000;
    for (const char* model : {"IP-50EX", "EH-8010FX"})
    {
        NodeContainer n;
        n.Create(2);
        internet.Install(n);
        CeragonLinkConfig cfg;
        cfg.modelA = model;
        cfg.distanceM = distance;
        NetDeviceContainer d = helper.Install(n.Get(0), n.Get(1), cfg);
        helper.InstallQos(d);
        Ipv4InterfaceContainer ifs = addr.Assign(d);
        addr.NewNetwork();

        PacketSinkHelper sink("ns3::UdpSocketFactory", InetSocketAddress(Ipv4Address::GetAny(), port));
        ApplicationContainer s = sink.Install(n.Get(1));
        OnOffHelper onoff("ns3::UdpSocketFactory", InetSocketAddress(ifs.GetAddress(1), port));
        onoff.SetConstantRate(DataRate(offered), 1400);
        ApplicationContainer a = onoff.Install(n.Get(0));
        a.Start(Seconds(0.5));
        g_hops.push_back({model, DynamicCast<CeragonRadioNetDevice>(d.Get(0)),
                          DynamicCast<PacketSink>(s.Get(0)), 0});
        ++port;
    }

    std::cout << "  time    rain";
    for (const auto& h : g_hops)
    {
        std::cout << " | " << std::left << std::setw(34) << (h.name + " cap/thr Mb/s, ACM")
                  << std::right;
    }
    std::cout << "\n";
    Simulator::Schedule(Seconds(g_interval), &Report, weather);
    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    std::cout << "\nOutage time: ";
    for (const auto& h : g_hops)
    {
        std::cout << h.name << "=" << h.dev->GetOutageTime().GetSeconds() << "s  ";
    }
    std::cout << "\n";
    Simulator::Destroy();
    return 0;
}
