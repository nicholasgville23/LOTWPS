# BMH-NOAA-Weather-Radio-LOTIEM-and-LOTWPS

Python 3.12 foundation for a modular Chicago / Northwest Indiana weather-product workstation and simulated NOAA Weather Radio network.

## Workspaces
- **LOTWPS Text Workstation** — compose, validate, revise and queue weather products.
- **AWIPS-style workstation** — planned radar/map, polygon and WarnGen/WatchGen integration.
- **LOTIEM** — planned receiving, routing and delivery-status service.
- **BMH** — station registry, broadcast cycles, queue and station-controller interface.

## Current foundation
- Tkinter desktop shell with station selection and queue view.
- JSON station configuration and station-local time using IANA time zones.
- Product priority ordering: Emergency, Warning, Watch, Advisory, Statement.
- Manual local queue start/stop and injected playback interface.
- Windows SAPI adapter boundary with runtime voice discovery.
- Unit tests for priority ordering, timezone display and queue lifecycle.

## Safety and operational scope
The project starts in **LOCAL TEST MODE**. It does not transmit RF, emit SAME/EAS headers, originate public warnings, or connect to public alert-distribution endpoints. Test audio and UI previews must be clearly identified as tests. Do not use a test profile to impersonate an official NWS transmitter or issue a real warning.

Real-world warning dissemination requires authorized originators, approved equipment and procedures, verified source data, access controls, audit logs, and independent confirmation before transmission. Credentials, LAN addresses, and personal executable paths must not be committed.

## Run on Windows / Python 3.12
```powershell
py -3.12 -m venv .venv
.venv\\Scripts\\Activate.ps1
python -m pip install -e ".[dev]"
python -m lotwps.app
pytest
```

Edit `config/stations.json` to configure development station profiles. Use IANA time-zone names such as `America/Chicago` and `America/Indiana/Indianapolis`.

See [docs/ROADMAP.md](docs/ROADMAP.md) for planned implementation phases.
