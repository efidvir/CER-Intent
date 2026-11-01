/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#include "ceragon-twin-helper.h"

#include "ns3/applications-module.h"
#include "ns3/ceragon-radio-channel.h"
#include "ns3/double.h"
#include "ns3/internet-module.h"
#include "ns3/ipv4-flow-classifier.h"
#include "ns3/log.h"
#include "ns3/mobility-module.h"
#include "ns3/point-to-point-helper.h"
#include "ns3/simulator.h"
#include "ns3/string.h"
#include "ns3/uinteger.h"

#include <algorithm>
#include <iomanip>
#include <sstream>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("CeragonTwinHelper");

namespace
{

std::vector<std::string>
Tokenize(const std::string& line)
{
    std::vector<std::string> out;
    std::istringstream is(line);
    std::string tok;
    while (is >> tok)
    {
        out.push_back(tok);
    }
    return out;
}

std::map<std::string, std::string>
ParseOpts(const std::vector<std::string>& toks, size_t from)
{
    std::map<std::string, std::string> m;
    for (size_t i = from; i < toks.size(); ++i)
    {
        const auto eq = toks[i].find('=');
        if (eq != std::string::npos)
        {
            m[toks[i].substr(0, eq)] = toks[i].substr(eq + 1);
        }
    }
    return m;
}

double
OptD(const std::map<std::string, std::string>& o, const std::string& k, double def)
{
    auto it = o.find(k);
    return it == o.end() ? def : std::stod(it->second);
}

std::string
OptS(const std::map<std::string, std::string>& o, const std::string& k, const std::string& def)
{
    auto it = o.find(k);
    return it == o.end() ? def : it->second;
}

bool
OptB(const std::map<std::string, std::string>& o, const std::string& k, bool def)
{
    auto it = o.find(k);
    if (it == o.end())
    {
        return def;
    }
    return it->second == "1" || it->second == "true" || it->second == "yes" || it->second == "on";
}

std::string
Esc(const std::string& s)
{
    std::string r;
    for (char c : s)
    {
        if (c == '"' || c == '\\')
        {
            r.push_back('\\');
        }
        r.push_back(c);
    }
    return r;
}

CeragonProtectionMode
ParseProtection(const std::string& s)
{
    if (s == "hsb" || s == "1+1" || s == "1+1_HSB")
    {
        return CeragonProtectionMode::HSB_1PLUS1;
    }
    if (s == "sd" || s == "space-diversity")
    {
        return CeragonProtectionMode::SPACE_DIVERSITY;
    }
    if (s == "ab" || s == "active-backup")
    {
        return CeragonProtectionMode::ACTIVE_BACKUP;
    }
    return CeragonProtectionMode::NONE;
}

CeragonSyncMode
ParseSync(const std::string& s)
{
    if (s == "bc" || s == "ptp" || s == "ptp-bc")
    {
        return CeragonSyncMode::PTP_BOUNDARY_CLOCK;
    }
    if (s == "tc" || s == "ptp-tc")
    {
        return CeragonSyncMode::PTP_TRANSPARENT_CLOCK;
    }
    if (s == "synce" || s == "synce+ptp")
    {
        return CeragonSyncMode::SYNCE_PTP;
    }
    return CeragonSyncMode::NONE;
}

} // namespace

CeragonTwinHelper::CeragonTwinHelper()
    : m_telemetryInterval(Seconds(0)),
      m_dynamicRouting(true),
      m_routePending(false),
      m_built(false),
      m_simTime(0.0),
      m_peakRain(0.0)
{
    m_weather = CreateObject<CeragonWeatherModel>();
    m_helper.SetWeatherModel(m_weather);
}

CeragonTwinHelper::~CeragonTwinHelper()
{
    if (m_csv)
    {
        m_csv->close();
    }
}

std::string
CeragonTwinHelper::Key(const std::string& a, const std::string& b) const
{
    return a + "->" + b;
}

bool
CeragonTwinHelper::LoadTopologyFile(const std::string& path)
{
    std::ifstream in(path);
    if (!in)
    {
        m_errors.push_back("cannot open topology file " + path);
        return false;
    }
    std::stringstream ss;
    ss << in.rdbuf();
    return LoadTopologyString(ss.str());
}

bool
CeragonTwinHelper::LoadTopologyString(const std::string& text)
{
    std::istringstream is(text);
    std::string line;
    uint32_t n = 0;
    bool ok = true;
    while (std::getline(is, line))
    {
        ++n;
        const auto hash = line.find('#');
        if (hash != std::string::npos)
        {
            line = line.substr(0, hash);
        }
        ok &= ParseLine(line, n);
    }
    return ok;
}

bool
CeragonTwinHelper::ParseLine(const std::string& line, uint32_t lineNo)
{
    const auto t = Tokenize(line);
    if (t.empty())
    {
        return true;
    }
    const std::string& kw = t[0];
    auto fail = [&](const std::string& msg) {
        m_errors.push_back("line " + std::to_string(lineNo) + ": " + msg);
        return false;
    };
    try
    {
        if (kw == "node" && t.size() >= 5)
        {
            m_nodeDefs.push_back({t[1], t[2], std::stod(t[3]), std::stod(t[4])});
        }
        else if ((kw == "link" || kw == "wire") && t.size() >= 3)
        {
            LinkDef l;
            l.a = t[1];
            l.b = t[2];
            l.wired = (kw == "wire");
            l.opts = ParseOpts(t, 3);
            m_linkDefs.push_back(l);
        }
        else if (kw == "rain" && t.size() >= 3 && t[1] == "base")
        {
            m_weather->SetRainRate(std::stod(t[2]));
            m_peakRain = std::max(m_peakRain, std::stod(t[2]));
        }
        else if (kw == "rain" && t.size() >= 4)
        {
            m_weather->ScheduleRainEvent(Seconds(std::stod(t[1])),
                                         Seconds(std::stod(t[2])),
                                         std::stod(t[3]));
            m_peakRain = std::max(m_peakRain, std::stod(t[3]));
        }
        else if (kw == "flow" && t.size() >= 5)
        {
            FlowDef f;
            f.name = t[1];
            f.src = t[2];
            f.dst = t[3];
            f.rate = t[4];
            auto o = ParseOpts(t, 5);
            f.dscp = static_cast<uint8_t>(OptD(o, "dscp", 0));
            f.size = static_cast<uint32_t>(OptD(o, "size", 1400));
            f.start = OptD(o, "start", 1.0);
            f.stop = OptD(o, "stop", -1.0);
            m_flowDefs.push_back(f);
        }
        else if (kw == "tsn" && t.size() >= 5)
        {
            auto o = ParseOpts(t, 5);
            m_tsnDefs.push_back(
                {t[1],
                 t[2],
                 std::stod(t[3]),
                 std::stod(t[4]),
                 static_cast<uint8_t>(std::stoul(OptS(o, "express_mask", "0x80"), nullptr, 0))});
        }
        else if (kw == "slice" && t.size() >= 5)
        {
            SliceDef s;
            s.a = t[1];
            s.b = t[2];
            s.cos = static_cast<uint8_t>(std::stoul(t[3]));
            s.pir = t[4];
            auto o = ParseOpts(t, 5);
            std::string d = OptS(o, "dscp", "");
            std::istringstream ds(d);
            std::string item;
            while (std::getline(ds, item, ','))
            {
                if (!item.empty())
                {
                    s.dscps.push_back(static_cast<uint8_t>(std::stoul(item)));
                }
            }
            s.weight = static_cast<uint32_t>(OptD(o, "weight", 1));
            m_sliceDefs.push_back(s);
        }
        else if (kw == "event" && t.size() >= 5)
        {
            m_eventDefs.push_back({std::stod(t[1]), t[2], t[3], t[4], t.size() > 5 ? t[5] : ""});
        }
        else
        {
            return fail("unrecognised statement '" + line + "'");
        }
    }
    catch (const std::exception& e)
    {
        return fail(std::string("parse error: ") + e.what());
    }
    return true;
}

void
CeragonTwinHelper::SetDynamicRouting(bool enabled)
{
    m_dynamicRouting = enabled;
}

void
CeragonTwinHelper::EnableTelemetry(Time interval, const std::string& csvPath)
{
    m_telemetryInterval = interval;
    if (!csvPath.empty())
    {
        m_csv = std::make_unique<std::ofstream>(csvPath);
        *m_csv << "time_s,link,model,link_up,capacity_mbps,carrier,freq_mhz,bw_mhz,pol,"
                  "modulation,rsl_dbm,sinr_db,tx_power_dbm,rate_mbps,rain_mmh,rain_att_db,"
                  "power_w,time_error_ns,misalignment_deg\n";
    }
}

void
CeragonTwinHelper::Build()
{
    NS_ASSERT_MSG(!m_built, "CeragonTwinHelper::Build called twice");
    m_built = true;

    // 1. Nodes + positions
    NodeContainer all;
    for (const auto& nd : m_nodeDefs)
    {
        Ptr<Node> node = CreateObject<Node>();
        m_nodes[nd.name] = node;
        all.Add(node);
    }
    MobilityHelper mobility;
    mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    mobility.Install(all);
    for (const auto& nd : m_nodeDefs)
    {
        m_nodes[nd.name]->GetObject<MobilityModel>()->SetPosition(Vector(nd.x, nd.y, 0.0));
    }

    InternetStackHelper internet;
    internet.Install(all);

    // 2. Links
    Ipv4AddressHelper addr;
    addr.SetBase("10.0.0.0", "255.255.255.252");
    std::map<std::string, std::string> modelOf;
    for (const auto& nd : m_nodeDefs)
    {
        modelOf[nd.name] = nd.model;
    }
    for (const auto& l : m_linkDefs)
    {
        if (!m_nodes.count(l.a) || !m_nodes.count(l.b))
        {
            m_errors.push_back("link references unknown node " + l.a + "/" + l.b);
            continue;
        }
        NetDeviceContainer devs;
        if (l.wired)
        {
            PointToPointHelper p2p;
            p2p.SetDeviceAttribute("DataRate", StringValue(OptS(l.opts, "rate", "10Gbps")));
            p2p.SetChannelAttribute("Delay", StringValue(OptS(l.opts, "delay", "5us")));
            devs = p2p.Install(m_nodes[l.a], m_nodes[l.b]);
        }
        else
        {
            CeragonLinkConfig cfg;
            // A site may host several radio products: link-level model overrides
            const std::string both = OptS(l.opts, "model", "");
            cfg.modelA = OptS(l.opts, "modelA", both.empty() ? modelOf[l.a] : both);
            cfg.modelB = OptS(l.opts, "modelB", both.empty() ? modelOf[l.b] : both);
            cfg.frequencyMhz = OptD(l.opts, "freq", 0.0);
            cfg.bandwidthMhz = OptD(l.opts, "bw", 0.0);
            cfg.carriers = static_cast<uint32_t>(OptD(l.opts, "carriers", 0));
            cfg.xpic = l.opts.count("xpic") ? (OptB(l.opts, "xpic", false) ? 1 : 0) : -1;
            cfg.multiband =
                l.opts.count("multiband") ? (OptB(l.opts, "multiband", false) ? 1 : 0) : -1;
            cfg.distanceM = OptD(l.opts, "distance", 0.0);
            cfg.antennaDiameterM = OptD(l.opts, "antenna", 0.0);
            cfg.maxModulation = OptS(l.opts, "maxmod", "");
            cfg.minModulation = OptS(l.opts, "minmod", "");
            cfg.protection = ParseProtection(OptS(l.opts, "protection", "none"));
            cfg.macsec = OptB(l.opts, "macsec", false);
            cfg.atpc = OptB(l.opts, "atpc", false);
            cfg.atpcTargetRslDbm = OptD(l.opts, "rsl", -45.0);
            cfg.sync = ParseSync(OptS(l.opts, "sync", "none"));
            cfg.headerCompression = OptB(l.opts, "hc", false);
            cfg.carrierSleep = OptB(l.opts, "sleep", false);
            devs = m_helper.Install(m_nodes[l.a], m_nodes[l.b], cfg);

            auto devA = DynamicCast<CeragonRadioNetDevice>(devs.Get(0));
            auto devB = DynamicCast<CeragonRadioNetDevice>(devs.Get(1));
            auto ch = DynamicCast<CeragonRadioChannel>(devA->GetChannel());
            if (l.opts.count("fading"))
            {
                ch->SetAttribute("FadingStdDb", DoubleValue(OptD(l.opts, "fading", 0.3)));
            }
            if (l.opts.count("intf"))
            {
                ch->SetInterferenceDbm(OptD(l.opts, "intf", -200.0));
            }
            m_devices[Key(l.a, l.b)] = devA;
            m_devices[Key(l.b, l.a)] = devB;
            m_radioLinkKeys.push_back(Key(l.a, l.b));
            m_radioLinkKeys.push_back(Key(l.b, l.a));

            if (OptB(l.opts, "qos", true))
            {
                QueueDiscContainer q =
                    m_helper.InstallQos(devs, static_cast<uint32_t>(OptD(l.opts, "strict", 2)));
                m_qdiscs[Key(l.a, l.b)] = DynamicCast<CeragonQosQueueDisc>(q.Get(0));
                m_qdiscs[Key(l.b, l.a)] = DynamicCast<CeragonQosQueueDisc>(q.Get(1));
            }
            const std::string ka = Key(l.a, l.b);
            const std::string kb = Key(l.b, l.a);
            for (const auto& [k, d] : {std::make_pair(ka, devA), std::make_pair(kb, devB)})
            {
                d->TraceConnectWithoutContext(
                    "ModulationChange",
                    MakeCallback(&CeragonTwinHelper::OnModulationChange, this).Bind(k));
                d->TraceConnectWithoutContext(
                    "LinkState",
                    MakeCallback(&CeragonTwinHelper::OnLinkState, this).Bind(k, d));
                d->TraceConnectWithoutContext(
                    "ProtectionSwitch",
                    MakeCallback(&CeragonTwinHelper::OnSwitch, this).Bind(k));
            }
        }
        addr.Assign(devs);
        addr.NewNetwork();
    }
    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    // 3. TSN gate control lists
    for (const auto& t : m_tsnDefs)
    {
        auto it = m_qdiscs.find(Key(t.a, t.b));
        if (it == m_qdiscs.end())
        {
            m_errors.push_back("tsn: no QoS queue disc on " + Key(t.a, t.b));
            continue;
        }
        it->second->ClearGateControlList();
        it->second->SetExpressQueues(t.expressMask);
        // Protected window: express queues only, then every gate open
        it->second->AddGateControlEntry(MicroSeconds(t.expressUs), t.expressMask);
        it->second->AddGateControlEntry(MicroSeconds(t.cycleUs - t.expressUs), 0xFF);
    }

    // 4. Transport slices
    for (const auto& s : m_sliceDefs)
    {
        auto it = m_qdiscs.find(Key(s.a, s.b));
        if (it == m_qdiscs.end())
        {
            m_errors.push_back("slice: no QoS queue disc on " + Key(s.a, s.b));
            continue;
        }
        it->second->SetQueueShaper(s.cos, DataRate(s.pir), 32000);
        it->second->SetQueueWeight(s.cos, s.weight);
        for (uint8_t d : s.dscps)
        {
            it->second->SetDscpQueue(d, s.cos);
        }
    }

    // 5. Traffic flows
    uint16_t port = 10000;
    for (auto& f : m_flowDefs)
    {
        if (!m_nodes.count(f.src) || !m_nodes.count(f.dst))
        {
            m_errors.push_back("flow " + f.name + " references unknown node");
            continue;
        }
        f.port = port++;
        PacketSinkHelper sink("ns3::UdpSocketFactory",
                              InetSocketAddress(Ipv4Address::GetAny(), f.port));
        ApplicationContainer sinkApp = sink.Install(m_nodes[f.dst]);
        sinkApp.Start(Seconds(0.0));

        OnOffHelper onoff("ns3::UdpSocketFactory",
                          InetSocketAddress(PrimaryAddress(f.dst), f.port));
        onoff.SetConstantRate(DataRate(f.rate), f.size);
        onoff.SetAttribute("Tos", UintegerValue(static_cast<uint8_t>(f.dscp << 2)));
        ApplicationContainer app = onoff.Install(m_nodes[f.src]);
        app.Start(Seconds(f.start));
        if (f.stop > 0.0)
        {
            app.Stop(Seconds(f.stop));
        }
    }

    // 6. Control events
    for (const auto& e : m_eventDefs)
    {
        Simulator::Schedule(Seconds(e.t), &CeragonTwinHelper::ApplyEvent, this, e);
    }

    m_monitor = m_flowHelper.InstallAll();
    if (m_telemetryInterval.IsStrictlyPositive())
    {
        Simulator::Schedule(m_telemetryInterval, &CeragonTwinHelper::Sample, this);
    }
}

Ipv4Address
CeragonTwinHelper::PrimaryAddress(const std::string& node) const
{
    Ptr<Ipv4> ipv4 = m_nodes.at(node)->GetObject<Ipv4>();
    NS_ASSERT_MSG(ipv4->GetNInterfaces() > 1, "node " << node << " has no interfaces");
    return ipv4->GetAddress(1, 0).GetLocal();
}

void
CeragonTwinHelper::ApplyEvent(const EventDef& e)
{
    auto dev = GetDevice(e.a, e.b);
    if (!dev)
    {
        AddTimeline("error", "event " + e.action + ": no radio " + Key(e.a, e.b));
        return;
    }
    auto peer = GetDevice(e.b, e.a);
    const std::string& v = e.value;
    const auto nC = dev->GetNCarriers();
    if (e.action == "fail-unit")
    {
        dev->FailRadioUnit(v.empty() ? 0 : std::stoul(v));
    }
    else if (e.action == "restore-unit")
    {
        dev->RestoreRadioUnit(v.empty() ? 0 : std::stoul(v));
    }
    else if (e.action == "switchover")
    {
        dev->ForceSwitchover();
    }
    else if (e.action == "pole-sway")
    {
        dev->ApplyPoleSway(std::stod(v));
    }
    else if (e.action == "topo-scan")
    {
        dev->StartTopologyScan();
        if (peer)
        {
            peer->StartTopologyScan();
        }
    }
    else if (e.action == "tx-power")
    {
        for (uint32_t i = 0; i < nC; ++i)
        {
            dev->SetCarrierTxPower(i, std::stod(v));
        }
    }
    else if (e.action == "freq")
    {
        dev->SetCarrierFrequency(0, std::stod(v));
        if (peer)
        {
            peer->SetCarrierFrequency(0, std::stod(v));
        }
    }
    else if (e.action == "min-mod" || e.action == "max-mod")
    {
        for (uint32_t i = 0; i < nC; ++i)
        {
            const auto& c = dev->GetCarrier(i);
            const auto& table = c.acm.GetTable();
            const std::string lo =
                (e.action == "min-mod") ? v : table[c.acm.GetMinIndex()].name;
            const std::string hi =
                (e.action == "max-mod") ? v : table[c.acm.GetMaxIndex()].name;
            dev->SetCarrierModulationRange(i, lo, hi);
        }
    }
    else if (e.action == "interference")
    {
        DynamicCast<CeragonRadioChannel>(dev->GetChannel())->SetInterferenceDbm(std::stod(v));
    }
    else if (e.action == "carrier-off" || e.action == "carrier-on")
    {
        const uint32_t i = v.empty() ? 0 : std::stoul(v);
        if (i < nC)
        {
            dev->SetCarrierEnabled(i, e.action == "carrier-on");
        }
    }
    else if (e.action == "macsec")
    {
        dev->SetMacsec(v != "0", "gcm-aes-256");
    }
    else if (e.action == "atpc")
    {
        dev->SetAtpc(v != "0", -45.0);
    }
    else if (e.action == "adaptive")
    {
        dev->SetAdaptiveModulation(v != "0");
    }
    else
    {
        AddTimeline("error", "unknown action " + e.action);
        return;
    }
    dev->UpdateLinkState();
    if (peer)
    {
        peer->UpdateLinkState();
    }
    AddTimeline("control", Key(e.a, e.b) + " " + e.action + (v.empty() ? "" : " " + v));
}

void
CeragonTwinHelper::AddTimeline(const std::string& type, const std::string& detail)
{
    if (m_timeline.size() < 5000)
    {
        m_timeline.push_back({Simulator::Now().GetSeconds(), type, detail});
    }
}

void
CeragonTwinHelper::OnModulationChange(std::string link,
                                      uint32_t carrier,
                                      std::string from,
                                      std::string to)
{
    AddTimeline("acm",
                link + " carrier " + std::to_string(carrier) + " " + from + " -> " + to);
}

void
CeragonTwinHelper::OnSwitch(std::string link, uint32_t from, uint32_t to)
{
    AddTimeline("protection",
                link + " radio unit " + std::to_string(from) + " -> " + std::to_string(to));
}

void
CeragonTwinHelper::OnLinkState(std::string link, Ptr<CeragonRadioNetDevice> dev, bool up)
{
    AddTimeline("link", link + (up ? " UP" : " DOWN"));
    if (!m_dynamicRouting)
    {
        return;
    }
    Ptr<Ipv4> ipv4 = dev->GetNode()->GetObject<Ipv4>();
    const int32_t ifc = ipv4->GetInterfaceForDevice(dev);
    if (ifc < 0)
    {
        return;
    }
    if (up)
    {
        ipv4->SetUp(ifc);
    }
    else
    {
        ipv4->SetDown(ifc);
    }
    if (!m_routePending)
    {
        m_routePending = true;
        Simulator::Schedule(MilliSeconds(20), &CeragonTwinHelper::RecomputeRoutes, this);
    }
}

void
CeragonTwinHelper::RecomputeRoutes()
{
    m_routePending = false;
    Ipv4GlobalRoutingHelper::RecomputeRoutingTables();
    AddTimeline("routing", "global routes recomputed");
}

void
CeragonTwinHelper::Sample()
{
    const double now = Simulator::Now().GetSeconds();
    for (const auto& key : m_radioLinkKeys)
    {
        auto dev = m_devices[key];
        const double cap = dev->GetAggregateCapacityBps();
        auto& st = m_linkStats[key];
        st.minCap = std::min(st.minCap, cap);
        st.maxCap = std::max(st.maxCap, cap);
        st.sumCap += cap;
        st.samples++;
        if (m_csv)
        {
            auto ch = DynamicCast<CeragonRadioChannel>(dev->GetChannel());
            for (uint32_t i = 0; i < dev->GetNCarriers(); ++i)
            {
                const auto& c = dev->GetCarrier(i);
                *m_csv << std::fixed << std::setprecision(3) << now << "," << key << ","
                       << dev->GetProductModel() << "," << (dev->IsLinkUp() ? 1 : 0) << ","
                       << cap / 1e6 << "," << i << "," << c.frequencyMhz << ","
                       << c.bandwidthMhz << "," << (c.verticalPol ? "V" : "H") << ","
                       << c.acm.GetCurrentName() << "," << c.rslDbm << "," << c.sinrDb << ","
                       << c.txPowerDbm << "," << c.rateBps / 1e6 << ","
                       << (ch ? ch->GetRainRate() : 0.0) << "," << c.rainAttDb << ","
                       << dev->GetPowerConsumptionW() << "," << dev->GetTimeErrorNs() << ","
                       << dev->GetMisalignmentDeg() << "\n";
            }
        }
    }
    m_peakRain = std::max(m_peakRain, m_weather->GetRainRate());
    Simulator::Schedule(m_telemetryInterval, &CeragonTwinHelper::Sample, this);
}

void
CeragonTwinHelper::Run(Time stopTime)
{
    if (!m_built)
    {
        Build();
    }
    m_simTime = stopTime.GetSeconds();
    Simulator::Stop(stopTime);
    Simulator::Run();
    if (m_csv)
    {
        m_csv->flush();
    }
}

std::string
CeragonTwinHelper::GetReportJson()
{
    std::ostringstream os;
    os << std::fixed << std::setprecision(4);
    os << "{\"engine\":\"ns-3 ceragon functional twin\",\"sim_time_s\":" << m_simTime
       << ",\"peak_rain_mmh\":" << m_peakRain << ",\"nodes\":[";
    for (size_t i = 0; i < m_nodeDefs.size(); ++i)
    {
        const auto& n = m_nodeDefs[i];
        const auto* spec = CeragonPortfolio::Resolve(n.model);
        os << (i ? "," : "") << "{\"name\":\"" << Esc(n.name) << "\",\"model\":\""
           << Esc(spec ? spec->model : n.model) << "\",\"family\":\""
           << (spec ? spec->family : "host") << "\",\"x\":" << n.x << ",\"y\":" << n.y << "}";
    }
    os << "],\"links\":[";
    bool first = true;
    for (const auto& key : m_radioLinkKeys)
    {
        auto dev = m_devices[key];
        const auto& st = m_linkStats[key];
        const double avail =
            m_simTime > 0 ? 1.0 - dev->GetOutageTime().GetSeconds() / m_simTime : 1.0;
        os << (first ? "" : ",") << "{\"link\":\"" << Esc(key) << "\",\"availability\":"
           << std::max(0.0, avail) << ",\"min_capacity_mbps\":"
           << (st.samples ? st.minCap / 1e6 : dev->GetAggregateCapacityBps() / 1e6)
           << ",\"avg_capacity_mbps\":"
           << (st.samples ? st.sumCap / st.samples / 1e6 : dev->GetAggregateCapacityBps() / 1e6)
           << ",\"max_capacity_mbps\":"
           << (st.samples ? st.maxCap / 1e6 : dev->GetAggregateCapacityBps() / 1e6);
        auto q = m_qdiscs.find(key);
        if (q != m_qdiscs.end())
        {
            os << ",\"qos\":{\"gate_cycle_us\":" << q->second->GetGateCycleTime().GetMicroSeconds()
               << ",\"gate_blocked\":" << q->second->GetGateBlockedEvents()
               << ",\"drops\":" << q->second->GetStats().nTotalDroppedPackets
               << ",\"dequeued_per_cos\":[";
            for (uint8_t c = 0; c < CeragonQosQueueDisc::N_QUEUES; ++c)
            {
                os << (c ? "," : "") << q->second->GetDequeuedPackets(c);
            }
            os << "]}";
        }
        os << ",\"state\":" << dev->GetStatusJson() << "}";
        first = false;
    }
    os << "],\"flows\":[";
    std::map<uint16_t, const FlowDef*> byPort;
    for (const auto& f : m_flowDefs)
    {
        byPort[f.port] = &f;
    }
    first = true;
    if (m_monitor)
    {
        m_monitor->CheckForLostPackets();
        auto classifier = DynamicCast<Ipv4FlowClassifier>(m_flowHelper.GetClassifier());
        for (const auto& [id, s] : m_monitor->GetFlowStats())
        {
            const auto tuple = classifier->FindFlow(id);
            auto it = byPort.find(tuple.destinationPort);
            if (it == byPort.end())
            {
                continue;
            }
            const FlowDef& f = *it->second;
            const double stop = (f.stop > 0.0) ? std::min(f.stop, m_simTime) : m_simTime;
            const double window = std::max(1e-9, stop - f.start);
            const double thr = s.rxBytes * 8.0 / window / 1e6;
            const double loss =
                s.txPackets ? 100.0 * (s.txPackets - s.rxPackets) / double(s.txPackets) : 0.0;
            const double delay = s.rxPackets ? s.delaySum.GetSeconds() * 1e3 / s.rxPackets : 0.0;
            const double jitter =
                s.rxPackets > 1 ? s.jitterSum.GetSeconds() * 1e3 / (s.rxPackets - 1) : 0.0;
            os << (first ? "" : ",") << "{\"name\":\"" << Esc(f.name) << "\",\"src\":\""
               << Esc(f.src) << "\",\"dst\":\"" << Esc(f.dst) << "\",\"dscp\":" << +f.dscp
               << ",\"offered_mbps\":" << DataRate(f.rate).GetBitRate() / 1e6
               << ",\"throughput_mbps\":" << thr << ",\"tx_packets\":" << s.txPackets
               << ",\"rx_packets\":" << s.rxPackets << ",\"loss_pct\":" << loss
               << ",\"mean_delay_ms\":" << delay << ",\"mean_jitter_ms\":" << jitter << "}";
            first = false;
        }
    }
    os << "],\"timeline\":[";
    for (size_t i = 0; i < m_timeline.size(); ++i)
    {
        const auto& e = m_timeline[i];
        os << (i ? "," : "") << "{\"t\":" << e.t << ",\"type\":\"" << e.type << "\",\"detail\":\""
           << Esc(e.detail) << "\"}";
    }
    os << "],\"errors\":[";
    for (size_t i = 0; i < m_errors.size(); ++i)
    {
        os << (i ? "," : "") << "\"" << Esc(m_errors[i]) << "\"";
    }
    os << "]}";
    return os.str();
}

void
CeragonTwinHelper::PrintReport(std::ostream& os)
{
    os << "===CERAGON_TWIN_METRICS_START===\n"
       << GetReportJson() << "\n===CERAGON_TWIN_METRICS_END===" << std::endl;
}

std::string
CeragonTwinHelper::PortfolioJson()
{
    std::ostringstream os;
    os << "[";
    const auto& cat = CeragonPortfolio::GetCatalog();
    for (size_t i = 0; i < cat.size(); ++i)
    {
        const auto& s = cat[i];
        os << (i ? "," : "") << "{\"model\":\"" << s.model << "\",\"family\":\"" << s.family
           << "\",\"api_flavor\":\"" << s.FlavorString() << "\",\"bands\":[";
        for (size_t b = 0; b < s.bands.size(); ++b)
        {
            os << (b ? "," : "") << "\"" << s.bands[b].name << "\"";
        }
        os << "],\"max_capacity_gbps\":" << s.maxCapacityGbps << ",\"topology\":\"" << s.topology
           << "\",\"duplex\":\"" << s.duplex << "\",\"radio_carriers\":" << s.radioCarriers
           << ",\"max_modulation\":\"" << s.maxModulation << "\",\"channel_bandwidths_mhz\":[";
        for (size_t c = 0; c < s.channelBandwidthsMhz.size(); ++c)
        {
            os << (c ? "," : "") << s.channelBandwidthsMhz[c];
        }
        os << "],\"features\":\"" << s.FeatureString() << "\",\"api_verified\":"
           << (s.apiVerified ? "true" : "false") << "}";
    }
    os << "]";
    return os.str();
}

Ptr<Node>
CeragonTwinHelper::GetNode(const std::string& name) const
{
    auto it = m_nodes.find(name);
    return it == m_nodes.end() ? nullptr : it->second;
}

Ptr<CeragonRadioNetDevice>
CeragonTwinHelper::GetDevice(const std::string& a, const std::string& b) const
{
    auto it = m_devices.find(Key(a, b));
    return it == m_devices.end() ? nullptr : it->second;
}

Ptr<CeragonQosQueueDisc>
CeragonTwinHelper::GetQueueDisc(const std::string& a, const std::string& b) const
{
    auto it = m_qdiscs.find(Key(a, b));
    return it == m_qdiscs.end() ? nullptr : it->second;
}

Ptr<CeragonWeatherModel>
CeragonTwinHelper::GetWeather() const
{
    return m_weather;
}

CeragonHelper&
CeragonTwinHelper::GetHelper()
{
    return m_helper;
}

std::vector<std::string>
CeragonTwinHelper::GetErrors() const
{
    return m_errors;
}

} // namespace ns3
