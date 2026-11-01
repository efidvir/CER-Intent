/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * TSN / O-RAN fronthaul twin over a Ceragon IP-50FX hop.
 *
 * An O-RAN Split 7.2x eCPRI flow (EF, CoS 7, express) shares a 112 MHz XPIC
 * hop with bursty best-effort traffic that oversubscribes the radio. Three
 * configurations are compared:
 *   fifo  : no Ceragon QoS (single FIFO)              -> fronthaul delay explodes
 *   qos   : Ceragon 8-CoS strict priority + DRR        -> bounded delay
 *   tsn   : QoS + IEEE 802.1Qbv GCL (express window)   -> deterministic window
 *
 *   ./ns3 run "ceragon-tsn-fronthaul --mode=tsn"
 */

#include "ns3/applications-module.h"
#include "ns3/ceragon-module.h"
#include "ns3/core-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"
#include "ns3/traffic-control-module.h"

#include <iomanip>
#include <iostream>

using namespace ns3;

int
main(int argc, char* argv[])
{
    std::string mode = "tsn";
    std::string model = "IP-50FX";
    double simTime = 3.0;
    double cycleUs = 500.0;
    double expressUs = 100.0;
    uint32_t layers = 2;
    uint32_t nrBandwidthMhz = 20;
    std::string beLoad = "2500Mbps";

    CommandLine cmd(__FILE__);
    cmd.AddValue("mode", "fifo | qos | tsn", mode);
    cmd.AddValue("model", "Ceragon product of the hop", model);
    cmd.AddValue("simTime", "Simulation time (s)", simTime);
    cmd.AddValue("cycleUs", "802.1Qbv cycle time (us)", cycleUs);
    cmd.AddValue("expressUs", "Express (fronthaul) window per cycle (us)", expressUs);
    cmd.AddValue("layers", "O-RAN eAxC layers", layers);
    cmd.AddValue("nrBandwidth", "NR carrier bandwidth (MHz)", nrBandwidthMhz);
    cmd.AddValue("beLoad", "Best-effort offered load", beLoad);
    cmd.Parse(argc, argv);

    const double fhRate = CeragonOranXhaul::EcpriBitRate(nrBandwidthMhz, 1, layers, "bfp-9bit");
    const double budgetUs = CeragonOranXhaul::DelayBudgetUs("high-100us");

    NodeContainer n;
    n.Create(2);
    CeragonHelper helper;
    CeragonLinkConfig cfg;
    cfg.modelA = model;
    cfg.distanceM = 3000.0;
    cfg.sync = CeragonSyncMode::PTP_BOUNDARY_CLOCK;
    NetDeviceContainer d = helper.Install(n.Get(0), n.Get(1), cfg);
    InternetStackHelper internet;
    internet.Install(n);

    Ptr<CeragonQosQueueDisc> qd;
    if (mode == "fifo")
    {
        TrafficControlHelper tch;
        tch.SetRootQueueDisc("ns3::FifoQueueDisc", "MaxSize", StringValue("2000p"));
        tch.Install(d);
        DynamicCast<CeragonRadioNetDevice>(d.Get(0))->GetQueue()->SetMaxSize(QueueSize("4p"));
    }
    else
    {
        QueueDiscContainer q = helper.InstallQos(d, 2);
        qd = DynamicCast<CeragonQosQueueDisc>(q.Get(0));
        if (mode == "tsn")
        {
            // Protected window: only CoS 7 during the express window, all gates
            // (incl. CoS 7) open afterwards; guard band + 802.1Qbu preemption keep
            // best-effort frames from overrunning the window start.
            qd->SetAttribute("FramePreemption", BooleanValue(true));
            qd->SetExpressQueues(0x80);
            qd->AddGateControlEntry(MicroSeconds(expressUs), 0x80);
            qd->AddGateControlEntry(MicroSeconds(cycleUs - expressUs), 0xFF);
        }
    }
    Ipv4AddressHelper addr("10.20.0.0", "255.255.255.252");
    Ipv4InterfaceContainer ifs = addr.Assign(d);

    // Fronthaul (eCPRI-like CBR, EF) and best-effort bursts (AF11 + BE)
    PacketSinkHelper sink("ns3::UdpSocketFactory", InetSocketAddress(Ipv4Address::GetAny(), 7000));
    sink.Install(n.Get(1));
    PacketSinkHelper sink2("ns3::UdpSocketFactory", InetSocketAddress(Ipv4Address::GetAny(), 7001));
    sink2.Install(n.Get(1));

    OnOffHelper fh("ns3::UdpSocketFactory", InetSocketAddress(ifs.GetAddress(1), 7000));
    fh.SetConstantRate(DataRate(static_cast<uint64_t>(fhRate)), 1200);
    fh.SetAttribute("Tos", UintegerValue(46 << 2));
    fh.Install(n.Get(0)).Start(Seconds(0.5));

    OnOffHelper be("ns3::UdpSocketFactory", InetSocketAddress(ifs.GetAddress(1), 7001));
    be.SetAttribute("DataRate", DataRateValue(DataRate(beLoad)));
    be.SetAttribute("PacketSize", UintegerValue(1472));
    be.SetAttribute("OnTime", StringValue("ns3::ExponentialRandomVariable[Mean=0.02]"));
    be.SetAttribute("OffTime", StringValue("ns3::ExponentialRandomVariable[Mean=0.01]"));
    be.Install(n.Get(0)).Start(Seconds(0.5));

    FlowMonitorHelper fmh;
    Ptr<FlowMonitor> mon = fmh.InstallAll();
    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    mon->CheckForLostPackets();
    auto cls = DynamicCast<Ipv4FlowClassifier>(fmh.GetClassifier());
    auto dev = DynamicCast<CeragonRadioNetDevice>(d.Get(0));
    std::cout << std::fixed << std::setprecision(3);
    std::cout << "\nMode=" << mode << "  hop=" << model << "  radio capacity="
              << dev->GetAggregateCapacityBps() / 1e6 << " Mb/s"
              << "  fronthaul=" << fhRate / 1e6 << " Mb/s  budget=" << budgetUs << " us"
              << "  PTP TE=" << dev->GetTimeErrorNs() << " ns\n";
    for (const auto& [id, s] : mon->GetFlowStats())
    {
        const auto t = cls->FindFlow(id);
        if (t.destinationPort != 7000 && t.destinationPort != 7001)
        {
            continue;
        }
        const double delayUs = s.rxPackets ? s.delaySum.GetMicroSeconds() / double(s.rxPackets) : 0;
        const double loss = s.txPackets ? 100.0 * (s.txPackets - s.rxPackets) / s.txPackets : 0;
        const std::string name = (t.destinationPort == 7000) ? "fronthaul(EF)" : "best-effort";
        std::cout << "  " << std::left << std::setw(15) << name << std::right
                  << " thr=" << std::setw(9) << s.rxBytes * 8.0 / (simTime - 0.5) / 1e6
                  << " Mb/s  mean delay=" << std::setw(9) << delayUs
                  << " us  loss=" << loss << " %";
        if (t.destinationPort == 7000)
        {
            std::cout << (delayUs <= budgetUs ? "  [within O-RAN budget]" : "  [BUDGET VIOLATED]");
        }
        std::cout << "\n";
    }
    if (qd)
    {
        std::cout << "  CoS7 dequeued=" << qd->GetDequeuedPackets(7)
                  << "  gate-blocked events=" << qd->GetGateBlockedEvents() << "\n";
    }
    Simulator::Destroy();
    return 0;
}
