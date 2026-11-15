# BMH NOAA Weather Radio — LOTWPS / LOTIEM Framework

Python 3.12 starter framework for the Chicago / Northeast Illinois / Northwest Indiana weather-processing workstation and BMH-style local audio test console.

- LOTWPS — LOT Weather Processing System: sender-side weather retrieval, text-product editing, alert prioritization, product queue, and forecaster tools.
- LOTIEM — Chicago Illinois Integrated Emergency Manager: receiving-side message ledger and future distribution gateway boundary. The earlier project notes used “Chicago Illinois Iowa Environmental Mesonet” as a legacy expansion.
- BMH — station registry, ticker, queue, test SAME/EAS file builder, and local playout controls.

## Original project scope

The owner's original framework description identifies LOTWPS as the sender side, with a forecaster text workstation and AWIPS/WarnGen-style polygon workflow. LOTIEM is the receiving side, intended to receive LOTWPS products and route approved messages to downstream BMH, WwA, officials, and public outlets. The project is transitioning the configured office/station identity from IWX to LOT.

Initial simulated station plan:
- WXK75 — Valparaiso / Porter Township, Indiana; 162.400 MHz.
- KBB58 — Gary / Lake Township, Indiana; 162.425 MHz.
- WXK89 — secondary node represented in the sample JSON configuration.

These names, locations, coverage areas, and station details are project inputs. Verify exact authorized coverage, SAME/FIPS/UGC values, frequency assignments, and legal authorization before any real-world integration.

## Safety boundary

This repository is not an NOAA/NWS system and is not approved for life-safety use. It does not transmit RF, connect to an EAS encoder, send IPAWS/EAS messages, or dispatch messages to officials, email, IEMBOT, or public websites. Station controls are in-memory simulations. Generated SAME/1050-Hz audio is for local development and lab testing only. Do not connect generated alerts to a real transmitter or public alert distribution system. Always use official NWS/NOAA warning channels for real emergencies.

## Implemented in this starter

- Tkinter GUI with KLOT LOTIEM TEXT WORKSTATION, WMO/AWIPS header fields, draft segment actions, distribution toggles, active-alert view, and local message ledger.
- BMH Network tab with WXK75, KBB58, and WXK89 sample nodes, simulated station controller, operating modes, ticker text, local queue, and manual start/stop audio loop.
- AWIPS/WarnGen starter tab with coordinate polygon entry and local save. It is not an operational radar ingest or WarnGen integration.
- Official api.weather.gov point-forecast and active-alert client; point-derived forecast URLs; station-local time with IANA time zones; UGC listening-area filtering.
- Alert ordering: Emergency > Warning > Watch > Advisory > Statement. Tornado Emergency receives emergency priority.
- Local SAME/EAS test WAV generation: three header bursts, a 1050-Hz attention tone, optional synthesized speech, and three end-of-message bursts. This is a file only; there is no RF or EAS transport.
- Optional pyttsx3 / Windows SAPI adapter with configurable voice-name matching for Paul, David, and Zira.
- JSON configuration and local audit/message store.

## Requirements and setup

Windows 10/11 is recommended for Tkinter, Windows SAPI/pyttsx3, and local WAV playback. Python 3.12 is required. The core uses only the Python standard library.

PowerShell setup:
1. Create and activate a virtual environment: py -3.12 -m venv .venv, then .\.venv\Scripts\Activate.ps1.
2. Install: python -m pip install -e ".[windows,test]".
3. Copy config.example.json to config.json.
4. Replace the NWS User-Agent with an identifiable application name and contact email.
5. Verify station coordinates, time zones, UGC coverage and six-digit SAME county/FIPS codes.
6. Run: python run_workstation.py.

Optional TTS installation: python -m pip install -e ".[tts]". The Paul, David, and Zira profiles match installed Windows voices by name. Availability depends on the local host.

## VoiceText / NeoSpeech Paul

No proprietary engine, DLL, voice pack, or VTEditor_ENG.exe is included. The local path must be configured on the computer where it is installed and must not be committed to a public repository. VTEditor_ENG.exe may be a GUI editor rather than a command-line synthesis engine. Use a documented vendor CLI/SDK wrapper if one is available; the wrapper accepts {text}, {output}, and {voice} placeholders. Otherwise, use the installed SAPI adapter if NeoSpeech Paul is registered as a SAPI voice.

## Tests

Install the test extra and run python -m pytest. GitHub Actions runs the same tests on pushes and pull requests.

## Upstream references and licensing

See UPSTREAMS.md. The implementation is independently authored and does not copy source files or ship proprietary assets from upstream repositories. dondaplayer1/weather-radio-suite declares AGPL-3.0; directly copying or deriving code from that repository requires preserving its license and complying with its terms.

## Next integration milestones

1. Verify station coverage plans and SAME/FIPS/UGC mappings with authorized operators.
2. Implement authenticated LOTWPS-to-LOTIEM exchange on a separate access-controlled network.
3. Add reviewed email, website, and IEMBOT adapters with authentication, audit trail, deduplication, and human approval gates.
4. Add verified climate records, regional observations, and fully formatted products for all configured stations.
5. Integrate radar/geospatial data and official polygon sources behind a reviewed AWIPS adapter.
6. Complete security, load, recovery, and failover testing before operational deployment.
