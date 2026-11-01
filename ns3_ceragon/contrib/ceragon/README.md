# `contrib/ceragon` — Ceragon Portfolio Functional Twin for ns-3

An ns-3 (3.45) contrib module that emulates the **functional behaviour** of the
whole Ceragon / Siklu wireless-transport portfolio, using the same product
catalog, feature gating and control domains as the CER-Intent TeraFlowSDN
RESTCONF adapter (`ceragon_tfs_adapter/portfolio.py`).

| Family | Models | API flavor | Twinned behaviour |
|---|---|---|---|
| FibeAir IP-20 | IP-20C, IP-20C-HP, IP-20S, IP-20E, IP-20V, IP-20N, IP-20A, IP-20A-LH, IP-20G, IP-20GX | `ceraos` | 4096QAM hitless ACM, XPIC 2+0, multi-carrier, 1+1 HSB / SD, ATPC, PTP/SyncE, MACsec |
| IP-50 | IP-50C, IP-50CX, IP-50E, IP-50EX, IP-50EXA, IP-50FX | `ceraos` | + Multi-Band (E-band + MW bonded), carrier sleep, nodal routing |
| IP-100 | IP-100E | `ceraos` | dual-carrier E-band, 1024QAM, 25 Gb/s |
| EtherHaul | EH-614TX … EH-8020FX | `siklu_eh` | E-band / V-band PtP, 64QAM, FDD/TDD, AES/MACsec |
| MultiHaul TG | MH-T260/T261/T265/T280, MH-N265/N366/N367 | `siklu_tg` | 802.11ad MCS1–12, 60 GHz O2 absorption, beamforming, pole sway, beam tracking, topology scan, mesh, active-backup |

Unlisted variants (`IP-50XYZ`, `EH-9010FX`, `MH-N368`, …) resolve to a family
fallback, exactly like the adapter.

## Layout

```
contrib/ceragon/
├── CMakeLists.txt
├── model/
│   ├── ceragon-portfolio.{h,cc}        # 31 models + 5 family fallbacks, resolution, gating
│   ├── ceragon-acm.{h,cc}              # QAM & 802.11ad MCS tables, hysteresis ACM, BER/PER
│   ├── ceragon-propagation.{h,cc}      # ITU-R P.525/P.676/P.838/P.530, XPD, weather model
│   ├── ceragon-radio-channel.{h,cc}    # hop geometry, impairments, delivery
│   ├── ceragon-radio-net-device.{h,cc} # THE radio twin
│   ├── ceragon-qos-queue-disc.{h,cc}   # 8 CoS SP+DRR, PIR shapers, 802.1Qbv/Qbu
│   ├── ceragon-oran-xhaul.{h,cc}       # Split 7.2x eCPRI sizing
│   └── ceragon-radio-header.{h,cc}
├── helper/
│   ├── ceragon-helper.{h,cc}           # portfolio-driven hop installation
│   └── ceragon-twin-helper.{h,cc}      # .twin topology -> network, events, telemetry, JSON
├── examples/                           # 6 scenarios + topologies/metro-ring.twin
├── test/ceragon-test-suite.cc          # 11 test cases
└── doc/ceragon.rst                     # ns-3 model documentation (Sphinx)
```

## Install

```bash
cp -r contrib/ceragon  <ns-3.45>/contrib/
cd <ns-3.45>
./ns3 configure --enable-examples --enable-tests      # or --enable-modules=ceragon
./ns3 build
./test.py -s ceragon                                   # or: ./ns3 run "test-runner --suite=ceragon"
```

Dependencies: `core network internet traffic-control mobility point-to-point applications flow-monitor`.

## Quick start

```bash
./ns3 run "ceragon-portfolio-twin --rain=60"                       # every product, clear vs storm
./ns3 run "ceragon-multiband-rain --distance=3000 --peakRain=120"  # IP-50EX vs EH-8010FX
./ns3 run "ceragon-tsn-fronthaul --mode=tsn"                       # fifo | qos | tsn
./ns3 run "ceragon-terragraph-mesh"                                # TG mesh, sway, reroute, scan
./ns3 run "ceragon-protection-switchover"                          # 1+0 vs HSB vs SD
./ns3 run "ceragon-twin-from-file --topology=contrib/ceragon/examples/topologies/metro-ring.twin --simTime=12 --telemetry=t.csv"
./ns3 run "ceragon-twin-from-file --listPortfolio"
```

## C++ API in 10 lines

```cpp
Ptr<CeragonWeatherModel> weather = CreateObject<CeragonWeatherModel>();
weather->ScheduleRainEvent(Seconds(5), Seconds(10), 90.0);     // storm peaking at 90 mm/h
CeragonHelper ceragon;
ceragon.SetWeatherModel(weather);
CeragonLinkConfig cfg;
cfg.modelA = "IP-50EX";  cfg.distanceM = 3000;                 // Multi-Band E-band + 18 GHz
cfg.protection = CeragonProtectionMode::HSB_1PLUS1;
NetDeviceContainer radios = ceragon.Install(a, b, cfg);
internet.Install(nodes);  ceragon.InstallQos(radios);  ipv4.Assign(radios);
```

Control at run time (same domains as the TFS adapter `set_config`):
`SetCarrierFrequency`, `SetCarrierTxPower`, `SetCarrierModulationRange`,
`SetAdaptiveModulation`, `SetAtpc`, `SetCarrierSleep`, `SetMacsec`, `SetSyncMode`,
`FailRadioUnit` / `RestoreRadioUnit` / `ForceSwitchover`, `ApplyPoleSway`,
`StartTopologyScan`, and on the queue disc `SetQueueShaper`, `SetQueueWeight`,
`SetDscpQueue`, `AddGateControlEntry`.

Telemetry (same data the adapter streams northbound): `GetStatusJson()`, and
trace sources `ModulationChange`, `RfSample`, `Capacity`, `PowerConsumption`,
`TimeError`, `ProtectionSwitch`, `LinkState`, `BeamMisalignment`.

See [`doc/ceragon.rst`](doc/ceragon.rst) for the models, equations, attributes,
limitations and validation.
