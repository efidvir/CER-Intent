/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef CERAGON_RADIO_HEADER_H
#define CERAGON_RADIO_HEADER_H

#include "ns3/header.h"

namespace ns3
{

/**
 * @ingroup ceragon
 * Minimal radio frame header carried over the Ceragon air interface
 * (EtherType of the payload + frame flags).
 */
class CeragonRadioHeader : public Header
{
  public:
    static TypeId GetTypeId();
    TypeId GetInstanceTypeId() const override;
    CeragonRadioHeader();

    void SetProtocol(uint16_t protocol);
    uint16_t GetProtocol() const;
    void SetFlags(uint8_t flags);
    uint8_t GetFlags() const;

    void Print(std::ostream& os) const override;
    uint32_t GetSerializedSize() const override;
    void Serialize(Buffer::Iterator start) const override;
    uint32_t Deserialize(Buffer::Iterator start) override;

    static constexpr uint8_t FLAG_MACSEC = 0x01;     //!< frame protected by MACsec
    static constexpr uint8_t FLAG_COMPRESSED = 0x02; //!< header de-duplication applied

  private:
    uint16_t m_protocol;
    uint8_t m_flags;
};

} // namespace ns3

#endif /* CERAGON_RADIO_HEADER_H */
