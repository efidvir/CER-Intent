/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Unit and system tests for the Ceragon functional-twin module.
 */
#include "ns3/applications-module.h"
#include "ns3/ceragon-acm.h"
#include "ns3/ceragon-helper.h"
#include "ns3/ceragon-oran-xhaul.h"
#include "ns3/ceragon-portfolio.h"
#include "ns3/ceragon-propagation.h"
#include "ns3/ceragon-qos-queue-disc.h"
#include "ns3/ceragon-radio-net-device.h"
#include "ns3/ceragon-twin-helper.h"
#include "ns3/core-module.h"
#include "ns3/internet-module.h"
#include "ns3/network-module.h"
#include "ns3/test.h"

using namespace ns3;

namespace
{

/// Build a two-node Ceragon hop
NetDeviceContainer
MakeHop(NodeContainer& nodes,
        const std::string& modelA,
        const std::string& modelB,
        double distanceM,
        CeragonLinkConfig cfg = CeragonLinkConfig(),
        Ptr<CeragonWeatherModel> weather = nullptr)
{
    nodes.Create(2);
    CeragonHelper helper;
    if (weather)
    {
        helper.SetWeatherModel(weather);
    }
    helper.SetChannelAttribute("FadingStdDb", DoubleValue(0.0));
    cfg.modelA = modelA;
    cfg.modelB = modelB;
    cfg.distanceM = distanceM;
    return helper.Install(nodes.Get(0), nodes.Get(1), cfg);
}

Ptr<CeragonRadioNetDevice>
Dev(const NetDeviceContainer& d, uint32_t i)
{
    return DynamicCast<CeragonRadioNetDevice>(d.Get(i));
}

} // namespace

// ---------------------------------------------------------------------------
class CeragonPortfolioTestCase : public TestCase
{
  public:
    CeragonPortfolioTestCase()
        : TestCase("Portfolio catalog, vendor-string resolution and capability gating")
    {
    }

  private:
    void DoRun() override
    {
        NS_TEST_ASSERT_MSG_EQ(CeragonPortfolio::GetCatalog().size(), 31, "31 explicit models");
        NS_TEST_ASSERT_MSG_EQ(CeragonPortfolio::GetFamilyFallbacks().size(), 5, "5 families");
        for (const auto& spec : CeragonPortfolio::GetCatalog())
        {
            NS_TEST_ASSERT_MSG_EQ(CeragonPortfolio::Resolve(spec.model), &spec, spec.model);
            for (const auto& a : spec.aliases)
            {
                NS_TEST_ASSERT_MSG_EQ(CeragonPortfolio::Resolve(a), &spec, a);
            }
        }
        const std::vector<std::pair<std::string, std::string>> cases{
            {"FibeAir IP20C", "IP-20C"},
            {"ip_50cx", "IP-50CX"},
            {"Ceragon IP-50EXA", "IP-50EXA"},
            {"Siklu EtherHaul-8010FX", "EH-8010FX"},
            {"EtherHaul 8020", "EH-8020FX"},
            {"Ceragon-MH-T261-ctu-96", "MH-T261"},
            {"MultiHaul TG N366", "MH-N366"},
            {"IP-20 Evolution LH", "IP-20A-LH"},
            {"IP-50CXB", "IP-50CX"},
            {"IP-100E", "IP-100E"}};
        for (const auto& [raw, expected] : cases)
        {
            const auto* s = CeragonPortfolio::Resolve(raw);
            NS_TEST_ASSERT_MSG_NE(s, nullptr, raw);
            NS_TEST_ASSERT_MSG_EQ(s->model, expected, raw);
        }
        NS_TEST_ASSERT_MSG_EQ(CeragonPortfolio::Resolve("IP-50ZZZ9")->isFamilyFallback, true, "");
        NS_TEST_ASSERT_MSG_EQ(CeragonPortfolio::Resolve("MH-N999")->family, "MultiHaul TG", "");
        NS_TEST_ASSERT_MSG_EQ(CeragonPortfolio::Resolve("node-A"), nullptr, "non-Ceragon");
        uint32_t verified = 0;
        for (const auto& s : CeragonPortfolio::GetCatalog())
        {
            verified += s.apiVerified ? 1 : 0;
        }
        NS_TEST_ASSERT_MSG_EQ(verified, 1, "only MH-T261 is lab verified");
        std::string why;
        NS_TEST_ASSERT_MSG_EQ(
            CeragonPortfolio::CheckConfigSupport(CeragonPortfolio::Resolve("IP-20C"),
                                                 "beamforming",
                                                 why),
            false,
            "IP-20C has no beamforming");
        NS_TEST_ASSERT_MSG_EQ(
            CeragonPortfolio::CheckConfigSupport(CeragonPortfolio::Resolve("MH-N366"),
                                                 "protection",
                                                 why),
            true,
            "TG supports active-backup protection");
        NS_TEST_ASSERT_MSG_EQ(
            CeragonPortfolio::CheckConfigSupport(CeragonPortfolio::Resolve("EH-8010FX"),
                                                 "multiband",
                                                 why),
            false,
            "EtherHaul has no multiband");
    }
};

// ---------------------------------------------------------------------------
class CeragonAcmTestCase : public TestCase
{
  public:
    CeragonAcmTestCase()
        : TestCase("ACM profile tables, hysteresis and BER model")
    {
    }

  private:
    void DoRun() override
    {
        const auto& qam = CeragonAcm::GetQamTable();
        CeragonAcmController acm;
        acm.Configure(false,
                      CeragonAcm::FindIndex(qam, "QPSK"),
                      CeragonAcm::FindIndex(qam, "qam-4096"));
        NS_TEST_ASSERT_MSG_EQ(qam[acm.Update(45.0)].name, "4096QAM", "clear sky");
        NS_TEST_ASSERT_MSG_EQ(qam[acm.Update(25.0)].name, "128QAM", "immediate downshift");
        NS_TEST_ASSERT_MSG_EQ(qam[acm.Update(28.2)].name, "128QAM", "hysteresis holds");
        NS_TEST_ASSERT_MSG_EQ(qam[acm.Update(28.6)].name, "256QAM", "upshift");
        NS_TEST_ASSERT_MSG_EQ(acm.Update(5.0), -1, "outage below the ACM floor");
        acm.SetRange(CeragonAcm::FindIndex(qam, "256QAM"), CeragonAcm::FindIndex(qam, "4096QAM"));
        NS_TEST_ASSERT_MSG_EQ(acm.Update(25.0), -1, "raised ACM floor -> outage at 25 dB");

        const double r = CeragonAcm::CarrierRateBps(qam.back(), 112.0, false);
        NS_TEST_ASSERT_MSG_EQ_TOL(r / 1e6, 1052.0, 5.0, "112 MHz 4096QAM ~ 1 Gbps");
        const auto& mcs = CeragonAcm::GetMcsTable();
        NS_TEST_ASSERT_MSG_EQ_TOL(CeragonAcm::CarrierRateBps(mcs.back(), 2160.0, true) / 1e6,
                                  3696.0,
                                  1.0,
                                  "802.11ad MCS12 with MAC efficiency");
        NS_TEST_ASSERT_MSG_EQ_TOL(CeragonAcm::BitErrorRate(0.0), 1e-6, 1e-9, "BER at threshold");
        NS_TEST_ASSERT_MSG_LT(CeragonAcm::BitErrorRate(3.0), 1e-10, "BER with margin");
    }
};

// ---------------------------------------------------------------------------
class CeragonPropagationTestCase : public TestCase
{
  public:
    CeragonPropagationTestCase()
        : TestCase("ITU-R P.525, P.676, P.838, P.530 propagation")
    {
    }

  private:
    void DoRun() override
    {
        NS_TEST_ASSERT_MSG_EQ_TOL(CeragonItuPropagation::FreeSpaceLossDb(23.0, 1.0),
                                  119.68,
                                  0.05,
                                  "FSPL 23 GHz 1 km");
        NS_TEST_ASSERT_MSG_EQ_TOL(
            CeragonItuPropagation::GaseousSpecificAttenuationDbPerKm(60.0),
            15.0,
            0.01,
            "60 GHz oxygen absorption peak");
        NS_TEST_ASSERT_MSG_LT(CeragonItuPropagation::GaseousSpecificAttenuationDbPerKm(80.0),
                              0.5,
                              "E-band window");
        const double g80 = CeragonItuPropagation::RainSpecificAttenuationDbPerKm(80.0, 25.0, false);
        NS_TEST_ASSERT_MSG_EQ_TOL(g80, 11.5, 1.0, "P.838 80 GHz, 25 mm/h");
        const double g23 = CeragonItuPropagation::RainSpecificAttenuationDbPerKm(23.0, 25.0, false);
        NS_TEST_ASSERT_MSG_GT(g80, 2.5 * g23, "E-band far more rain sensitive than 23 GHz");
        NS_TEST_ASSERT_MSG_LT(CeragonItuPropagation::RainAttenuationDb(23.0, 20.0, 50.0, false, true),
                              CeragonItuPropagation::RainAttenuationDb(23.0, 20.0, 50.0, false, false),
                              "P.530 path reduction on long hops");
        NS_TEST_ASSERT_MSG_EQ_TOL(CeragonItuPropagation::XpdDb(23.0, 0.0), 40.0, 1e-6, "clear XPD");
        NS_TEST_ASSERT_MSG_LT(CeragonItuPropagation::XpdDb(23.0, 20.0), 30.0, "XPD degrades");
        NS_TEST_ASSERT_MSG_EQ_TOL(CeragonItuPropagation::ParabolicAntennaGainDbi(0.3, 23.0),
                                  34.6,
                                  0.5,
                                  "1 ft dish at 23 GHz");
        NS_TEST_ASSERT_MSG_EQ_TOL(CeragonItuPropagation::NoiseFloorDbm(112.0, 6.0),
                                  -87.5,
                                  0.1,
                                  "kTB + NF");

        Ptr<CeragonWeatherModel> w = CreateObject<CeragonWeatherModel>();
        w->ScheduleRainEvent(Seconds(1), Seconds(2), 80.0);
        double atPeak = 0;
        Simulator::Schedule(Seconds(2), [&atPeak, w]() { atPeak = w->GetRainRate(); });
        Simulator::Stop(Seconds(3));
        Simulator::Run();
        Simulator::Destroy();
        NS_TEST_ASSERT_MSG_EQ_TOL(atPeak, 80.0, 1e-6, "raised-cosine rain peak");
    }
};

// ---------------------------------------------------------------------------
class CeragonLinkCapacityTestCase : public TestCase
{
  public:
    CeragonLinkCapacityTestCase()
        : TestCase("IP-20C XPIC capacity in clear sky and rain")
    {
    }

  private:
    void DoRun() override
    {
        Ptr<CeragonWeatherModel> weather = CreateObject<CeragonWeatherModel>();
        NodeContainer nodes;
        auto devs = MakeHop(nodes, "IP-20C", "IP-20C", 5000.0, CeragonLinkConfig(), weather);
        auto a = Dev(devs, 0);
        double clear = 0;
        std::string mod0;
        std::string mod1;
        bool vertical = false;
        double rain = 0;
        bool upInRain = false;
        Simulator::Schedule(Seconds(0.1), [&]() {
            clear = a->GetAggregateCapacityBps();
            mod0 = a->GetCarrierModulation(0);
            mod1 = a->GetCarrierModulation(1);
            vertical = a->GetCarrier(1).verticalPol;
            weather->SetRainRate(50.0);
        });
        Simulator::Schedule(Seconds(0.2), [&]() {
            rain = a->GetAggregateCapacityBps();
            upInRain = a->IsLinkUp();
        });
        Simulator::Stop(Seconds(0.25));
        Simulator::Run();
        Simulator::Destroy();
        NS_TEST_ASSERT_MSG_EQ(a->GetNCarriers(), 2, "two XPIC carriers");
        NS_TEST_ASSERT_MSG_EQ(vertical, true, "carrier 1 on V polarization");
        NS_TEST_ASSERT_MSG_EQ(mod0, "4096QAM", "clear sky carrier 0");
        NS_TEST_ASSERT_MSG_EQ(mod1, "4096QAM", "clear sky carrier 1");
        NS_TEST_ASSERT_MSG_EQ_TOL(clear / 1e9, 2.0, 1e-6, "capped at IP-20C 2 Gbps");
        NS_TEST_ASSERT_MSG_LT(rain, 1.5e9, "ACM downshift in 50 mm/h rain");
        NS_TEST_ASSERT_MSG_EQ(upInRain, true, "hitless ACM keeps the link up");
    }
};

// ---------------------------------------------------------------------------
class CeragonTrafficTestCase : public TestCase
{
  public:
    CeragonTrafficTestCase()
        : TestCase("End-to-end UDP over EH-8010FX and QoS queue disc")
    {
    }

  private:
    void DoRun() override
    {
        NodeContainer nodes;
        auto devs = MakeHop(nodes, "EH-8010FX", "EH-8010FX", 1000.0);
        InternetStackHelper internet;
        internet.Install(nodes);
        CeragonHelper helper;
        QueueDiscContainer q = helper.InstallQos(devs);
        Ipv4AddressHelper addr("10.1.1.0", "255.255.255.252");
        Ipv4InterfaceContainer ifs = addr.Assign(devs);

        PacketSinkHelper sink("ns3::UdpSocketFactory",
                              InetSocketAddress(Ipv4Address::GetAny(), 9000));
        auto sinkApp = sink.Install(nodes.Get(1));
        OnOffHelper onoff("ns3::UdpSocketFactory", InetSocketAddress(ifs.GetAddress(1), 9000));
        onoff.SetConstantRate(DataRate("2Gbps"), 1400);
        onoff.SetAttribute("Tos", UintegerValue(46 << 2));
        auto app = onoff.Install(nodes.Get(0));
        app.Start(Seconds(0.1));
        app.Stop(Seconds(0.6));
        Simulator::Stop(Seconds(0.7));
        Simulator::Run();
        const uint64_t rx = DynamicCast<PacketSink>(sinkApp.Get(0))->GetTotalRx();
        auto qd = DynamicCast<CeragonQosQueueDisc>(q.Get(0));
        const uint64_t efDequeued = qd->GetDequeuedPackets(7);
        Simulator::Destroy();
        const double mbps = rx * 8.0 / 0.5 / 1e6;
        NS_TEST_ASSERT_MSG_EQ_TOL(mbps, 2000.0, 60.0, "2 Gbps delivered over a 10 Gbps E-band hop");
        NS_TEST_ASSERT_MSG_GT(efDequeued, 1000, "EF traffic classified into CoS 7");
    }
};

// ---------------------------------------------------------------------------
class CeragonMultibandTestCase : public TestCase
{
  public:
    CeragonMultibandTestCase()
        : TestCase("IP-50EX Multi-Band: E-band fades, MW anchor keeps the link up")
    {
    }

  private:
    void DoRun() override
    {
        Ptr<CeragonWeatherModel> weather = CreateObject<CeragonWeatherModel>();
        NodeContainer nodes;
        auto devs = MakeHop(nodes, "IP-50EX", "IP-50EX", 3000.0, CeragonLinkConfig(), weather);
        auto a = Dev(devs, 0);
        double clear = 0;
        double storm = 0;
        bool eUp = true;
        bool mwUp = false;
        bool linkUp = false;
        Simulator::Schedule(Seconds(0.1), [&]() {
            clear = a->GetAggregateCapacityBps();
            weather->SetRainRate(120.0);
        });
        Simulator::Schedule(Seconds(0.2), [&]() {
            storm = a->GetAggregateCapacityBps();
            eUp = a->GetCarrier(0).up;
            mwUp = a->GetCarrier(1).up;
            linkUp = a->IsLinkUp();
        });
        Simulator::Stop(Seconds(0.25));
        Simulator::Run();
        Simulator::Destroy();
        NS_TEST_ASSERT_MSG_EQ(a->GetNCarriers(), 2, "E-band + MW carriers");
        NS_TEST_ASSERT_MSG_GT(clear, 10e9, "multi-gigabit in clear sky");
        NS_TEST_ASSERT_MSG_EQ(eUp, false, "E-band carrier lost in 120 mm/h");
        NS_TEST_ASSERT_MSG_EQ(mwUp, true, "MW carrier survives");
        NS_TEST_ASSERT_MSG_EQ(linkUp, true, "link stays up (hitless multiband)");
        NS_TEST_ASSERT_MSG_GT(storm, 50e6, "residual MW capacity");
    }
};

// ---------------------------------------------------------------------------
class CeragonProtectionTestCase : public TestCase
{
  public:
    CeragonProtectionTestCase()
        : TestCase("1+1 HSB switchover vs unprotected radio failure")
    {
    }

  private:
    void DoRun() override
    {
        CeragonLinkConfig cfg;
        cfg.protection = CeragonProtectionMode::HSB_1PLUS1;
        NodeContainer n1;
        auto prot = MakeHop(n1, "IP-20C", "IP-20C", 5000.0, cfg);
        NodeContainer n2;
        auto unprot = MakeHop(n2, "IP-20C", "IP-20C", 5000.0);
        auto p = Dev(prot, 0);
        auto u = Dev(unprot, 0);
        bool duringSwitch = true;
        bool afterSwitch = false;
        bool unprotUp = true;
        Simulator::Schedule(Seconds(0.5), [&]() {
            p->FailRadioUnit(0);
            u->FailRadioUnit(0);
        });
        Simulator::Schedule(Seconds(0.52), [&]() { duringSwitch = p->IsLinkUp(); });
        Simulator::Schedule(Seconds(0.65), [&]() {
            afterSwitch = p->IsLinkUp();
            unprotUp = u->IsLinkUp();
        });
        Simulator::Stop(Seconds(0.7));
        Simulator::Run();
        Simulator::Destroy();
        NS_TEST_ASSERT_MSG_EQ(duringSwitch, false, "traffic hit during the 50 ms switchover");
        NS_TEST_ASSERT_MSG_EQ(afterSwitch, true, "protection radio carries the link");
        NS_TEST_ASSERT_MSG_EQ(p->GetActiveRadioUnit(), 1, "unit 1 active");
        NS_TEST_ASSERT_MSG_EQ(p->GetProtectionSwitchCount(), 1, "one switchover");
        NS_TEST_ASSERT_MSG_EQ(unprotUp, false, "unprotected link is down");
    }
};

// ---------------------------------------------------------------------------
class CeragonBeamformingTestCase : public TestCase
{
  public:
    CeragonBeamformingTestCase()
        : TestCase("MultiHaul TG beamforming: pole sway, beam tracking, topology scan")
    {
    }

  private:
    void DoRun() override
    {
        NodeContainer nodes;
        auto devs = MakeHop(nodes, "MH-N366", "MH-T261", 200.0);
        auto dn = Dev(devs, 0);
        double base = 0;
        double swayed = 0;
        double tracked = 0;
        bool bigSwayUp = true;
        double scanned = 0;
        Simulator::Schedule(Seconds(0.5), [&]() { base = dn->GetAggregateCapacityBps(); });
        Simulator::Schedule(Seconds(0.55), [&]() {
            dn->ApplyPoleSway(2.0);
            swayed = dn->GetAggregateCapacityBps();
        });
        Simulator::Schedule(Seconds(0.75), [&]() { tracked = dn->GetAggregateCapacityBps(); });
        Simulator::Schedule(Seconds(0.8), [&]() {
            dn->ApplyPoleSway(20.0);
            bigSwayUp = dn->IsLinkUp();
            dn->StartTopologyScan();
        });
        Simulator::Schedule(Seconds(1.5), [&]() { scanned = dn->GetAggregateCapacityBps(); });
        Simulator::Stop(Seconds(1.6));
        Simulator::Run();
        Simulator::Destroy();
        NS_TEST_ASSERT_MSG_EQ(dn->GetUseMcsTable(), true, "802.11ad MCS table");
        NS_TEST_ASSERT_MSG_GT(base, 500e6, "MCS operation at 200 m");
        NS_TEST_ASSERT_MSG_LT(swayed, base, "pole sway degrades the beam");
        NS_TEST_ASSERT_MSG_EQ_TOL(tracked, base, base * 0.25, "beam tracking recovers");
        NS_TEST_ASSERT_MSG_EQ(bigSwayUp, false, "20 deg misalignment breaks the link");
        NS_TEST_ASSERT_MSG_GT(scanned, 0.5 * base, "topology scan re-acquires the beam");
    }
};

// ---------------------------------------------------------------------------
class CeragonTsnGateTestCase : public TestCase
{
  public:
    CeragonTsnGateTestCase()
        : TestCase("IEEE 802.1Qbv gate control list and DSCP classification")
    {
    }

  private:
    void DoRun() override
    {
        Ptr<CeragonQosQueueDisc> q = CreateObject<CeragonQosQueueDisc>();
        q->AddGateControlEntry(MicroSeconds(200), 0x80);
        q->AddGateControlEntry(MicroSeconds(800), 0x7F);
        uint8_t g1 = 0;
        uint8_t g2 = 0;
        uint8_t g3 = 0;
        Simulator::Schedule(MicroSeconds(100), [&]() { g1 = q->GetGateStates(); });
        Simulator::Schedule(MicroSeconds(500), [&]() { g2 = q->GetGateStates(); });
        Simulator::Schedule(MicroSeconds(1150), [&]() { g3 = q->GetGateStates(); });
        Simulator::Stop(MilliSeconds(2));
        Simulator::Run();
        Simulator::Destroy();
        NS_TEST_ASSERT_MSG_EQ(q->GetGateCycleTime(), MicroSeconds(1000), "cycle");
        NS_TEST_ASSERT_MSG_EQ(+g1, 0x80, "express window");
        NS_TEST_ASSERT_MSG_EQ(+g2, 0x7F, "best-effort window");
        NS_TEST_ASSERT_MSG_EQ(+g3, 0x80, "next cycle");
        NS_TEST_ASSERT_MSG_EQ(+q->GetDscpQueue(46), 7, "EF -> CoS 7");
        NS_TEST_ASSERT_MSG_EQ(+q->GetDscpQueue(34), 4, "AF41 -> CoS 4");
        NS_TEST_ASSERT_MSG_EQ(+q->GetDscpQueue(0), 0, "BE -> CoS 0");
    }
};

// ---------------------------------------------------------------------------
class CeragonEnergySyncTestCase : public TestCase
{
  public:
    CeragonEnergySyncTestCase()
        : TestCase("Green carrier sleep, ATPC and PTP time error with holdover")
    {
    }

  private:
    void DoRun() override
    {
        CeragonLinkConfig green;
        green.carrierSleep = true;
        green.atpc = true;
        green.atpcTargetRslDbm = -50.0;
        green.sync = CeragonSyncMode::PTP_BOUNDARY_CLOCK;
        NodeContainer n1;
        auto g = MakeHop(n1, "IP-20C", "IP-20C", 5000.0, green);
        NodeContainer n2;
        auto r = MakeHop(n2, "IP-20C", "IP-20C", 5000.0);
        auto gd = Dev(g, 0);
        auto rd = Dev(r, 0);
        double gp = 0;
        double rp = 0;
        bool sleeping = false;
        double txp = 0;
        double teLocked = 0;
        Simulator::Schedule(Seconds(0.5), [&]() {
            gp = gd->GetPowerConsumptionW();
            rp = rd->GetPowerConsumptionW();
            sleeping = gd->GetCarrier(1).sleeping;
            txp = gd->GetCarrier(0).txPowerDbm;
            teLocked = gd->GetTimeErrorNs();
            gd->FailRadioUnit(0); // unprotected -> holdover
        });
        Simulator::Stop(Seconds(2.5));
        Simulator::Run();
        const double teHoldover = gd->GetTimeErrorNs();
        Simulator::Destroy();
        NS_TEST_ASSERT_MSG_EQ(sleeping, true, "secondary carrier sleeps at zero load");
        NS_TEST_ASSERT_MSG_LT(gp, rp, "green mode saves power");
        NS_TEST_ASSERT_MSG_LT(txp, 20.0, "ATPC reduced the transmit power");
        NS_TEST_ASSERT_MSG_EQ_TOL(teLocked, 20.0, 30.0, "class-B boundary clock cTE");
        NS_TEST_ASSERT_MSG_GT(teHoldover, teLocked + 50.0, "holdover drift while link down");
    }
};

// ---------------------------------------------------------------------------
class CeragonTwinHelperTestCase : public TestCase
{
  public:
    CeragonTwinHelperTestCase()
        : TestCase("Topology-file twin: build, flows, rain event, report")
    {
    }

  private:
    void DoRun() override
    {
        const std::string topo = R"(
# mixed-portfolio backhaul: CeraOS MW trunk + fibre + MultiHaul TG access
node core   IP-50FX   0    0
node hub    IP-50FX   3000 0
node dn     MH-N366   3000 10
node cn     MH-T261   3000 210
node site   host      0    -50
wire site core rate=10Gbps
link core hub distance=3000
wire hub dn rate=10Gbps
link dn cn distance=200
flow urllc site cn 50Mbps dscp=46 start=0.5
flow embb  site cn 600Mbps dscp=0 start=0.5
rain 1.0 1.0 60
event 1.2 core hub tx-power 10
)";
        CeragonTwinHelper twin;
        NS_TEST_ASSERT_MSG_EQ(twin.LoadTopologyString(topo), true, "parse");
        twin.EnableTelemetry(MilliSeconds(100), "");
        twin.Build();
        twin.Run(Seconds(2.5));
        const std::string json = twin.GetReportJson();
        NS_TEST_ASSERT_MSG_EQ(twin.GetErrors().empty(), true, "no errors");
        NS_TEST_ASSERT_MSG_NE(json.find("\"name\":\"urllc\""), std::string::npos, "flow report");
        NS_TEST_ASSERT_MSG_NE(json.find("tx-power"), std::string::npos, "control timeline");
        NS_TEST_ASSERT_MSG_EQ(static_cast<bool>(twin.GetDevice("dn", "cn")), true, "radio lookup");
        Simulator::Destroy();

        const double rate = CeragonOranXhaul::EcpriBitRate(100, 1, 4, "bfp-9bit");
        NS_TEST_ASSERT_MSG_EQ(CeragonOranXhaul::NumPrb(100, 1), 273, "273 PRB");
        NS_TEST_ASSERT_MSG_EQ_TOL(rate / 1e9, 7.1, 0.4, "Split 7.2x 100 MHz 4T4R BFP9");
    }
};

// ---------------------------------------------------------------------------
class CeragonTestSuite : public TestSuite
{
  public:
    CeragonTestSuite()
        : TestSuite("ceragon", Type::UNIT)
    {
        AddTestCase(new CeragonPortfolioTestCase, Duration::QUICK);
        AddTestCase(new CeragonAcmTestCase, Duration::QUICK);
        AddTestCase(new CeragonPropagationTestCase, Duration::QUICK);
        AddTestCase(new CeragonLinkCapacityTestCase, Duration::QUICK);
        AddTestCase(new CeragonTrafficTestCase, Duration::QUICK);
        AddTestCase(new CeragonMultibandTestCase, Duration::QUICK);
        AddTestCase(new CeragonProtectionTestCase, Duration::QUICK);
        AddTestCase(new CeragonBeamformingTestCase, Duration::QUICK);
        AddTestCase(new CeragonTsnGateTestCase, Duration::QUICK);
        AddTestCase(new CeragonEnergySyncTestCase, Duration::QUICK);
        AddTestCase(new CeragonTwinHelperTestCase, Duration::QUICK);
    }
};

static CeragonTestSuite g_ceragonTestSuite;
