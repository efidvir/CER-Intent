/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#include "ceragon-qos-queue-disc.h"

#include "ceragon-radio-net-device.h"

#include "ns3/boolean.h"
#include "ns3/drop-tail-queue.h"
#include "ns3/log.h"
#include "ns3/object-factory.h"
#include "ns3/simulator.h"
#include "ns3/socket.h"
#include "ns3/uinteger.h"

#include <algorithm>
#include <cmath>
#include <limits>

namespace ns3
{

NS_LOG_COMPONENT_DEFINE("CeragonQosQueueDisc");
NS_OBJECT_ENSURE_REGISTERED(CeragonQosQueueDisc);

namespace
{
constexpr int64_t NEVER = std::numeric_limits<int64_t>::max();
}

TypeId
CeragonQosQueueDisc::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::CeragonQosQueueDisc")
            .SetParent<QueueDisc>()
            .SetGroupName("Ceragon")
            .AddConstructor<CeragonQosQueueDisc>()
            .AddAttribute("MaxSize",
                          "Total queue disc capacity",
                          QueueSizeValue(QueueSize("8000p")),
                          MakeQueueSizeAccessor(&QueueDisc::SetMaxSize, &QueueDisc::GetMaxSize),
                          MakeQueueSizeChecker())
            .AddAttribute("QueueLimit",
                          "Per-CoS queue limit (packets)",
                          UintegerValue(1000),
                          MakeUintegerAccessor(&CeragonQosQueueDisc::m_queueLimit),
                          MakeUintegerChecker<uint32_t>(1))
            .AddAttribute("StrictPriorityQueues",
                          "Number of highest CoS queues served in strict priority",
                          UintegerValue(2),
                          MakeUintegerAccessor(&CeragonQosQueueDisc::m_strictQueues),
                          MakeUintegerChecker<uint32_t>(0, N_QUEUES))
            .AddAttribute("Quantum",
                          "DRR quantum (bytes) per unit of weight",
                          UintegerValue(1600),
                          MakeUintegerAccessor(&CeragonQosQueueDisc::m_quantum),
                          MakeUintegerChecker<uint32_t>(64))
            .AddAttribute("GuardBand",
                          "802.1Qbv guard band: do not start frames that cross a gate close",
                          BooleanValue(true),
                          MakeBooleanAccessor(&CeragonQosQueueDisc::m_guardBand),
                          MakeBooleanChecker())
            .AddAttribute("FramePreemption",
                          "802.1Qbu: preemptable frames only need a 127-byte guard band",
                          BooleanValue(false),
                          MakeBooleanAccessor(&CeragonQosQueueDisc::m_preemption),
                          MakeBooleanChecker())
            .AddAttribute("ExpressQueues",
                          "Bit mask of express (non-preemptable) CoS queues",
                          UintegerValue(0xC0),
                          MakeUintegerAccessor(&CeragonQosQueueDisc::m_expressMask),
                          MakeUintegerChecker<uint8_t>());
    return tid;
}

CeragonQosQueueDisc::CeragonQosQueueDisc()
    : QueueDisc(QueueDiscSizePolicy::MULTIPLE_QUEUES, QueueSizeUnit::PACKETS),
      m_cycleNs(0),
      m_baseNs(0),
      m_lastRefillNs(0),
      m_strictQueues(2),
      m_quantum(1600),
      m_queueLimit(1000),
      m_drrPos(0),
      m_drrFresh(true),
      m_guardBand(true),
      m_preemption(false),
      m_expressMask(0xC0),
      m_gateBlocked(0)
{
    NS_LOG_FUNCTION(this);
    for (uint32_t d = 0; d < 64; ++d)
    {
        m_dscpMap[d] = static_cast<uint8_t>(d >> 3); // class selector -> CoS
    }
    m_dscpMap[46] = 7; // EF  (URLLC / TSN)
    m_dscpMap[48] = 6; // CS6 (network control, PTP)
    m_dscpMap[56] = 7; // CS7
    m_weights.fill(1);
    m_deficit.fill(0);
    m_dequeued.fill(0);
}

CeragonQosQueueDisc::~CeragonQosQueueDisc() = default;

void
CeragonQosQueueDisc::DoDispose()
{
    m_wakeEvent.Cancel();
    m_device = nullptr;
    QueueDisc::DoDispose();
}

void
CeragonQosQueueDisc::SetDscpQueue(uint8_t dscp, uint8_t queue)
{
    NS_ASSERT(dscp < 64 && queue < N_QUEUES);
    m_dscpMap[dscp] = queue;
}

uint8_t
CeragonQosQueueDisc::GetDscpQueue(uint8_t dscp) const
{
    return m_dscpMap[dscp & 0x3F];
}

void
CeragonQosQueueDisc::SetQueueWeight(uint8_t queue, uint32_t weight)
{
    NS_ASSERT(queue < N_QUEUES);
    m_weights[queue] = std::max<uint32_t>(1, weight);
}

void
CeragonQosQueueDisc::SetQueueShaper(uint8_t queue, DataRate pir, uint32_t burstBytes)
{
    NS_ASSERT(queue < N_QUEUES);
    m_shapers[queue].rateBps = static_cast<double>(pir.GetBitRate());
    m_shapers[queue].burstBytes = std::max<double>(burstBytes, 1600.0);
    m_shapers[queue].tokens = m_shapers[queue].burstBytes;
}

void
CeragonQosQueueDisc::AddGateControlEntry(Time duration, uint8_t gateMask)
{
    NS_ASSERT(duration.IsStrictlyPositive());
    m_gcl.push_back({duration.GetNanoSeconds(), gateMask});
    m_cycleNs += duration.GetNanoSeconds();
}

void
CeragonQosQueueDisc::ClearGateControlList()
{
    m_gcl.clear();
    m_cycleNs = 0;
}

void
CeragonQosQueueDisc::SetGateBaseTime(Time baseTime)
{
    m_baseNs = baseTime.GetNanoSeconds();
}

Time
CeragonQosQueueDisc::GetGateCycleTime() const
{
    return NanoSeconds(m_cycleNs);
}

uint8_t
CeragonQosQueueDisc::GetGateStates() const
{
    int64_t next;
    return MaskAt(Simulator::Now().GetNanoSeconds(), next);
}

void
CeragonQosQueueDisc::SetDevice(Ptr<CeragonRadioNetDevice> device)
{
    m_device = device;
}

void
CeragonQosQueueDisc::SetExpressQueues(uint8_t mask)
{
    m_expressMask = mask;
}

uint32_t
CeragonQosQueueDisc::GetQueueLength(uint8_t queue) const
{
    if (queue >= GetNInternalQueues())
    {
        return 0;
    }
    return GetInternalQueue(queue)->GetNPackets();
}

uint64_t
CeragonQosQueueDisc::GetDequeuedPackets(uint8_t queue) const
{
    return m_dequeued[queue % N_QUEUES];
}

uint64_t
CeragonQosQueueDisc::GetGateBlockedEvents() const
{
    return m_gateBlocked;
}

uint8_t
CeragonQosQueueDisc::ClassifyCos(Ptr<QueueDiscItem> item) const
{
    uint8_t ds = 0;
    if (item->GetUint8Value(QueueItem::IP_DSFIELD, ds))
    {
        return m_dscpMap[(ds >> 2) & 0x3F];
    }
    SocketPriorityTag tag;
    if (item->GetPacket()->PeekPacketTag(tag))
    {
        return tag.GetPriority() & 0x07;
    }
    return 0;
}

bool
CeragonQosQueueDisc::DoEnqueue(Ptr<QueueDiscItem> item)
{
    NS_LOG_FUNCTION(this << item);
    if (GetCurrentSize() >= GetMaxSize())
    {
        DropBeforeEnqueue(item, "Queue disc limit exceeded");
        return false;
    }
    const uint8_t q = ClassifyCos(item);
    // On failure the internal queue triggers DropBeforeEnqueue via its traces
    return GetInternalQueue(q)->Enqueue(item);
}

uint8_t
CeragonQosQueueDisc::MaskAt(int64_t tNs, int64_t& nextChangeNs) const
{
    if (m_gcl.empty() || m_cycleNs <= 0)
    {
        nextChangeNs = NEVER;
        return 0xFF;
    }
    if (tNs < m_baseNs)
    {
        nextChangeNs = m_baseNs;
        return 0xFF;
    }
    const int64_t pos = (tNs - m_baseNs) % m_cycleNs;
    int64_t acc = 0;
    for (const auto& e : m_gcl)
    {
        if (pos < acc + e.durationNs)
        {
            nextChangeNs = tNs + (acc + e.durationNs - pos);
            return e.mask;
        }
        acc += e.durationNs;
    }
    nextChangeNs = tNs + (m_cycleNs - pos);
    return m_gcl.back().mask;
}

int64_t
CeragonQosQueueDisc::NextGateOpen(uint8_t queue, int64_t nowNs) const
{
    const uint8_t bit = static_cast<uint8_t>(1U << queue);
    int64_t t = nowNs;
    for (size_t step = 0; step < 2 * m_gcl.size() + 2; ++step)
    {
        int64_t next;
        const uint8_t mask = MaskAt(t, next);
        if (mask & bit)
        {
            return t;
        }
        if (next == NEVER)
        {
            return NEVER;
        }
        t = next;
    }
    return NEVER;
}

int64_t
CeragonQosQueueDisc::NextGateClose(uint8_t queue, int64_t nowNs) const
{
    const uint8_t bit = static_cast<uint8_t>(1U << queue);
    int64_t t = nowNs;
    for (size_t step = 0; step < 2 * m_gcl.size() + 2; ++step)
    {
        int64_t next;
        const uint8_t mask = MaskAt(t, next);
        if (!(mask & bit))
        {
            return t;
        }
        if (next == NEVER)
        {
            return NEVER;
        }
        t = next;
    }
    return NEVER;
}

void
CeragonQosQueueDisc::RefillTokens(int64_t nowNs)
{
    const double dt = static_cast<double>(nowNs - m_lastRefillNs) * 1e-9;
    m_lastRefillNs = nowNs;
    if (dt <= 0.0)
    {
        return;
    }
    for (auto& s : m_shapers)
    {
        if (s.rateBps > 0.0)
        {
            s.tokens = std::min(s.burstBytes, s.tokens + s.rateBps * dt / 8.0);
        }
    }
}

bool
CeragonQosQueueDisc::Eligible(uint8_t queue, int64_t nowNs, int64_t& wakeNs)
{
    Ptr<InternalQueue> q = GetInternalQueue(queue);
    if (q->IsEmpty())
    {
        return false;
    }
    const uint32_t size = q->Peek()->GetSize();
    const uint8_t bit = static_cast<uint8_t>(1U << queue);

    if (!m_gcl.empty())
    {
        const int64_t open = NextGateOpen(queue, nowNs);
        if (open > nowNs)
        {
            wakeNs = std::min(wakeNs, open);
            m_gateBlocked++;
            return false;
        }
        if (m_guardBand && m_device)
        {
            const double rate = m_device->GetAggregateCapacityBps();
            if (rate > 0.0)
            {
                const uint32_t guardBytes = (m_preemption && !(m_expressMask & bit))
                                                ? std::min<uint32_t>(size, 127)
                                                : size;
                const auto txNs = static_cast<int64_t>(std::ceil(guardBytes * 8.0 / rate * 1e9));
                const int64_t close = NextGateClose(queue, nowNs);
                if (close != NEVER && nowNs + txNs > close)
                {
                    wakeNs = std::min(wakeNs, NextGateOpen(queue, close));
                    m_gateBlocked++;
                    return false;
                }
            }
        }
    }

    Shaper& s = m_shapers[queue];
    if (s.rateBps > 0.0 && s.tokens < size)
    {
        const auto needNs =
            static_cast<int64_t>(std::ceil((size - s.tokens) * 8.0 / s.rateBps * 1e9));
        wakeNs = std::min(wakeNs, nowNs + std::max<int64_t>(needNs, 1));
        return false;
    }
    return true;
}

Ptr<QueueDiscItem>
CeragonQosQueueDisc::Serve(uint8_t queue)
{
    Ptr<QueueDiscItem> item = GetInternalQueue(queue)->Dequeue();
    if (item)
    {
        if (m_shapers[queue].rateBps > 0.0)
        {
            m_shapers[queue].tokens -= item->GetSize();
        }
        m_dequeued[queue]++;
    }
    return item;
}

Ptr<QueueDiscItem>
CeragonQosQueueDisc::DoDequeue()
{
    NS_LOG_FUNCTION(this);
    const int64_t now = Simulator::Now().GetNanoSeconds();
    RefillTokens(now);
    int64_t wake = NEVER;

    // 1. Strict-priority CoS queues (highest first)
    for (int q = static_cast<int>(N_QUEUES) - 1; q >= static_cast<int>(N_QUEUES - m_strictQueues);
         --q)
    {
        if (Eligible(static_cast<uint8_t>(q), now, wake))
        {
            return Serve(static_cast<uint8_t>(q));
        }
    }

    // 2. Deficit Round Robin among the remaining queues
    const uint32_t nDrr = N_QUEUES - m_strictQueues;
    for (uint32_t tries = 0; nDrr > 0 && tries < 4 * nDrr; ++tries)
    {
        const auto q = static_cast<uint8_t>(m_drrPos % nDrr);
        if (!Eligible(q, now, wake))
        {
            if (GetInternalQueue(q)->IsEmpty())
            {
                m_deficit[q] = 0;
            }
            m_drrPos = (m_drrPos + 1) % nDrr;
            m_drrFresh = true;
            continue;
        }
        if (m_drrFresh)
        {
            m_deficit[q] += static_cast<int64_t>(m_quantum) * m_weights[q];
            m_drrFresh = false;
        }
        const uint32_t size = GetInternalQueue(q)->Peek()->GetSize();
        if (m_deficit[q] >= static_cast<int64_t>(size))
        {
            m_deficit[q] -= size;
            return Serve(q);
        }
        m_drrPos = (m_drrPos + 1) % nDrr;
        m_drrFresh = true;
    }

    // 3. Backlog blocked by gates / shapers: wake the queue disc later
    if (wake != NEVER && GetNPackets() > 0)
    {
        const Time delay = NanoSeconds(std::max<int64_t>(wake - now, 1));
        if (!m_wakeEvent.IsPending() || Simulator::GetDelayLeft(m_wakeEvent) > delay)
        {
            m_wakeEvent.Cancel();
            m_wakeEvent = Simulator::Schedule(delay, &QueueDisc::Run, this);
        }
    }
    return nullptr;
}

bool
CeragonQosQueueDisc::CheckConfig()
{
    NS_LOG_FUNCTION(this);
    if (GetNQueueDiscClasses() > 0)
    {
        NS_LOG_ERROR("CeragonQosQueueDisc cannot have classes");
        return false;
    }
    if (GetNPacketFilters() > 0)
    {
        NS_LOG_ERROR("CeragonQosQueueDisc classifies internally (no packet filters)");
        return false;
    }
    if (GetNInternalQueues() == 0)
    {
        ObjectFactory factory;
        factory.SetTypeId("ns3::DropTailQueue<QueueDiscItem>");
        factory.Set("MaxSize", QueueSizeValue(QueueSize(QueueSizeUnit::PACKETS, m_queueLimit)));
        for (uint32_t i = 0; i < N_QUEUES; ++i)
        {
            AddInternalQueue(factory.Create<InternalQueue>());
        }
    }
    if (GetNInternalQueues() != N_QUEUES)
    {
        NS_LOG_ERROR("CeragonQosQueueDisc needs exactly 8 internal queues");
        return false;
    }
    return true;
}

void
CeragonQosQueueDisc::InitializeParams()
{
    NS_LOG_FUNCTION(this);
    m_deficit.fill(0);
    m_lastRefillNs = Simulator::Now().GetNanoSeconds();
    for (auto& s : m_shapers)
    {
        s.tokens = s.burstBytes;
    }
}

} // namespace ns3
