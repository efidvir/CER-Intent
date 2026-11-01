/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * MultiHaul TG (Terragraph, 60 GHz) mesh twin.
 *
 * A POP MH-N366 feeds two distribution nodes forming a ring with client nodes
 * (MH-T261 / MH-T265). The scenario exercises:
 *   - 802.11ad MCS link adaptation and the 60 GHz oxygen absorption
 *   - pole sway (beam misalignment) and automatic beam tracking
 *   - a large misalignment that breaks a link, mesh rerouting, then
 *     a topology scan (start-topo-scan) that re-acquires the beam
 *
 *   ./ns3 run "ceragon-terragraph-mesh --simTime=8"
 */

#include "ns3/ceragon-module.h"
#include "ns3/core-module.h"

#include <iostream>

using namespace ns3;

int
main(int argc, char* argv[])
{
    double simTime = 8.0;
    std::string telemetry = "";

    CommandLine cmd(__FILE__);
    cmd.AddValue("simTime", "Simulation time (s)", simTime);
    cmd.AddValue("telemetry", "CSV telemetry file", telemetry);
    cmd.Parse(argc, argv);

    CeragonTwinHelper twin;
    twin.LoadTopologyString(R"(
# POP and fibre-fed core
node core  host     -30   0
node pop   MH-N366   0    0
node dnA   MH-N366   180  60
node dnB   MH-N366   180 -60
node cn1   MH-T261   330  80
node cn2   MH-T265   330 -80
node cn3   MH-T261   360   0
wire core pop rate=10Gbps
# mesh (ring) links
link pop dnA
link pop dnB
link dnA dnB
link dnA cn1
link dnB cn2
link dnA cn3
link dnB cn3
# services
flow cctv   core cn1 400Mbps dscp=0  start=0.5
flow voice  core cn2 20Mbps  dscp=46 start=0.5
flow fwa    core cn3 500Mbps dscp=18 start=0.5
# disturbances
event 2.0 pop dnA pole-sway 1.5
event 3.5 pop dnA pole-sway 25
event 5.0 pop dnA topo-scan
)");
    twin.EnableTelemetry(MilliSeconds(100), telemetry);
    twin.Build();
    twin.Run(Seconds(simTime));
    twin.PrintReport(std::cout);
    Simulator::Destroy();
    return 0;
}
