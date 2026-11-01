/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * Ceragon CeraOS-style hierarchical QoS scheduler with IEEE 802.1Qbv
 * time-aware shaping (TSN) for the ns-3 functional twin.
 */
#ifndef CERAGON_QOS_QUEUE_DISC_H
#define CERAGON_QOS_QUEUE_DISC_H

#include "ns3/data-rate.h"
#include "ns3/event-id.h"
#include "ns3/nstime.h"
#include "ns3/queue-disc.h"

#include <array>
#include <vector>

namespace ns3
{

class CeragonRadioNetDevice;

/**
 * @ingroup ceragon
 * Eight class-of-service queues per radio interface (CoS 0..7):
 *  - classification by DSCP (configurable map) or SocketPriorityTag
 *  - the top "StrictPriorityQueues" CoS queues are served in strict priority
 *  - remaining queues are served by Deficit Round Robin with per-queue weights
 *  - optional per-queue PIR token-bucket shaper (transport slice bandwidth)
 *  - optional IEEE 802.1Qbv gate control list (GCL) with guard band and
 *    IEEE 802.1Qbu frame-preemption approximation for express traffic
 */
class CeragonQosQueueDisc : public QueueDisc
{
  public:
    static TypeId GetTypeId();
    CeragonQosQueueDisc();
    ~CeragonQosQueueDisc() override;

    static constexpr uint32_t N_QUEUES = 8;

    /// Map a DSCP code point (0..63) to a CoS queue (0..7)
    void SetDscpQueue(uint8_t dscp, uint8_t queue);
    uint8_t GetDscpQueue(uint8_t dscp) const;
    /// DRR weight of a CoS queue
    void SetQueueWeight(uint8_t queue, uint32_t weight);
    /**
     * Peak-rate shaper on a CoS queue (slice bandwidth).
     * @param queue the CoS queue
     * @param pir peak information rate (0 disables)
     * @param burstBytes bucket depth
     */
    void SetQueueShaper(uint8_t queue, DataRate pir, uint32_t burstBytes);
    /**
     * Append an entry to the IEEE 802.1Qbv gate control list.
     * @param duration time interval of the entry
     * @param gateMask bit i set = gate of CoS queue i open
     */
    void AddGateControlEntry(Time duration, uint8_t gateMask);
    void ClearGateControlList();
    /// Base time of the GCL cycle
    void SetGateBaseTime(Time baseTime);
    Time GetGateCycleTime() const;
    /// Gate states at the current time
    uint8_t GetGateStates() const;
    /// Radio device (used for guard-band computation with the live ACM rate)
    void SetDevice(Ptr<CeragonRadioNetDevice> device);
    /// Express (preemptive) queue mask for 802.1Qbu
    void SetExpressQueues(uint8_t mask);

    uint32_t GetQueueLength(uint8_t queue) const;
    uint64_t GetDequeuedPackets(uint8_t queue) const;
    uint64_t GetGateBlockedEvents() const;

  private:
    bool DoEnqueue(Ptr<QueueDiscItem> item) override;
    Ptr<QueueDiscItem> DoDequeue() override;
    bool CheckConfig() override;
    void InitializeParams() override;
    void DoDispose() override;

    uint8_t ClassifyCos(Ptr<QueueDiscItem> item) const;
    bool Eligible(uint8_t queue, int64_t nowNs, int64_t& wakeNs);
    Ptr<QueueDiscItem> Serve(uint8_t queue);
    void RefillTokens(int64_t nowNs);
    uint8_t MaskAt(int64_t tNs, int64_t& nextChangeNs) const;
    int64_t NextGateOpen(uint8_t queue, int64_t nowNs) const;
    int64_t NextGateClose(uint8_t queue, int64_t nowNs) const;

    struct Shaper
    {
        double rateBps{0.0};
        double burstBytes{0.0};
        double tokens{0.0};
    };

    struct GclEntry
    {
        int64_t durationNs;
        uint8_t mask;
    };

    std::array<uint8_t, 64> m_dscpMap;
    std::array<uint32_t, N_QUEUES> m_weights;
    std::array<int64_t, N_QUEUES> m_deficit;
    std::array<Shaper, N_QUEUES> m_shapers;
    std::array<uint64_t, N_QUEUES> m_dequeued;
    std::vector<GclEntry> m_gcl;
    int64_t m_cycleNs;
    int64_t m_baseNs;
    int64_t m_lastRefillNs;
    uint32_t m_strictQueues;
    uint32_t m_quantum;
    uint32_t m_queueLimit;
    uint32_t m_drrPos;
    bool m_drrFresh;
    bool m_guardBand;
    bool m_preemption;
    uint8_t m_expressMask;
    uint64_t m_gateBlocked;
    EventId m_wakeEvent;
    Ptr<CeragonRadioNetDevice> m_device;
};

} // namespace ns3

#endif /* CERAGON_QOS_QUEUE_DISC_H */
