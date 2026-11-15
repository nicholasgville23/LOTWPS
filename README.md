# BMH-NOAA-Weather-Radio-LOTIEM-and-LOTWPS

Python 3.12 desktop workstation prototype for the LOT Weather Processing System (LOTWPS), LOTIEM receiving-side workflow, and two **simulated** Northwest Indiana weather-radio station profiles.

This repository now contains a runnable Python/Tkinter scaffold. It retrieves real-time weather information from the public National Weather Service API; it does not claim to be an official NOAA/NWS system and it does not control a radio transmitter.

## Included in this first build

- KLOT LOTIEM TEXT WORKSTATION window with product draft editor, WMO-style header helper, destination checkboxes and right-click segment actions.
- WarnGen/WatchGen draft composer for user-entered hazard details.
- BMH local message queue and ticker preview.
- WXJ75 (Valparaiso) and KBB58 (Gary) station profiles, both configured for America/Chicago local time.
- Live NWS point metadata, seven-day forecast, hourly forecast, active alerts and latest observation retrieval.
- Alert priority ordering: Emergency, Warning, Watch, Advisory, Statement.
- Local SAPI voice playback for installed Windows voices such as David and Zira.
- Manual local briefing loop with Start and Stop controls.
- Settings for the NWS User-Agent, refresh interval, station endpoint and VoiceText Editor path.

The code currently supports English (en-US). Forecast normals/records, full regional roundup, marine forecast rendering, polygon drawing, durable queue storage and outbound distribution adapters are roadmap items rather than completed features.

## Run on Windows

1. Install Python 3.12 from python.org and ensure Tcl/Tk is included.
2. Open PowerShell in this repository.
3. Create and activate a virtual environment:

   py -3.12 -m venv .venv

   .\.venv\Scripts\Activate.ps1

4. Install the app and optional SAPI integration:

   python -m pip install --upgrade pip

   pip install -e ".[windows-sapi]"

5. Open the Settings tab and set a descriptive NWS User-Agent that includes a contact email or URL.
6. Run the application:

   python -m lotwps

The app uses only Python's standard library for its NWS HTTP client and Tkinter UI. The optional pywin32 dependency enables Windows SAPI voice selection and playback.

## Station configuration

Edit config/stations.json to change station IDs, station coordinates, IANA time zones, coverage labels and optional marine settings. The supplied station coordinates are approximate city coordinates used to discover the current NWS grid via the NWS points endpoint; the application then uses the grid URL returned by NWS.

The configured RF frequencies are display metadata for the simulated station profiles only. No transmission hardware or RF driver is included.

## VoiceText Paul, David and Zira

David and Zira are selected from voices installed in Windows SAPI. Paul is selected from SAPI if a matching Paul token is installed. If it is not installed as a SAPI voice, LOTWPS can open the VoiceText Editor executable selected in Settings. The current code does not assume that VTEditor_ENG.exe accepts command-line speech text, because that interface has not been verified.

## EAS Tools

EAS Tools is an independent project at https://eas.tools and https://github.com/wagwan-piffting-blud/EAS-Tools. Its own README describes it as an EAS/SAME decoder, encoder, text-crawl and audio toolkit for lab, testing, hobbyist and educational use.

LOTWPS links to EAS Tools for reference only. LOTWPS does **not** generate or transmit SAME headers, EAS Attention Signals, 1050 Hz alert tones, or EOM signal sequences. FCC rules restrict transmission of EAS codes and Attention Signals, including simulations, to specified permitted uses. Do not send EAS-related tones or headers over broadcast, RF, cable, public address or another public system without the required authorization.

## System boundaries

- NWS API data is real and may be delayed, revised or unavailable. Always check the official NWS product before taking action.
- The Text Workstation and WarnGen/WatchGen screens create editable drafts; they do not issue official NWS warnings.
- The BMH queue is in-memory and local to this app. The TCP status button checks whether a port accepts a connection and sends no payload.
- Email, IEMBOT, website/outlet publishing, official AWIPS integration, encrypted station transport and RF transmission are not implemented.
- The local voice loop is an audio preview facility, not an operational life-safety warning service.

See docs/ROADMAP.md for the next implementation stages.
