# Implementation roadmap

## Phase 1 — foundation
- [x] Python 3.12 package and core data models
- [x] JSON station registry and IANA station-local clocks
- [x] Priority queue and manual start/stop
- [x] Windows SAPI adapter boundary and runtime voice discovery
- [ ] Validate on Windows 11 / Python 3.12

## Phase 2 — weather data and product authoring
- NWS API client with configured user-agent, caching, provenance and stale-data handling
- Product templates: station ID, current conditions, hourly roundup, zone forecast, climate summary and hazardous outlook
- Product editor with revision history, segment operations and WMO header helper
- Region/season-aware marine and hazardous outlook selection

## Phase 3 — BMH workstation
- Station registry, station health, heartbeat and connection status
- Broadcast cycle editor, static messages, live queue and product selection
- Station-specific timezone and coverage filtering
- Local audio preview and simulated transmitter controls

## Phase 4 — AWIPS-style tools
- Radar/map data layer and geographic overlays
- Polygon drawing and validation
- WarnGen/WatchGen product drafting with human review
- Alert lifecycle and expiration tracking

## Phase 5 — LOTIEM receiving and integrations
- Authenticated message ingestion, schema validation and idempotency
- Delivery status, retries, audit events and role-based access
- External outlet integrations only after explicit configuration and authorization

## Operational gate
Any real public alert origination or transmitter/EAS integration is a separate gated project requiring documented authority, approved interfaces, credentials outside the repository, test fixtures, two-person review, auditability and compliance validation. No public transmission path is implemented in this foundation.
