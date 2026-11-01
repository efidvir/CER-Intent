/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Digital-twin builder: turns a declarative topology description (exported
 * from TeraFlowSDN / CER-Intent) into a running ns-3 network of Ceragon radio
 * twins, drives scheduled control events and weather, collects telemetry and
 * produces a machine-readable JSON report.
 */
#ifndef CERAGON_TWIN_HELPER_H
#define CERAGON_TWIN_HELPER_H

#include "ns3/ceragon-helper.h"
#include "ns3/ceragon-qos-queue-disc.h"
#include "ns3/flow-monitor-helper.h"
#include "ns3/ipv4-address.h"
#include "ns3/net-device-container.h"
#include "ns3/node-container.h"

#include <fstream>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace ns3
{

/**
 * @ingroup ceragon
 * Topology-file driven Ceragon network twin.
 *
 * Grammar (one statement per line, '#' starts a comment):
 * @code
 * node  <name> <model|host> <x_m> <y_m>
 * link  <a> <b> [model=|modelA=|modelB=<product>] [freq=MHz] [bw=MHz] [carriers=N]
 *               [xpic=0|1] [multiband=0|1]
 *               [distance=m] [maxmod=..] [minmod=..] [protection=none|hsb|sd|ab]
 *               [macsec=0|1] [atpc=0|1] [rsl=dBm] [sync=none|bc|tc|synce] [hc=0|1]
 *               [sleep=0|1] [qos=0|1] [strict=N] [fading=dB] [intf=dBm] [antenna=m]
 * wire  <a> <b> [rate=10Gbps] [delay=5us]
 * rain  <start_s> <duration_s> <peak_mm_h>
 * rain  base <mm_h>
 * flow  <name> <src> <dst> <rate> [dscp=0] [size=1400] [start=s] [stop=s]
 * tsn   <a> <b> <cycle_us> <express_window_us> [express_mask=0x80]
 * slice <a> <b> <cos> <pir> [dscp=d[,d...]] [weight=w]
 * event <t_s> <a> <b> <action> [value]
 *        actions: fail-unit, restore-unit, switchover, pole-sway, topo-scan,
 *                 tx-power, freq, min-mod, max-mod, interference, carrier-off,
 *                 carrier-on, macsec, atpc, adaptive
 * @endcode
 * The direction of a "link"/"tsn"/"slice"/"event" statement is a->b
 * (statements act on the device of node a facing node b).
 */
class CeragonTwinHelper
{
  public:
    CeragonTwinHelper();
    ~CeragonTwinHelper();

    bool LoadTopologyFile(const std::string& path);
    bool LoadTopologyString(const std::string& text);
    /// Build nodes, radios, IP addressing, routing, QoS, flows and events
    void Build();
    /// Periodic telemetry (per carrier) to a CSV file (empty path = memory only)
    void EnableTelemetry(Time interval, const std::string& csvPath);
    /// Recompute global routes when radio links go down/up (mesh rerouting)
    void SetDynamicRouting(bool enabled);
    /// Run the simulation until @p stopTime
    void Run(Time stopTime);

    std::string GetReportJson();
    /// Print the report wrapped in ===CERAGON_TWIN_METRICS_START/END=== markers
    void PrintReport(std::ostream& os);
    /// JSON dump of the full product catalog
    static std::string PortfolioJson();

    Ptr<Node> GetNode(const std::string& name) const;
    Ptr<CeragonRadioNetDevice> GetDevice(const std::string& a, const std::string& b) const;
    Ptr<CeragonQosQueueDisc> GetQueueDisc(const std::string& a, const std::string& b) const;
    Ptr<CeragonWeatherModel> GetWeather() const;
    CeragonHelper& GetHelper();
    std::vector<std::string> GetErrors() const;

  private:
    struct NodeDef
    {
        std::string name;
        std::string model;
        double x;
        double y;
    };

    struct LinkDef
    {
        std::string a;
        std::string b;
        bool wired{false};
        std::map<std::string, std::string> opts;
    };

    struct FlowDef
    {
        std::string name;
        std::string src;
        std::string dst;
        std::string rate;
        uint8_t dscp{0};
        uint32_t size{1400};
        double start{1.0};
        double stop{-1.0};
        uint16_t port{0};
    };

    struct EventDef
    {
        double t;
        std::string a;
        std::string b;
        std::string action;
        std::string value;
    };

    struct TsnDef
    {
        std::string a;
        std::string b;
        double cycleUs;
        double expressUs;
        uint8_t expressMask;
    };

    struct SliceDef
    {
        std::string a;
        std::string b;
        uint8_t cos;
        std::string pir;
        std::vector<uint8_t> dscps;
        uint32_t weight{1};
    };

    struct LinkStats
    {
        double minCap{1e300};
        double maxCap{0.0};
        double sumCap{0.0};
        uint64_t samples{0};
    };

    struct TimelineEvent
    {
        double t;
        std::string type;
        std::string detail;
    };

    bool ParseLine(const std::string& line, uint32_t lineNo);
    void ApplyEvent(const EventDef& e);
    void Sample();
    void OnModulationChange(std::string link, uint32_t carrier, std::string from, std::string to);
    void OnLinkState(std::string link, Ptr<CeragonRadioNetDevice> dev, bool up);
    void OnSwitch(std::string link, uint32_t from, uint32_t to);
    void RecomputeRoutes();
    void AddTimeline(const std::string& type, const std::string& detail);
    std::string Key(const std::string& a, const std::string& b) const;
    Ipv4Address PrimaryAddress(const std::string& node) const;

    std::vector<NodeDef> m_nodeDefs;
    std::vector<LinkDef> m_linkDefs;
    std::vector<FlowDef> m_flowDefs;
    std::vector<EventDef> m_eventDefs;
    std::vector<TsnDef> m_tsnDefs;
    std::vector<SliceDef> m_sliceDefs;
    std::vector<std::string> m_errors;

    CeragonHelper m_helper;
    Ptr<CeragonWeatherModel> m_weather;
    std::map<std::string, Ptr<Node>> m_nodes;
    std::map<std::string, Ptr<CeragonRadioNetDevice>> m_devices;
    std::map<std::string, Ptr<CeragonQosQueueDisc>> m_qdiscs;
    std::map<std::string, LinkStats> m_linkStats;
    std::vector<TimelineEvent> m_timeline;
    std::vector<std::string> m_radioLinkKeys;

    FlowMonitorHelper m_flowHelper;
    Ptr<FlowMonitor> m_monitor;
    Time m_telemetryInterval;
    std::unique_ptr<std::ofstream> m_csv;
    bool m_dynamicRouting;
    bool m_routePending;
    bool m_built;
    double m_simTime;
    double m_peakRain;
};

} // namespace ns3

#endif /* CERAGON_TWIN_HELPER_H */
