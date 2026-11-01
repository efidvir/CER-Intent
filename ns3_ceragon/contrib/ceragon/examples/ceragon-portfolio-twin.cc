/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Portfolio-wide functional twin: instantiates one radio hop per Ceragon
 * product (IP-20, IP-50, IP-100, EtherHaul, MultiHaul TG), applies a rain
 * storm and reports clear-sky vs. peak-rain behaviour (ACM profile, capacity,
 * RSL/SINR, power) for every model.
 *
 *   ./ns3 run "ceragon-portfolio-twin --all --rain=60"
 *   ./ns3 run "ceragon-portfolio-twin --model=IP-50EX --distance=3000 --rain=100"
 */

#include "ns3/ceragon-module.h"
#include "ns3/core-module.h"
#include "ns3/network-module.h"

#include <iomanip>
#include <iostream>
#include <sstream>

using namespace ns3;

namespace
{

double
TypicalHopMeters(const CeragonProductSpec& s)
{
    const auto& band = s.PrimaryBand().name;
    if (s.flavor == CeragonApiFlavor::SIKLU_TG)
    {
        return 200.0;
    }
    if (band == "V-band")
    {
        return 500.0;
    }
    if (band == "E-band")
    {
        return 2000.0;
    }
    if (band == "MW-LH")
    {
        return 30000.0;
    }
    return 5000.0;
}

struct Snapshot
{
    double capacity{0};
    std::string mods;
    double sinr{0};
    double rsl{0};
    double power{0};
    bool up{false};
};

Snapshot
Take(Ptr<CeragonRadioNetDevice> d)
{
    Snapshot s;
    s.capacity = d->GetAggregateCapacityBps();
    s.up = d->IsLinkUp();
    s.power = d->GetPowerConsumptionW();
    for (uint32_t i = 0; i < d->GetNCarriers(); ++i)
    {
        s.mods += (i ? "+" : "") + d->GetCarrierModulation(i);
    }
    if (d->GetNCarriers() > 0)
    {
        s.sinr = d->GetCarrier(0).sinrDb;
        s.rsl = d->GetCarrier(0).rslDbm;
    }
    return s;
}

} // namespace

int
main(int argc, char* argv[])
{
    std::string model = "";
    bool all = true;
    double distance = 0.0;
    double rain = 60.0;
    double simTime = 3.0;

    CommandLine cmd(__FILE__);
    cmd.AddValue("model", "Single product to twin (empty = whole portfolio)", model);
    cmd.AddValue("all", "Twin the whole portfolio", all);
    cmd.AddValue("distance", "Hop length in m (0 = typical per band)", distance);
    cmd.AddValue("rain", "Peak rain rate of the storm (mm/h)", rain);
    cmd.AddValue("simTime", "Simulation time (s)", simTime);
    cmd.Parse(argc, argv);

    std::vector<const CeragonProductSpec*> specs;
    if (!model.empty())
    {
        const auto* s = CeragonPortfolio::Resolve(model);
        if (!s)
        {
            std::cerr << "Unknown Ceragon model " << model << std::endl;
            return 1;
        }
        specs.push_back(s);
    }
    else
    {
        for (const auto& s : CeragonPortfolio::GetCatalog())
        {
            specs.push_back(&s);
        }
    }

    Ptr<CeragonWeatherModel> weather = CreateObject<CeragonWeatherModel>();
    weather->ScheduleRainEvent(Seconds(1.0), Seconds(1.0), rain); // peak at t = 1.5 s
    CeragonHelper helper;
    helper.SetWeatherModel(weather);

    std::vector<Ptr<CeragonRadioNetDevice>> devs;
    std::vector<double> hops;
    for (const auto* s : specs)
    {
        NodeContainer n;
        n.Create(2);
        CeragonLinkConfig cfg;
        cfg.modelA = s->model;
        cfg.distanceM = distance > 0 ? distance : TypicalHopMeters(*s);
        auto d = helper.Install(n.Get(0), n.Get(1), cfg);
        devs.push_back(DynamicCast<CeragonRadioNetDevice>(d.Get(0)));
        hops.push_back(cfg.distanceM);
    }

    std::vector<Snapshot> clear(devs.size());
    std::vector<Snapshot> storm(devs.size());
    Simulator::Schedule(Seconds(0.5), [&]() {
        for (size_t i = 0; i < devs.size(); ++i)
        {
            clear[i] = Take(devs[i]);
        }
    });
    Simulator::Schedule(Seconds(1.5), [&]() {
        for (size_t i = 0; i < devs.size(); ++i)
        {
            storm[i] = Take(devs[i]);
        }
    });
    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    std::cout << std::fixed << std::setprecision(1);
    std::cout << "\nCeragon portfolio functional twin  (storm peak " << rain << " mm/h)\n";
    std::cout << std::left << std::setw(11) << "Model" << std::setw(13) << "Family"
              << std::setw(9) << "Hop(km)" << std::setw(24) << "Clear ACM" << std::setw(11)
              << "Clear Mb/s" << std::setw(24) << "Rain ACM" << std::setw(11) << "Rain Mb/s"
              << std::setw(9) << "SINR dB" << std::setw(8) << "Avail" << "Power W\n";
    std::ostringstream json;
    json << std::fixed << std::setprecision(3) << "{\"rain_peak_mmh\":" << rain << ",\"models\":[";
    for (size_t i = 0; i < devs.size(); ++i)
    {
        const double avail = 1.0 - devs[i]->GetOutageTime().GetSeconds() / simTime;
        std::cout << std::left << std::setw(11) << specs[i]->model << std::setw(13)
                  << specs[i]->family << std::setw(9) << hops[i] / 1000.0 << std::setw(24)
                  << clear[i].mods << std::setw(11) << clear[i].capacity / 1e6 << std::setw(24)
                  << storm[i].mods << std::setw(11) << storm[i].capacity / 1e6 << std::setw(9)
                  << clear[i].sinr << std::setw(8) << avail * 100.0 << clear[i].power << "\n";
        json << (i ? "," : "") << "{\"model\":\"" << specs[i]->model << "\",\"family\":\""
             << specs[i]->family << "\",\"hop_km\":" << hops[i] / 1000.0
             << ",\"clear_capacity_mbps\":" << clear[i].capacity / 1e6
             << ",\"clear_modulation\":\"" << clear[i].mods << "\",\"rain_capacity_mbps\":"
             << storm[i].capacity / 1e6 << ",\"rain_modulation\":\"" << storm[i].mods
             << "\",\"clear_sinr_db\":" << clear[i].sinr << ",\"clear_rsl_dbm\":" << clear[i].rsl
             << ",\"availability\":" << avail << ",\"power_w\":" << clear[i].power
             << ",\"state\":" << devs[i]->GetStatusJson() << "}";
    }
    json << "]}";
    std::cout << "===CERAGON_TWIN_METRICS_START===\n"
              << json.str() << "\n===CERAGON_TWIN_METRICS_END===" << std::endl;
    Simulator::Destroy();
    return 0;
}
