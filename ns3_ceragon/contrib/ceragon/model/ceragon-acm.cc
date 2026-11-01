/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#include "ceragon-acm.h"

#include <algorithm>
#include <cctype>
#include <cmath>

namespace ns3
{

const std::vector<CeragonModulation>&
CeragonAcm::GetQamTable()
{
    // Required SNR at BER 1e-6 including LDPC coding gain (typical CeraOS ACM thresholds).
    static const std::vector<CeragonModulation> t{{"BPSK", 1, 6.0, 0},
                                                  {"QPSK", 2, 9.0, 0},
                                                  {"8PSK", 3, 12.5, 0},
                                                  {"16QAM", 4, 15.5, 0},
                                                  {"32QAM", 5, 18.5, 0},
                                                  {"64QAM", 6, 21.5, 0},
                                                  {"128QAM", 7, 24.5, 0},
                                                  {"256QAM", 8, 27.5, 0},
                                                  {"512QAM", 9, 30.5, 0},
                                                  {"1024QAM", 10, 33.5, 0},
                                                  {"2048QAM", 11, 36.5, 0},
                                                  {"4096QAM", 12, 39.5, 0}};
    return t;
}

const std::vector<CeragonModulation>&
CeragonAcm::GetMcsTable()
{
    // IEEE 802.11ad SC PHY (2160 MHz channel). Terragraph link adaptation thresholds.
    static const std::vector<CeragonModulation> t{{"MCS1", 1, 1.0, 385.0},
                                                  {"MCS2", 1, 3.0, 770.0},
                                                  {"MCS3", 1, 4.5, 962.5},
                                                  {"MCS4", 1, 5.5, 1155.0},
                                                  {"MCS5", 1, 6.5, 1251.25},
                                                  {"MCS6", 2, 7.5, 1540.0},
                                                  {"MCS7", 2, 9.0, 1925.0},
                                                  {"MCS8", 2, 10.5, 2310.0},
                                                  {"MCS9", 2, 12.0, 2502.5},
                                                  {"MCS10", 4, 14.5, 3080.0},
                                                  {"MCS11", 4, 17.0, 3850.0},
                                                  {"MCS12", 4, 19.0, 4620.0}};
    return t;
}

int
CeragonAcm::FindIndex(const std::vector<CeragonModulation>& table, const std::string& name)
{
    std::string n;
    for (char c : name)
    {
        if (c != '-' && c != '_' && c != ' ')
        {
            n.push_back(static_cast<char>(std::toupper(static_cast<unsigned char>(c))));
        }
    }
    // "QAM4096" -> "4096QAM"
    if (n.rfind("QAM", 0) == 0 && n.size() > 3)
    {
        n = n.substr(3) + "QAM";
    }
    for (size_t i = 0; i < table.size(); ++i)
    {
        if (table[i].name == n)
        {
            return static_cast<int>(i);
        }
    }
    return -1;
}

double
CeragonAcm::CarrierRateBps(const CeragonModulation& m, double channelBandwidthMhz, bool mcsTable)
{
    if (mcsTable)
    {
        return m.phyRateMbps * 1e6 * (channelBandwidthMhz / 2160.0) * MAC_EFFICIENCY_TG;
    }
    return channelBandwidthMhz * 1e6 * m.bitsPerSymbol * CODE_RATE / (1.0 + ROLL_OFF);
}

double
CeragonAcm::BitErrorRate(double marginDb)
{
    double ber = 1e-6 * std::pow(10.0, -1.5 * marginDb);
    return std::clamp(ber, 1e-13, 0.5);
}

double
CeragonAcm::PacketErrorRate(double ber, uint32_t bytes)
{
    if (ber <= 0.0)
    {
        return 0.0;
    }
    return 1.0 - std::pow(1.0 - ber, 8.0 * bytes);
}

// ----------------------------------------------------------------------------

CeragonAcmController::CeragonAcmController()
    : m_mcs(false),
      m_min(0),
      m_max(11),
      m_current(-1),
      m_adaptive(true),
      m_upHysteresisDb(1.0),
      m_inOutage(false)
{
}

void
CeragonAcmController::Configure(bool mcsTable, int minIndex, int maxIndex)
{
    m_mcs = mcsTable;
    SetRange(minIndex, maxIndex);
    m_current = -1;
}

void
CeragonAcmController::SetRange(int minIndex, int maxIndex)
{
    const int last = static_cast<int>(GetTable().size()) - 1;
    m_min = std::clamp(minIndex, 0, last);
    m_max = std::clamp(maxIndex, m_min, last);
    if (m_current >= 0)
    {
        m_current = std::clamp(m_current, m_min, m_max);
    }
}

void
CeragonAcmController::SetAdaptive(bool adaptive)
{
    m_adaptive = adaptive;
}

void
CeragonAcmController::SetHysteresis(double upDb)
{
    m_upHysteresisDb = upDb;
}

int
CeragonAcmController::Update(double sinrDb)
{
    const auto& t = GetTable();
    if (!m_adaptive)
    {
        // Fixed modulation: stays at the ceiling until SINR falls below the floor threshold.
        m_current = (sinrDb >= t[m_min].requiredSnrDb) ? m_max : -1;
        return m_current;
    }
    if (sinrDb < t[m_min].requiredSnrDb)
    {
        m_current = -1; // outage: below the ACM floor
        m_inOutage = true;
        return m_current;
    }
    if (m_inOutage && sinrDb < t[m_min].requiredSnrDb + m_upHysteresisDb)
    {
        return -1; // outage recovery requires the floor threshold + hysteresis
    }
    m_inOutage = false;
    // Highest profile whose threshold is met
    int target = m_min;
    for (int i = m_max; i >= m_min; --i)
    {
        if (sinrDb >= t[i].requiredSnrDb)
        {
            target = i;
            break;
        }
    }
    if (m_current < 0)
    {
        m_current = target;
    }
    else if (target < m_current)
    {
        m_current = target; // immediate (hitless) downshift
    }
    else if (target > m_current)
    {
        // upshift only with hysteresis margin
        int up = m_current;
        for (int i = target; i > m_current; --i)
        {
            if (sinrDb >= t[i].requiredSnrDb + m_upHysteresisDb)
            {
                up = i;
                break;
            }
        }
        m_current = up;
    }
    return m_current;
}

int
CeragonAcmController::GetCurrentIndex() const
{
    return m_current;
}

int
CeragonAcmController::GetMinIndex() const
{
    return m_min;
}

int
CeragonAcmController::GetMaxIndex() const
{
    return m_max;
}

bool
CeragonAcmController::IsAdaptive() const
{
    return m_adaptive;
}

bool
CeragonAcmController::IsMcsTable() const
{
    return m_mcs;
}

const std::vector<CeragonModulation>&
CeragonAcmController::GetTable() const
{
    return m_mcs ? CeragonAcm::GetMcsTable() : CeragonAcm::GetQamTable();
}

std::string
CeragonAcmController::GetCurrentName() const
{
    if (m_current < 0)
    {
        return "OUTAGE";
    }
    return GetTable()[m_current].name;
}

} // namespace ns3
