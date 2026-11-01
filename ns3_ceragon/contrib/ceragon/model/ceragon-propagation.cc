/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#include "ceragon-propagation.h"

#include "ns3/double.h"
#include "ns3/log.h"
#include "ns3/simulator.h"

#include <algorithm>
#include <cmath>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("CeragonPropagation");
NS_OBJECT_ENSURE_REGISTERED(CeragonWeatherModel);

namespace
{

struct RainRow
{
    double f;
    double kH;
    double aH;
    double kV;
    double aV;
};

// ITU-R P.838-3 Table 5 (subset)
const std::vector<RainRow> P838{{1, 0.0000259, 0.9691, 0.0000308, 0.8592},
                                {2, 0.0000847, 1.0664, 0.0000998, 0.9490},
                                {4, 0.0001071, 1.6009, 0.0002461, 1.2476},
                                {6, 0.0007056, 1.5900, 0.0004878, 1.5728},
                                {7, 0.001915, 1.4810, 0.001425, 1.4745},
                                {8, 0.004115, 1.3905, 0.003450, 1.3797},
                                {10, 0.01217, 1.2571, 0.01129, 1.2156},
                                {11, 0.01772, 1.2140, 0.01731, 1.1617},
                                {13, 0.03041, 1.1586, 0.03266, 1.0901},
                                {15, 0.04481, 1.1233, 0.05008, 1.0440},
                                {18, 0.07078, 1.0818, 0.07708, 1.0025},
                                {20, 0.09164, 1.0568, 0.09611, 0.9847},
                                {25, 0.1571, 0.9991, 0.1533, 0.9491},
                                {30, 0.2403, 0.9485, 0.2291, 0.9129},
                                {35, 0.3374, 0.9047, 0.3224, 0.8761},
                                {40, 0.4431, 0.8673, 0.4274, 0.8421},
                                {50, 0.6600, 0.8084, 0.6472, 0.7871},
                                {60, 0.8606, 0.7656, 0.8515, 0.7486},
                                {70, 1.0315, 0.7345, 1.0253, 0.7215},
                                {80, 1.1704, 0.7115, 1.1668, 0.7021},
                                {90, 1.2807, 0.6944, 1.2795, 0.6876},
                                {100, 1.3671, 0.6815, 1.3680, 0.6765}};

// Sea-level gaseous specific attenuation (dB/km), ITU-R P.676 (7.5 g/m3, 15 C)
const std::vector<std::pair<double, double>> P676{
    {1, 0.005},  {6, 0.010},  {10, 0.013}, {15, 0.030}, {18, 0.060}, {20, 0.110}, {22.2, 0.200},
    {23, 0.180}, {26, 0.130}, {30, 0.110}, {38, 0.130}, {42, 0.180}, {50, 0.50},  {54, 2.50},
    {56, 7.00},  {58, 12.5},  {60, 15.0},  {62, 13.0},  {64, 6.50},  {66, 1.60},  {68, 0.70},
    {70, 0.45},  {75, 0.36},  {80, 0.35},  {86, 0.38},  {90, 0.40},  {100, 0.45}};

double
LogInterp(double x0, double y0, double x1, double y1, double x)
{
    const double t = (std::log(x) - std::log(x0)) / (std::log(x1) - std::log(x0));
    return std::exp(std::log(y0) + t * (std::log(y1) - std::log(y0)));
}

} // namespace

double
CeragonItuPropagation::FreeSpaceLossDb(double freqGhz, double distanceKm)
{
    distanceKm = std::max(distanceKm, 1e-4);
    return 92.45 + 20.0 * std::log10(freqGhz) + 20.0 * std::log10(distanceKm);
}

double
CeragonItuPropagation::GaseousSpecificAttenuationDbPerKm(double freqGhz)
{
    if (freqGhz <= P676.front().first)
    {
        return P676.front().second;
    }
    if (freqGhz >= P676.back().first)
    {
        return P676.back().second;
    }
    for (size_t i = 1; i < P676.size(); ++i)
    {
        if (freqGhz <= P676[i].first)
        {
            return LogInterp(P676[i - 1].first,
                             P676[i - 1].second,
                             P676[i].first,
                             P676[i].second,
                             freqGhz);
        }
    }
    return P676.back().second;
}

void
CeragonItuPropagation::RainCoefficients(double freqGhz, bool verticalPol, double& k, double& alpha)
{
    freqGhz = std::clamp(freqGhz, P838.front().f, P838.back().f);
    for (size_t i = 1; i < P838.size(); ++i)
    {
        if (freqGhz <= P838[i].f)
        {
            const RainRow& a = P838[i - 1];
            const RainRow& b = P838[i];
            const double ka = verticalPol ? a.kV : a.kH;
            const double kb = verticalPol ? b.kV : b.kH;
            const double aa = verticalPol ? a.aV : a.aH;
            const double ab = verticalPol ? b.aV : b.aH;
            k = LogInterp(a.f, ka, b.f, kb, freqGhz);
            const double t = (std::log(freqGhz) - std::log(a.f)) / (std::log(b.f) - std::log(a.f));
            alpha = aa + t * (ab - aa);
            return;
        }
    }
    k = verticalPol ? P838.back().kV : P838.back().kH;
    alpha = verticalPol ? P838.back().aV : P838.back().aH;
}

double
CeragonItuPropagation::RainSpecificAttenuationDbPerKm(double freqGhz,
                                                      double rainMmH,
                                                      bool verticalPol)
{
    if (rainMmH <= 0.0)
    {
        return 0.0;
    }
    double k;
    double alpha;
    RainCoefficients(freqGhz, verticalPol, k, alpha);
    return k * std::pow(rainMmH, alpha);
}

double
CeragonItuPropagation::P530DistanceFactor(double distanceKm,
                                          double freqGhz,
                                          double rainMmH,
                                          double alpha)
{
    if (rainMmH <= 0.0 || distanceKm <= 0.0)
    {
        return 1.0;
    }
    const double denom = 0.477 * std::pow(distanceKm, 0.633) * std::pow(rainMmH, 0.073 * alpha) *
                             std::pow(freqGhz, 0.123) -
                         10.579 * (1.0 - std::exp(-0.024 * distanceKm));
    if (denom <= 0.0)
    {
        return 2.5;
    }
    return std::clamp(1.0 / denom, 0.0, 2.5);
}

double
CeragonItuPropagation::RainAttenuationDb(double freqGhz,
                                         double distanceKm,
                                         double rainMmH,
                                         bool verticalPol,
                                         bool usePathReduction)
{
    if (rainMmH <= 0.0)
    {
        return 0.0;
    }
    double k;
    double alpha;
    RainCoefficients(freqGhz, verticalPol, k, alpha);
    const double gamma = k * std::pow(rainMmH, alpha);
    // For an instantaneous rain cell the P.530 factor is only used to model the
    // finite extent of the cell on long hops (r <= 1); short hops see uniform rain.
    const double r =
        usePathReduction
            ? std::min(1.0, P530DistanceFactor(distanceKm, freqGhz, rainMmH, alpha))
            : 1.0;
    return gamma * distanceKm * r;
}

double
CeragonItuPropagation::XpdDb(double freqGhz, double copolarRainAttDb)
{
    const double clearAirXpd = 40.0;
    if (copolarRainAttDb <= 0.1)
    {
        return clearAirXpd;
    }
    const double f = std::clamp(freqGhz, 8.0, 100.0);
    const double u = 15.0 + 30.0 * std::log10(f);
    const double v = (f <= 20.0) ? 12.8 * std::pow(f, 0.19) : 22.6;
    return std::clamp(u - v * std::log10(copolarRainAttDb), 0.0, clearAirXpd);
}

double
CeragonItuPropagation::ParabolicAntennaGainDbi(double diameterM, double freqGhz)
{
    const double lambda = 0.299792458 / freqGhz;
    const double eff = 0.55;
    return 10.0 * std::log10(eff * std::pow(M_PI * diameterM / lambda, 2.0));
}

double
CeragonItuPropagation::NoiseFloorDbm(double bandwidthMhz, double noiseFigureDb)
{
    return -174.0 + 10.0 * std::log10(bandwidthMhz * 1e6) + noiseFigureDb;
}

// ----------------------------------------------------------------------------

TypeId
CeragonWeatherModel::GetTypeId()
{
    static TypeId tid = TypeId("ns3::CeragonWeatherModel")
                            .SetParent<Object>()
                            .SetGroupName("Ceragon")
                            .AddConstructor<CeragonWeatherModel>()
                            .AddAttribute("RainRate",
                                          "Baseline rain rate (mm/h)",
                                          DoubleValue(0.0),
                                          MakeDoubleAccessor(&CeragonWeatherModel::m_baseRain),
                                          MakeDoubleChecker<double>(0.0, 300.0));
    return tid;
}

CeragonWeatherModel::CeragonWeatherModel()
    : m_baseRain(0.0)
{
}

CeragonWeatherModel::~CeragonWeatherModel() = default;

void
CeragonWeatherModel::SetRainRate(double mmPerHour)
{
    m_baseRain = std::max(0.0, mmPerHour);
}

double
CeragonWeatherModel::GetRainRate() const
{
    const Time now = Simulator::Now();
    double rain = m_baseRain;
    for (const auto& e : m_events)
    {
        if (now >= e.start && now <= e.start + e.duration && e.duration.IsStrictlyPositive())
        {
            const double x = (now - e.start).GetSeconds() / e.duration.GetSeconds();
            const double s = std::sin(M_PI * x);
            rain += e.peak * s * s;
        }
    }
    return rain;
}

void
CeragonWeatherModel::ScheduleRainEvent(Time start, Time duration, double peakMmPerHour)
{
    NS_LOG_FUNCTION(this << start << duration << peakMmPerHour);
    m_events.push_back({start, duration, peakMmPerHour});
}

void
CeragonWeatherModel::ClearRainEvents()
{
    m_events.clear();
}

} // namespace ns3
