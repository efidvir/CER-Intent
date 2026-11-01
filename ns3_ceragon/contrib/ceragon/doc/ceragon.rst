.. include:: replace.txt
.. highlight:: cpp

Ceragon Functional Twin Module
------------------------------

.. heading hierarchy:
   ------------- Chapter
   ************* Section (#.#)
   ============= Subsection (#.#.#)
   ############# Paragraph (no number)

The ``ceragon`` module is a *functional digital twin* of the Ceragon Networks /
Siklu wireless-transport portfolio for |ns3|. Every product handled by the
CER-Intent TeraFlowSDN RESTCONF adapter (``ceragon_tfs_adapter/portfolio.py``)
can be instantiated as an ns-3 ``NetDevice`` whose capacity, latency,
reliability and control knobs behave like the real radio:

* **FibeAir IP-20** (IP-20C, IP-20C-HP, IP-20S, IP-20E, IP-20V, IP-20N, IP-20A,
  IP-20A-LH, IP-20G, IP-20GX)
* **IP-50** (IP-50C, IP-50CX, IP-50E, IP-50EX, IP-50EXA, IP-50FX)
* **IP-100** (IP-100E)
* **EtherHaul** (EH-614TX, EH-710TX, EH-1200TX, EH-1200FX, EH-2500FX,
  EH-8010FX, EH-8020FX)
* **MultiHaul TG** (MH-T260, MH-T261, MH-T265, MH-T280, MH-N265, MH-N366,
  MH-N367)

plus family fallbacks for unlisted variants (``IP-50XYZ``, ``EH-9010FX``,
``MH-N368`` ...), resolved with the same vendor-string normalisation and
longest-prefix rules as the TFS adapter.

Model Description
*****************

The source code lives in ``contrib/ceragon``. The module is organised as:

=====================================  ==============================================
File                                   Role
=====================================  ==============================================
``model/ceragon-portfolio.{h,cc}``     Product catalog, resolution, feature gating
``model/ceragon-acm.{h,cc}``           ACM profiles (QAM / 802.11ad MCS), BER model
``model/ceragon-propagation.{h,cc}``   ITU-R P.525/P.676/P.838/P.530, weather model
``model/ceragon-radio-channel.{h,cc}`` Radio hop: geometry, impairments, delivery
``model/ceragon-radio-net-device.*``   The radio twin (carriers, ACM, ATPC, ...)
``model/ceragon-qos-queue-disc.*``     8-CoS SP+DRR scheduler, shapers, 802.1Qbv
``model/ceragon-oran-xhaul.{h,cc}``    O-RAN Split 7.2x eCPRI dimensioning
``helper/ceragon-helper.{h,cc}``       Portfolio-driven link installation
``helper/ceragon-twin-helper.{h,cc}``  Topology-file network twin + JSON report
=====================================  ==============================================

Design
======

A Ceragon radio hop is a ``CeragonRadioChannel`` connecting exactly two
``CeragonRadioNetDevice`` instances. Each device is one end of the hop and owns
the *transmit direction* towards its peer. Every ``LinkUpdateInterval``
(default 10 ms) the device runs its link engine:

1. **Link budget per carrier**

   .. math::

      RSL = P_{tx} + G_{tx} + G_{rx} - FSPL(f,d) - \gamma_{gas}(f)\,d
            - A_{rain}(f,d,R,pol) - L_{misc} + F

   with free-space loss (ITU-R P.525), sea-level gaseous attenuation including
   the 15 dB/km oxygen peak at 60 GHz (ITU-R P.676), rain attenuation
   :math:`\gamma_R = k R^\alpha` with the ITU-R P.838-3 coefficients and the
   ITU-R P.530-17 cell-extent reduction on long hops, and a Gaussian
   multipath/scintillation fading sample :math:`F` (``FadingStdDb``).
   Space-Diversity protection draws two independent fading samples and keeps
   the best (selection diversity).

2. **SINR** against the thermal noise floor :math:`-174 + 10\log_{10}B + NF`,
   external interference (``InterferenceDbm``) and, for XPIC carrier pairs
   (same channel, H + V), the rain-degraded cross-polar discrimination of
   ITU-R P.530 improved by the XPIC cancellation factor (``XpicImprovement``).

3. **ATPC / Green-ATPC**: the transmit power converges by 1 dB per update
   towards ``AtpcTargetRsl`` within ``[MinTxPower, MaxTxPower]``.

4. **Hitless ACM** per carrier (``CeragonAcmController``): immediate downshift
   to the highest profile whose threshold is met, upshift only with
   ``AcmHysteresis`` margin, and outage when the SINR falls below the ACM floor.
   CeraOS / EtherHaul use the BPSK..4096QAM table; MultiHaul TG uses the
   IEEE 802.11ad SC-PHY MCS1..MCS12 table (Terragraph link adaptation).

5. **Carrier rate**

   .. math::

      R_{QAM} = B \cdot \log_2 M \cdot \frac{r_c}{1+\beta}, \qquad
      R_{MCS} = R_{PHY}(MCS)\cdot \frac{B}{2160\,\mathrm{MHz}} \cdot \eta_{MAC}

   (code rate 0.9, roll-off 0.15, Terragraph MAC efficiency 0.8), multiplied
   by ``TddShare`` on TDD products.

6. **L1 bonding**: the aggregate capacity is the sum of all carriers (Multi-
   Carrier ABC, XPIC 2+0, Multi-Band E-band + MW) capped at the product's
   catalog capacity. Frames are serialised at the aggregate rate; the frame
   error probability is computed per carrier from the SINR margin above the
   active profile threshold (BER waterfall of 1.5 decades/dB from 1e-6) and
   the share of the frame carried by that carrier.

7. **Energy**: :math:`P = P_{base} + \sum_{active}(P_{carrier} + P_{tx}/\eta_{PA})`
   plus a powered standby unit when protection is configured. With carrier
   sleep enabled, secondary carriers are switched off after 10 consecutive
   intervals below ``CarrierSleepLoadFraction`` of the primary capacity and
   woken when the offered load exceeds 80 %.

8. **Sync**: in PTP / SyncE modes the device exposes a time error made of a
   constant part (cTE, G.8273.2 class) and a Gaussian dynamic part (dTE); when
   the radio link is down the clock is in holdover and the time error grows at
   ``HoldoverDriftNsPerS``.

Functional features and the corresponding control domain of the TFS adapter:

===============  ===========================================  ==============================
TFS domain       ns-3 API                                     Behaviour
===============  ===========================================  ==============================
radio            ``SetCarrierFrequency/Bandwidth/TxPower``    re-evaluated link budget
acm              ``SetCarrierModulationRange``,               ACM floor / ceiling, fixed mod
                 ``SetAdaptiveModulation``
qos / slice      ``CeragonQosQueueDisc::SetQueueShaper``,     SP + DRR, PIR shaping per CoS
                 ``SetQueueWeight``, ``SetDscpQueue``
tsn              ``AddGateControlEntry``, ``FramePreemption``  802.1Qbv GCL, guard band, Qbu
beamforming      ``ApplyPoleSway``, ``StartTopologyScan``,    array gain, misalignment loss,
                 ``SetBeamTracking``                          tracking, topology scan
multiband        ``CeragonLinkConfig::multiband``             E-band + MW bonded carriers
protection       ``SetProtectionMode``, ``FailRadioUnit``,    1+1 HSB (50 ms), SD (hitless),
                 ``ForceSwitchover``                          TG active-backup (100 ms)
xpic             ``CeragonLinkConfig::xpic``                  H/V co-channel, XPD under rain
sync             ``SetSyncMode``                              cTE/dTE, holdover drift
security         ``SetMacsec``                                32 B SecTAG+ICV per frame
energy           ``SetAtpc``, ``SetCarrierSleep``             Green ATPC, carrier sleep
oran_xhaul       ``CeragonOranXhaul::EcpriBitRate``           Split 7.2x U-plane sizing
===============  ===========================================  ==============================

Feature gating is identical to the TFS adapter: ``CeragonHelper::ConfigureDevice``
calls ``CeragonPortfolio::CheckConfigSupport`` and refuses (with a log warning)
features that the product does not have, e.g. beamforming on an IP-20C or
Multi-Band on an EtherHaul.

Scope and Limitations
=====================

* The catalog data (capacities, bands, features) is nominal public-catalog
  information; only the MH-T261 southbound behaviour was verified against
  lab hardware. Validate against datasheets before using results for planning.
* Rain is modelled as a regional time series (``CeragonWeatherModel``) shared
  by the channels that reference it; there is no spatial rain-cell field.
* The PHY is abstracted (no symbol-level modem); the BER waterfall is generic.
* MultiHaul TG point-to-multipoint sectors are modelled as one hop per
  DN-CN pair; TDD air-time sharing between sectors is a fixed ``TddShare``.
* PTP is a time-error budget model, not a packet-level 1588 implementation.

References
==========

* ITU-R P.525-4, P.676-13, P.838-3, P.530-18 (propagation for fixed links)
* IETF RFC 8561 (microwave radio link YANG), IEEE 802.1Qbv/Qbu, IEEE 802.1AE
* ITU-T G.8275.1, G.8273.2, G.8262 (timing)
* O-RAN WG4 CUS-plane specification (Split 7.2x)
* IEEE 802.11ad / Terragraph link adaptation

Usage
*****

Helpers
=======

``CeragonHelper`` creates a hop and configures both radios from the portfolio::

  NodeContainer nodes;
  nodes.Create (2);
  Ptr<CeragonWeatherModel> weather = CreateObject<CeragonWeatherModel> ();
  weather->ScheduleRainEvent (Seconds (5), Seconds (10), 90.0); // storm, 90 mm/h peak

  CeragonHelper ceragon;
  ceragon.SetWeatherModel (weather);
  CeragonLinkConfig cfg;
  cfg.modelA = "IP-50EX";          // Multi-Band: E-band + 18 GHz bonded
  cfg.distanceM = 3000;
  cfg.protection = CeragonProtectionMode::HSB_1PLUS1;
  cfg.sync = CeragonSyncMode::PTP_BOUNDARY_CLOCK;
  NetDeviceContainer radios = ceragon.Install (nodes.Get (0), nodes.Get (1), cfg);

  InternetStackHelper internet;
  internet.Install (nodes);
  QueueDiscContainer qos = ceragon.InstallQos (radios);   // 8-CoS scheduler
  Ipv4AddressHelper ip ("10.0.0.0", "255.255.255.252");
  ip.Assign (radios);

``CeragonTwinHelper`` builds a complete network from a declarative topology
(produced from TeraFlowSDN by ``tools/tfs_to_ceragon_twin.py``)::

  CeragonTwinHelper twin;
  twin.LoadTopologyFile ("metro-ring.twin");
  twin.EnableTelemetry (MilliSeconds (100), "telemetry.csv");
  twin.Build ();
  twin.Run (Seconds (12));
  twin.PrintReport (std::cout);  // JSON between ===CERAGON_TWIN_METRICS_START/END===

Topology file grammar::

  node  <name> <model|host|site> <x_m> <y_m>
  link  <a> <b> [model=|modelA=|modelB=..] [freq=MHz] [bw=MHz] [carriers=N]
               [xpic=0|1] [multiband=0|1] [distance=m] [maxmod=..] [minmod=..]
               [protection=none|hsb|sd|ab] [macsec=0|1] [atpc=0|1] [rsl=dBm]
               [sync=none|bc|tc|synce] [hc=0|1] [sleep=0|1] [qos=0|1]
               [strict=N] [fading=dB] [intf=dBm] [antenna=m]
  wire  <a> <b> [rate=10Gbps] [delay=5us]
  rain  <start_s> <duration_s> <peak_mm_h>  |  rain base <mm_h>
  flow  <name> <src> <dst> <rate> [dscp=..] [size=..] [start=..] [stop=..]
  tsn   <a> <b> <cycle_us> <express_window_us> [express_mask=0x80]
  slice <a> <b> <cos> <pir> [dscp=d1,d2] [weight=w]
  event <t_s> <a> <b> <action> [value]

Event actions: ``fail-unit``, ``restore-unit``, ``switchover``, ``pole-sway``,
``topo-scan``, ``tx-power``, ``freq``, ``min-mod``, ``max-mod``,
``interference``, ``carrier-off``, ``carrier-on``, ``macsec``, ``atpc``,
``adaptive``. When ``SetDynamicRouting(true)`` (default) a radio link going
down disables the IPv4 interface and global routes are recomputed, so mesh and
ring topologies reroute around faded links.

Attributes
==========

``ns3::CeragonRadioNetDevice``: ``ProductModel``, ``LinkUpdateInterval``,
``RadioLatency``, ``AntennaGain``, ``NoiseFigure``, ``MinTxPower``,
``MaxTxPower``, ``AtpcEnabled``, ``AtpcTargetRsl``, ``XpicEnabled``,
``XpicImprovement``, ``TddShare``, ``CapacityLimit``, ``AcmHysteresis``,
``L1OverheadBytes``, ``HsbSwitchoverTime``, ``ActiveBackupSwitchoverTime``,
``BeamResidualError``, ``BeamTrackingRange``, ``BeamTrackingInterval``,
``TopologyScanDuration``, ``MacsecOverhead``, ``HeaderCompressionSaving``,
``BasePower``, ``CarrierPower``, ``PaEfficiency``, ``CarrierSleepLoadFraction``,
``ConstantTimeErrorNs``, ``DynamicTimeErrorSigmaNs``, ``HoldoverDriftNsPerS``.

``ns3::CeragonRadioChannel``: ``Distance``, ``InterferenceDbm``,
``FadingStdDb``, ``MiscLossDb``, ``UsePathReduction``, ``WeatherModel``.

``ns3::CeragonQosQueueDisc``: ``MaxSize``, ``QueueLimit``,
``StrictPriorityQueues``, ``Quantum``, ``GuardBand``, ``FramePreemption``,
``ExpressQueues``.

``ns3::CeragonWeatherModel``: ``RainRate``.

Traces
======

``CeragonRadioNetDevice`` trace sources: ``MacTx``, ``MacTxDrop``, ``MacRx``,
``PhyTxBegin``, ``PhyTxEnd``, ``PhyTxDrop``, ``PhyRxDrop``, ``Sniffer``,
``ModulationChange`` (carrier, old, new), ``RfSample`` (carrier, RSL, SINR),
``ProtectionSwitch`` (from, to), ``LinkState`` (up), ``Capacity``,
``PowerConsumption``, ``TimeError``, ``BeamMisalignment``.

Examples
========

* ``ceragon-portfolio-twin``: one hop per product, clear-sky vs. storm table.
* ``ceragon-multiband-rain``: IP-50EX Multi-Band vs. EH-8010FX under a storm.
* ``ceragon-tsn-fronthaul``: O-RAN 7.2x fronthaul with FIFO / QoS / 802.1Qbv.
* ``ceragon-terragraph-mesh``: MultiHaul TG mesh, pole sway, rerouting, scan.
* ``ceragon-protection-switchover``: 1+0 vs. 1+1 HSB vs. 1+1 SD.
* ``ceragon-twin-from-file``: generic topology-file driver (CER-Intent entry
  point), ``--listPortfolio`` dumps the catalog as JSON.

Validation
**********

The ``ceragon`` test suite (``./test.py -s ceragon``) checks:

* catalog size, alias/vendor-string resolution, family fallbacks, single
  lab-verified model and capability gating;
* ACM thresholds, hysteresis, outage, carrier rates and BER model;
* ITU-R propagation values (FSPL, 60 GHz O2 peak, P.838 at 80 GHz, P.530
  reduction, XPD, antenna gain, noise floor) and the weather profile;
* IP-20C XPIC capacity (2 Gb/s cap) and hitless ACM downshift in rain;
* 2 Gb/s end-to-end UDP over EH-8010FX with EF traffic in CoS 7;
* IP-50EX Multi-Band: E-band outage at 120 mm/h with MW carrier surviving;
* 1+1 HSB 50 ms switchover vs. unprotected failure;
* MultiHaul TG pole sway, beam tracking recovery and topology-scan re-acquisition;
* 802.1Qbv gate states over the cycle and DSCP classification;
* Green carrier sleep, ATPC power reduction, PTP cTE and holdover drift;
* the topology-file twin (build, flows, rain, control timeline, report) and
  O-RAN Split 7.2x bit-rate dimensioning.
