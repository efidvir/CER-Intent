/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Generic Ceragon network twin driver.
 *
 * Loads a topology description (exported from TeraFlowSDN / CER-Intent by
 * tools/tfs_to_ceragon_twin.py), runs it and prints a JSON report between
 * ===CERAGON_TWIN_METRICS_START=== / ===CERAGON_TWIN_METRICS_END=== markers.
 *
 *   ./ns3 run "ceragon-twin-from-file --topology=contrib/ceragon/examples/topologies/metro-ring.twin
 *              --simTime=10 --telemetry=twin-telemetry.csv"
 *   ./ns3 run "ceragon-twin-from-file --listPortfolio"
 */

#include "ns3/ceragon-module.h"
#include "ns3/core-module.h"

#include <algorithm>
#include <iostream>

using namespace ns3;

int
main(int argc, char* argv[])
{
    std::string topology;
    std::string inlineTopo;
    std::string telemetry;
    double simTime = 10.0;
    double telemetryInterval = 0.1;
    bool listPortfolio = false;
    bool dynamicRouting = true;
    uint32_t seed = 1;

    CommandLine cmd(__FILE__);
    cmd.AddValue("topology", "Path to the .twin topology file", topology);
    cmd.AddValue("inline", "Topology statements separated by ';'", inlineTopo);
    cmd.AddValue("simTime", "Simulation time (s)", simTime);
    cmd.AddValue("telemetry", "CSV telemetry output path (empty = none)", telemetry);
    cmd.AddValue("telemetryInterval", "Telemetry sampling period (s)", telemetryInterval);
    cmd.AddValue("dynamicRouting", "Recompute routes on radio link up/down", dynamicRouting);
    cmd.AddValue("listPortfolio", "Print the Ceragon portfolio catalog as JSON and exit",
                 listPortfolio);
    cmd.AddValue("seed", "RNG run number", seed);
    cmd.Parse(argc, argv);

    if (listPortfolio)
    {
        std::cout << "===CERAGON_PORTFOLIO_START===\n"
                  << CeragonTwinHelper::PortfolioJson() << "\n===CERAGON_PORTFOLIO_END==="
                  << std::endl;
        return 0;
    }
    RngSeedManager::SetRun(seed);

    CeragonTwinHelper twin;
    bool ok = true;
    if (!topology.empty())
    {
        ok = twin.LoadTopologyFile(topology);
    }
    if (!inlineTopo.empty())
    {
        std::string text = inlineTopo;
        std::replace(text.begin(), text.end(), ';', '\n');
        ok &= twin.LoadTopologyString(text);
    }
    if (topology.empty() && inlineTopo.empty())
    {
        // Built-in demo: Multi-Band trunk (HSB) + MultiHaul TG access under a storm
        ok = twin.LoadTopologyString(R"(
node core  IP-50EX  0     0
node agg   IP-50EX  2500  0
node dn    MH-N366  2500  15
node cn1   MH-T261  2650  140
node cn2   MH-T261  2380  160
node srv   host     -20   0
wire srv core rate=25Gbps
link core agg distance=2500 protection=hsb sync=bc
wire agg dn rate=10Gbps
link dn cn1 distance=200
link dn cn2 distance=200
flow fronthaul srv cn1 150Mbps dscp=46 start=0.5
flow video     srv cn2 600Mbps dscp=0  start=0.5
rain 3 4 90
event 6.0 core agg fail-unit 0
event 7.5 dn cn1 pole-sway 3
)");
    }
    for (const auto& e : twin.GetErrors())
    {
        std::cerr << "topology error: " << e << std::endl;
    }
    if (!ok)
    {
        return 1;
    }
    twin.SetDynamicRouting(dynamicRouting);
    twin.EnableTelemetry(Seconds(telemetryInterval), telemetry);
    twin.Build();
    twin.Run(Seconds(simTime));
    twin.PrintReport(std::cout);
    Simulator::Destroy();
    return 0;
}
