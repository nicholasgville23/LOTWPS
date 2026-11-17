# BMH-NOAA-Weather-Radio-LOTIEM-and-LOTWPS

A self-contained Windows simulator of the NOAA Weather Radio broadcast chain used
by the Chicago / Romeoville (KLOT) Weather Forecast Office. Everything runs on one
PC: the WXJ75 and KBB58 transmitters, the BMH network controller, the LOTIEM
distribution hub, the KLOT text workstation, and the CAVE-LOT AWIPS display.

All weather text, alerts, radar imagery and audio are **simulated**. No live NWS
feeds are downloaded, and nothing transmits over the air.

## What is included

| Window | Launch | Purpose |
| --- | --- | --- |
| NWR-1 receiver | `python run_lotwps.py radio` | NOAA Weather Radio face, three SAPI voices, EAS details channel, SAME alerts |
| BMH Network | `python run_lotwps.py bmh` | Global network controls, TRANSMIT, transmitter list, dispatch |
| WXJ75 Station Controller | `python run_lotwps.py station` | Eight tabs controlling one transmitter |
| KLOT LOTIEM Text Workstation | `python run_lotwps.py tw` | AWIPS headers, segments, WarnGen polygons, sent alerts |
| CAVE-LOT D2D / AWIPS II | `python run_lotwps.py awips` | Radar map, alert polygons, WarnGen tools, Text 1-5 |
| LOTIEM daemon | `python run_lotwps.py lotiem` | TCP/JSON distribution server on `127.0.0.1:6000` |
| Launcher | `python run_lotwps.py` | Button panel for the whole suite |

`python run_lotwps.py all` starts the radio, BMH, station controller, text
workstation and AWIPS windows together. Every app is also runnable directly, for
example `python apps/bmh_network.py`.

## Requirements

* Windows 10 or 11
* Python 3.12 with Tk 8.6 (python.org installer includes both)
* `pywin32` for SAPI speech synthesis (`pip install -r requirements.txt`)
* The VoiceText Paul editor (`VTEditor_ENG.exe`) is optional. Without it the
  broadcaster uses SAPI David with a slight pitch shift as a Paul stand-in.

Audio playback uses the standard-library `winsound` module, so no extra audio
package is needed.

## Install and run

```bat
cd "C:\Users\nicho\OneDrive\Documents\Default Project"
py -3.12 -m pip install -r requirements.txt
py -3.12 run_lotwps.py
```

The first run creates `config/settings.json` and the runtime folders under
`var/`. The defaults already describe the Valparaiso build:

* WXJ75, 162.400 MHz, Porter Township (active)
* KBB58, 162.425 MHz, Lake Township / Gary (active)
* WNG689, 162.450 MHz (inactive spare)
* LOTIEM at `192.168.10.144:6000`, BMH network status `ONLINE (1)`
* Central time with the correct CST/CDT label

## NOAA Weather Radio engine

`lotwps/weather.py` builds a deterministic, date-seeded weather scenario. Text is
stable within a day and changes from day to day. Products include:

* Seven-day zone forecast (`.TODAY...`, `.TONIGHT...` with county seats)
* Hourly regional roundup with extra stations
* Hazardous Weather Outlook, varied by season and region
* Marine forecast for LMZ740-LMZ745 (coastal zones only)
* Area Forecast Discussion, climate summary with normals and records
* Key messages, observations, and static station IDs

Alert priorities follow the NWR ladder: **Tornado Emergency > Warning > Watch >
Advisory > Statement > Routine**. Active alerts live in
`var/state/alerts.json` and are shared by every window.

The broadcast engine (`lotwps/broadcast.py`) walks an ordered cycle of tokens:

* static IDs: `STATION_ID`, `SHORT_ID`, `LONG_ID`, `EMR_STATION_ID`,
  `SLGT_STATION_ID`, `ADVANCE`, `OFF_AIR`, `PREPAREDNESS_ACTIONS`,
  `SEVERE_MESSAGE`, `CURRENT_TIME`
* special tokens: `@AUTO_ID`, `@ACTIVE_ALERTS`, `@SEVERE_DYNAMIC`,
  `@PRODUCT:ZFPLOT`, `@PRODUCT:AFDLOT`, `@AUTO_SEVERE_ID`,
  `@NEW_CON_ALERTS`, `@CAN_EXP_ALERTS`
* speech parts, pauses, SAME bursts, the 1050 Hz tone and EOM

Voice scripts are normalised for speech (callsigns spelled out, `mph` to "miles
per hour", `162.400` to "162.4 megahertz", AM/PM separated) and rendered to one
16 kHz mono 16-bit WAV per product under `var/audio/products`.

### Voices

| Key | Engine | Notes |
| --- | --- | --- |
| `paul` | VoiceText / SAPI fallback | Pre-rendered assets for static IDs; live SAPI David at `pitch="-3%"` elsewhere |
| `david` | SAPI | Microsoft David Desktop |
| `zira` | SAPI | Microsoft Zira Desktop |

`voices.paul.render_mode` in `config/settings.json` selects the behavior:

* `auto` - use Paul WAV assets for static IDs only (default)
* `assets` - always use the pre-rendered Paul assets when present
* `sapi` - always synthesize with the SAPI fallback

`VTEditor_ENG.exe` has no batch interface, so genuine Paul renders are produced
by exporting VTML and opening the editor. Static ID assets from the VoiceText
package are used directly.

### EAS / SAME

`lotwps/same.py` implements the over-the-air format:

```
ZCZC-ORG-EEE-PSSCCC-PSSCCC+TTTT-JJJHHMM-LLLLLLLL-
```

* 16 bytes of `0xAB` preamble before each header and before EOM
* 520.83 bps AFSK, mark 2083.3 Hz, space 1562.5 Hz
* each character framed with start/stop bits and sent twice
* headers repeated three times, then the 1050 Hz tone, then `NNNN` EOM three
  times

The WXJ75 SAME/EAS Builder can send a custom "This is a test.", select the
NE Illinois / NW Indiana UGC zones, preview the header, and fire the burst.

## KLOT text workstation

* AWIPS header block: `TTAAii`, `CCCC` (`KLOT`), `BBB` (`NOR`/`A`/`B`), BBB
  version, WSFO ID (`CHI`), product category, designator (`LOT`), addressee
  (`ALL`)
* New text message routing to BMH, Email, IEMBOT, and Websites & Outlets
* Segment right-click menu: Add, Edit, Remove, Combine, Add Hazard Segment, Add
  Hazard to Existing
* Hazard-segment builder with `HAZARD...` and `PRECAUTIONARY/PREPAREDNESS
  ACTIONS...` blocks
* WarnGen / WatchGen with map polygon drawing, Single Storm and Line of Storms
  modes, UGC resolution, preview, SAME issuance and bus publication
* AWIPS Active Alerts - Unified list, sent-alert browser, WFO LOT button,
  Restore UI

## CAVE-LOT D2D

The AWIPS client draws a simplified north Illinois / northwest Indiana map with
radar reflectivity, storm-relative velocity, watch and warning overlays, alert
polygons, animation controls and WarnGen tools. AWIPS II Text 1-5 windows show
the latest routed products. `Restore D2D` rebuilds the main perspective.

## BMH network and WXJ75 controller

The BMH window provides global network controls, broadcast hazard choice, ticker
text, TRANSMIT, the active transmitter tree and dispatch dialogs. Double-click a
transmitter (for example `WXJ75`) to open its controller.

The controller has eight tabs:

1. **Weather Message** - hazard category, Wednesday RMT/RWT, Add Hazard,
   Warning Message / Call to Action, periodic scroll update, SAME/EAS builder
2. **Transmitter Control** - START TX, STOP TX, NEXT PRODUCT, RESTART SERVICE,
   operational modes, Quick Read IDs (`STATION_ID`, `CURRENT_TIME`,
   `SVR_STATION_ID`, `SEVERE_MESSAGE`, `NWSLOT`, `SUMMARY`, `EMR_STATION_ID`,
   `PREPAREDNESS_ACTIONS`) and Manual Product Control (READ NOW, LOOP, STOP LOOP)
3. **Listening Area** - UGC filter, allow uncoded routine products, IL/IN text
4. **Broadcast Cycles** - mode list, NEW/DELETE/RESET MODE, special entries,
   cycle order 1-8
5. **Static Messages** - edit and preview static message overrides
6. **Live Queue** - queue status, voice, REFRESH NOW, READ SELECTED NOW,
   LOOP/STOP
7. **Active Alerts** - alert IDs, NEW/CON/CAN actions, expiry, SAME retone,
   1050 Hz tone, silent interrupt, `@Products`
8. **Products** - generated product browser

## LOTIEM

LOTIEM accepts newline-delimited JSON and fans each message out to the enabled
routes: BMH, WWA, LOCAL_OFFICIALS, PUBLIC, IEMBOT, EMAIL and WEBSITES. It writes a
per-route copy under `var/lotiem/routes/<ROUTE>/` and appends a replayable record
to `var/lotiem/messages.jsonl`.

Two transports are available:

* **File bus** (default) - atomic JSON files in `var/bus`, shared by every app on
  the machine
* **TCP** - set `lotiem.transport` to `"tcp"` and run `python run_lotwps.py
  lotiem` (or `python -m lotiem.server`) to accept remote clients

Run the daemon from the launcher's **START LOTIEM DAEMON** button. The launcher
status bar reports whether the daemon is running.

## Configuration

`config/settings.json` is created from `lotwps/config.py` defaults and is safe to
edit by hand. Useful keys:

| Key | Meaning |
| --- | --- |
| `text_workstation.host` / `.port` | `192.168.10.144` / `6000` |
| `lotiem.transport` | `file` or `tcp` |
| `lotiem.routes.*` | enable or disable each distribution route |
| `broadcast.modes` | cycle token lists by mode |
| `broadcast.listening_area.ugc` | UGC filter set |
| `broadcast.static_overrides` | per-key static message text overrides |
| `voices.paul.exe` / `.assets_dir` | VoiceText editor and WAV asset folders |
| `stations` | transmitter metadata, frequencies, SAME codes, voice |

The interface is currently English-only; the five-language requirement is not
implemented in this build.

## Project layout

```
run_lotwps.py          launcher and CLI
apps/                  Tk applications and shared dialogs
lotwps/                engine: weather, SAME, alerts, broadcast, bus, UI kit
lotiem/                hub routing and TCP daemon
data/                  generated climate normals
config/settings.json   user configuration
var/                   runtime audio, products, bus, logs and state
tests/test_core.py     headless unit tests
```

## Tests

```bat
py -3.12 -m unittest discover -s tests -v
py -3.12 -m compileall -q lotwps apps lotiem run_lotwps.py
```

The unit tests cover time zone/DST handling, UGC and SAME geography, SAME header
and AFSK framing, AWIPS headers and polygons, alert priority/persistence,
script normalisation, weather determinism and product shape, the file bus, and
LOTIEM route fan-out. GUI smoke tests are intentionally separate because they
need a desktop session.

## Troubleshooting

* **No audio** - confirm the default playback device and that `winsound` works;
  the engine deliberately keeps one audio stream per process.
* **No Paul voice** - check `voices.paul.exe` and `assets_dir`; `auto` mode falls
  back to David for live text.
* **SAPI errors** - install `pywin32` for the same Python interpreter that runs
  the apps. Run `python run_lotwps.py` and use **VOICE REPORT**.
* **LOTIEM port busy** - port 6000 may already be in use; change
  `lotiem.port` or keep the default file transport.
* **Stale alerts** - remove `var/state/alerts.json` or cancel alerts from the
  controller.
