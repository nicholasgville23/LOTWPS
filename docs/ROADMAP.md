# LOTWPS / LOTIEM implementation roadmap

## Delivered in the initial workstation scaffold

- Python 3.12 package with a Tkinter desktop shell.
- Configurable WXJ75 and KBB58 station profiles and per-station IANA time zones.
- Live NWS point lookup, seven-day point forecast, hourly forecast, active alerts and latest observation.
- Alert ordering: Emergency, Warning, Watch, Advisory, Statement, then other products.
- WMO-style draft header helper and local text editor with basic segment operations.
- WarnGen/WatchGen draft composer, explicitly separate from official AWIPS WarnGen.
- BMH in-memory queue, editable ticker preview and TCP reachability check that sends no payload.
- Manually controlled local SAPI audio briefing loop.

## Planned work requiring separate validation

1. Add a proper editable station/coverage editor and validate UGC/zone membership against authoritative NWS data.
2. Add full forecast products, hourly regional station roundups, and marine products only for configured coastal stations.
3. Add HWO and climate-product readers, then parse normals/records only where the underlying source actually provides them.
4. Add a map/polygon editor and geometry validation for draft products; do not describe the result as official WarnGen.
5. Add authenticated, encrypted BMH message transport after the station-server protocol and trust model are documented.
6. Add queue persistence, audit records, expiry handling and operator review workflows.
7. Add a verified VoiceText Paul automation adapter only after the vendor-supported interface is identified. The VTEditor executable is currently launched as a manual editor; no undocumented command line is assumed.
8. Add localization. The first build is English (en-US) only.
9. Add integrations for email, IEMBOT and web outlets only after their APIs, credentials and authorization are configured.

## Safety boundary

This project retrieves genuine NWS data but is not an official NWS/NOAA, NWS AWIPS, IPAWS or EAS participant system. The first build has no RF transmitter control, SAME header/attention-signal/EOM audio generation, 1050 Hz alert-tone generator, or public dispatch transport. The local audio loop uses Windows SAPI only. It is for local development and preview, not a life-safety service.

The EAS Tools project documents lab/testing/educational use and warns against unauthorized transmission of EAS signals. FCC 47 CFR 11.45 restricts transmission of EAS codes and attention signals (including simulations) to specified permitted circumstances. See the EAS Tools README and the FCC enforcement advisory linked from the project documentation.
