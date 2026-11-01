/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * ITU-R propagation models for microwave / millimetre-wave fixed links:
 *  - Free-space path loss (ITU-R P.525)
 *  - Gaseous (O2 + H2O) specific attenuation, incl. the 60 GHz oxygen peak (ITU-R P.676)
 *  - Rain specific attenuation k/alpha coefficients (ITU-R P.838-3)
 *  - Effective path length / distance factor (ITU-R P.530-17)
 *  - Cross-polar discrimination (XPD) degradation under rain (ITU-R P.530)
 * and a time-varying weather model (regional rain events).
 */
#ifndef CERAGON_PROPAGATION_H
#define CERAGON_PROPAGATION_H

#include "ns3/nstime.h"
#include "ns3/object.h"

#include <vector>

namespace ns3
{

/**
 * @ingroup ceragon
 * Static ITU-R propagation formulas.
 */
class CeragonItuPropagation
{
  public:
    /// Free-space path loss (dB), ITU-R P.525
    static double FreeSpaceLossDb(double freqGhz, double distanceKm);
    /// Sea-level gaseous specific attenuation (dB/km), 7.5 g/m3 water vapour
    static double GaseousSpecificAttenuationDbPerKm(double freqGhz);
    /**
     * ITU-R P.838-3 rain coefficients (log-log interpolated).
     * @param freqGhz frequency
     * @param verticalPol true for vertical polarization
     * @param k output k coefficient
     * @param alpha output alpha coefficient
     */
    static void RainCoefficients(double freqGhz, bool verticalPol, double& k, double& alpha);
    /// Rain specific attenuation gamma_R = k R^alpha (dB/km)
    static double RainSpecificAttenuationDbPerKm(double freqGhz, double rainMmH, bool verticalPol);
    /// ITU-R P.530-17 distance factor r (effective path = r * d)
    static double P530DistanceFactor(double distanceKm, double freqGhz, double rainMmH, double alpha);
    /// Total rain attenuation over the hop (dB)
    static double RainAttenuationDb(double freqGhz,
                                    double distanceKm,
                                    double rainMmH,
                                    bool verticalPol,
                                    bool usePathReduction);
    /// Cross-polar discrimination (dB) given the co-polar rain attenuation (P.530 sec. 4)
    static double XpdDb(double freqGhz, double copolarRainAttDb);
    /// Parabolic antenna gain (dBi), efficiency 0.55
    static double ParabolicAntennaGainDbi(double diameterM, double freqGhz);
    /// Thermal noise floor kTB + NF (dBm)
    static double NoiseFloorDbm(double bandwidthMhz, double noiseFigureDb);
};

/**
 * @ingroup ceragon
 * Regional weather model shared by one or more radio channels.
 *
 * The instantaneous rain rate is the baseline rain rate plus the sum of all
 * scheduled rain events, each one following a raised-cosine (sin^2) profile
 * between its start and end time.
 */
class CeragonWeatherModel : public Object
{
  public:
    static TypeId GetTypeId();
    CeragonWeatherModel();
    ~CeragonWeatherModel() override;

    /// Set the baseline (steady) rain rate (mm/h)
    void SetRainRate(double mmPerHour);
    /// Instantaneous rain rate at the current simulation time (mm/h)
    double GetRainRate() const;
    /**
     * Schedule a rain cell crossing the region.
     * @param start absolute start time
     * @param duration storm duration
     * @param peakMmPerHour peak rain rate (reached at mid-storm)
     */
    void ScheduleRainEvent(Time start, Time duration, double peakMmPerHour);
    /// Remove all scheduled events
    void ClearRainEvents();

  private:
    struct RainEvent
    {
        Time start;
        Time duration;
        double peak;
    };

    double m_baseRain;
    std::vector<RainEvent> m_events;
};

} // namespace ns3

#endif /* CERAGON_PROPAGATION_H */
