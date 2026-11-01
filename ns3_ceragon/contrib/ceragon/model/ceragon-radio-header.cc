/*
 * Copyright (c) 2026 Ceragon Networks Ltd.
 *
 * SPDX-License-Identifier: GPL-2.0-only
 */
#include "ceragon-radio-header.h"

namespace ns3
{

NS_OBJECT_ENSURE_REGISTERED(CeragonRadioHeader);

TypeId
CeragonRadioHeader::GetTypeId()
{
    static TypeId tid = TypeId("ns3::CeragonRadioHeader")
                            .SetParent<Header>()
                            .SetGroupName("Ceragon")
                            .AddConstructor<CeragonRadioHeader>();
    return tid;
}

TypeId
CeragonRadioHeader::GetInstanceTypeId() const
{
    return GetTypeId();
}

CeragonRadioHeader::CeragonRadioHeader()
    : m_protocol(0),
      m_flags(0)
{
}

void
CeragonRadioHeader::SetProtocol(uint16_t protocol)
{
    m_protocol = protocol;
}

uint16_t
CeragonRadioHeader::GetProtocol() const
{
    return m_protocol;
}

void
CeragonRadioHeader::SetFlags(uint8_t flags)
{
    m_flags = flags;
}

uint8_t
CeragonRadioHeader::GetFlags() const
{
    return m_flags;
}

void
CeragonRadioHeader::Print(std::ostream& os) const
{
    os << "proto=0x" << std::hex << m_protocol << std::dec << " flags=" << +m_flags;
}

uint32_t
CeragonRadioHeader::GetSerializedSize() const
{
    return 4;
}

void
CeragonRadioHeader::Serialize(Buffer::Iterator start) const
{
    start.WriteHtonU16(m_protocol);
    start.WriteU8(m_flags);
    start.WriteU8(0);
}

uint32_t
CeragonRadioHeader::Deserialize(Buffer::Iterator start)
{
    m_protocol = start.ReadNtohU16();
    m_flags = start.ReadU8();
    start.ReadU8();
    return 4;
}

} // namespace ns3
