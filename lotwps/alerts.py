"""Active alert store with the NWR priority model.

Priority ladder:  Tornado Emergency > Warning > Watch > Advisory > Statement.
Alerts are persisted to ``var/state/alerts.json`` so every window (text
workstation, BMH, station controller, radio receiver) shares one truth.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import awips, paths, same, tz, zones

PRIORITY_TIERS = {
    "Emergency": 100,
    "Warning": 70,
    "Watch": 50,
    "Advisory": 30,
    "Statement": 20,
    "Routine": 10,
}

STATUS_NEW = "NEW"
STATUS_CON = "CON"
STATUS_CAN = "CAN"
STATUS_EXP = "EXP"


def tier_for_event(event: str) -> str:
    text = event.lower()
    if "emergency" in text and "tornado" in text:
        return "Emergency"
    if "warning" in text:
        return "Warning"
    if "watch" in text:
        return "Watch"
    if "advisory" in text:
        return "Advisory"
    return "Statement"


def status_code_for(event: str, cancelled: bool, issued: datetime | None = None) -> str:
    if cancelled:
        return STATUS_CAN
    text = event.lower()
    if any(w in text for w in ("warning", "emergency", "statement", "watch")):
        return STATUS_NEW
    return STATUS_NEW


@dataclass
class Alert:
    alert_id: str
    event: str
    prod_id: str
    ugc: list[str]
    headline: str
    description: str = ""
    instruction: str = ""
    issued: datetime = field(default_factory=tz.utc_now)
    expires: datetime = field(default_factory=lambda: tz.utc_now() + timedelta(minutes=45))
    purge_minutes: int = 30
    status: str = STATUS_NEW
    callsign: str = "WXJ75/NWS"
    source: str = "LOTWPS"
    polygon: list[tuple[float, float]] = field(default_factory=list)
    same_header: str = ""

    # -- derived ---------------------------------------------------------
    @property
    def tier(self) -> str:
        return tier_for_event(self.event)

    @property
    def priority(self) -> int:
        if self.tier == "Emergency":
            return PRIORITY_TIERS["Emergency"]
        return PRIORITY_TIERS.get(self.tier, 20)

    @property
    def eas_code(self) -> str:
        try:
            return same.event_code(self.event)
        except same.SameHeaderError:
            return "SPS"

    @property
    def active(self) -> bool:
        return self.status != STATUS_CAN and self.expires > tz.utc_now()

    @property
    def minutes_left(self) -> int:
        return max(0, int((self.expires - tz.utc_now()).total_seconds() // 60))

    @property
    def area(self) -> str:
        return zones.describe_area(self.ugc) if self.ugc else "the listening area"

    def ensure_header(self) -> str:
        if not self.same_header:
            codes = zones.same_list(self.ugc)
            if codes:
                self.same_header = same.same_header(
                    self.event, codes, self.issued, self.purge_minutes, self.callsign
                )
        return self.same_header

    # -- serialisation ---------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "event": self.event,
            "prod_id": self.prod_id,
            "ugc": self.ugc,
            "headline": self.headline,
            "description": self.description,
            "instruction": self.instruction,
            "issued": self.issued.isoformat(),
            "expires": self.expires.isoformat(),
            "purge_minutes": self.purge_minutes,
            "status": self.status,
            "callsign": self.callsign,
            "source": self.source,
            "polygon": self.polygon,
            "same_header": self.same_header,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Alert":
        return cls(
            alert_id=data["alert_id"],
            event=data["event"],
            prod_id=data.get("prod_id", "SPS"),
            ugc=list(data.get("ugc", [])),
            headline=data.get("headline", ""),
            description=data.get("description", ""),
            instruction=data.get("instruction", ""),
            issued=datetime.fromisoformat(data["issued"]),
            expires=datetime.fromisoformat(data["expires"]),
            purge_minutes=int(data.get("purge_minutes", 30)),
            status=data.get("status", STATUS_NEW),
            callsign=data.get("callsign", "WXJ75/NWS"),
            source=data.get("source", "LOTWPS"),
            polygon=[tuple(p) for p in data.get("polygon", [])],
            same_header=data.get("same_header", ""),
        )


class AlertStore:
    def __init__(self, path=None):
        self.path = path or (paths.STATE / "alerts.json")
        self._lock = threading.RLock()
        self._alerts: list[Alert] = []
        self._sequence = 0
        self.load()

    # -- persistence -----------------------------------------------------
    def load(self) -> None:
        with self._lock:
            self._alerts = []
            self._sequence = 0
            if not self.path.exists():
                return
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return
            for item in data.get("alerts", []):
                try:
                    self._alerts.append(Alert.from_dict(item))
                except (KeyError, ValueError):
                    continue
            self._sequence = int(data.get("sequence", len(self._alerts)))

    def save(self) -> None:
        with self._lock:
            payload = {
                "sequence": self._sequence,
                "updated": tz.iso(tz.utc_now()),
                "alerts": [a.to_dict() for a in self._alerts],
            }
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def next_id(self, event: str) -> str:
        with self._lock:
            self._sequence += 1
            code = same.EVENT_CODES.get(event, "SPS")
            return f"LOT-{code}-{tz.utc_now():%Y}-{self._sequence:04d}"

    # -- mutation --------------------------------------------------------
    def add(self, alert: Alert) -> Alert:
        with self._lock:
            if not alert.alert_id:
                alert.alert_id = self.next_id(alert.event)
            alert.ensure_header()
            self._alerts = [a for a in self._alerts if a.alert_id != alert.alert_id]
            self._alerts.append(alert)
            self.save()
            return alert

    def issue(
        self,
        event: str,
        ugc: list[str],
        headline: str = "",
        description: str = "",
        instruction: str = "",
        duration_min: int = 45,
        purge_min: int | None = None,
        callsign: str = "WXJ75/NWS",
        polygon: list[tuple[float, float]] | None = None,
        prod_id: str | None = None,
    ) -> Alert:
        purge_min = duration_min if purge_min is None else purge_min
        prod_id = prod_id or next(
            (k for k, v in awips.EAS_EVENTS.items() if v == event), "SPS"
        )
        alert = Alert(
            alert_id="",
            event=event,
            prod_id=prod_id,
            ugc=list(ugc),
            headline=headline or f"{event} for {zones.describe_area(ugc)}",
            description=description,
            instruction=instruction,
            issued=tz.utc_now(),
            expires=tz.utc_now() + timedelta(minutes=duration_min),
            purge_minutes=purge_min,
            status=STATUS_NEW,
            callsign=callsign,
            polygon=polygon or [],
        )
        alert.alert_id = self.next_id(event)
        alert.ensure_header()
        with self._lock:
            self._alerts.append(alert)
            self.save()
        return alert

    def cancel(self, alert_id: str) -> Alert | None:
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.status = STATUS_CAN
                    alert.expires = min(alert.expires, tz.utc_now() + timedelta(minutes=15))
                    self.save()
                    return alert
        return None

    def retone(self, alert_id: str) -> Alert | None:
        """Re-issue the SAME header time for an existing alert."""
        with self._lock:
            for alert in self._alerts:
                if alert.alert_id == alert_id:
                    alert.issued = tz.utc_now()
                    alert.same_header = ""
                    alert.ensure_header()
                    self.save()
                    return alert
        return None

    def update(self, alert: Alert) -> Alert:
        return self.add(alert)

    def purge_expired(self) -> int:
        with self._lock:
            before = len(self._alerts)
            self._alerts = [
                a for a in self._alerts
                if a.status == STATUS_CAN or a.expires > tz.utc_now() - timedelta(hours=6)
            ]
            removed = before - len(self._alerts)
            if removed:
                self.save()
            return removed

    def clear(self) -> None:
        with self._lock:
            self._alerts.clear()
            self.save()

    # -- queries ---------------------------------------------------------
    def all(self) -> list[Alert]:
        with self._lock:
            return sorted(
                self._alerts,
                key=lambda a: (-a.priority, a.issued),
            )

    def active(self) -> list[Alert]:
        return [a for a in self.all() if a.active]

    def cancelled(self) -> list[Alert]:
        return [a for a in self.all() if a.status == STATUS_CAN]

    def expiring(self, within_min: int = 20) -> list[Alert]:
        now = tz.utc_now()
        return [
            a for a in self.active()
            if a.expires - now <= timedelta(minutes=within_min)
        ]

    def by_id(self, alert_id: str) -> Alert | None:
        return next((a for a in self.all() if a.alert_id == alert_id), None)

    def filtered(
        self,
        listing_ugc: list[str] | None = None,
        enable_filter: bool = False,
        allow_uncoded: bool = True,
    ) -> list[Alert]:
        alerts = self.active()
        if not enable_filter or not listing_ugc:
            return alerts
        listing = {u.upper() for u in listing_ugc}
        out = []
        for a in alerts:
            if not a.ugc:
                if allow_uncoded:
                    out.append(a)
                continue
            if listing & {u.upper() for u in a.ugc}:
                out.append(a)
        return out

    def newest(self, count: int = 5) -> list[Alert]:
        return sorted(self._alerts, key=lambda a: a.issued, reverse=True)[:count]

    def summary(self) -> str:
        active = self.active()
        if not active:
            return "No active alerts."
        return "; ".join(f"{a.event} ({a.minutes_left} min)" for a in active)

    def to_rows(self) -> list[dict]:
        rows = []
        for a in self.all():
            rows.append(
                {
                    "id": a.alert_id,
                    "event": a.event,
                    "tier": a.tier,
                    "area": a.area,
                    "status": a.status,
                    "issued": f"{a.issued:%m/%d %H:%M}Z",
                    "expires": f"{a.expires:%m/%d %H:%M}Z",
                    "minutes": a.minutes_left,
                }
            )
        return rows


_store: AlertStore | None = None
_store_lock = threading.Lock()


def store() -> AlertStore:
    global _store
    with _store_lock:
        if _store is None:
            _store = AlertStore()
        return _store


def new_alert_from_event(
    event: str,
    ugc: list[str] | None = None,
    headline: str = "",
    callsign: str = "WXJ75/NWS",
    duration_min: int | None = None,
) -> Alert:
    prod = next((p for p in awips.CATALOG.values() if awips.EAS_EVENTS.get(p.pil) == event), None)
    duration = duration_min or (prod.duration if prod else 45)
    alert = Alert(
        alert_id="",
        event=event,
        prod_id=prod.pil if prod else "SPS",
        ugc=ugc or (list(prod.ugc) if prod else ["INZ001", "INZ002"]),
        headline=headline or f"{event} for northeast Illinois and northwest Indiana",
        issued=tz.utc_now(),
        expires=tz.utc_now() + timedelta(minutes=duration),
        purge_minutes=min(60, duration),
        callsign=callsign,
    )
    alert.alert_id = uuid.uuid4().hex[:8].upper()
    alert.ensure_header()
    return alert
