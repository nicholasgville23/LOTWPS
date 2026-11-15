from __future__ import annotations

from .models import Alert, AlertPriority


def sort_alerts(alerts: list[Alert]) -> list[Alert]:
    return sorted(alerts, key=lambda a: (-int(a.priority), -(a.sent.timestamp() if a.sent else 0), a.event.casefold(), a.identifier))


def priority_label(priority: AlertPriority) -> str:
    return {
        AlertPriority.EMERGENCY: "EMERGENCY",
        AlertPriority.WARNING: "WARNING",
        AlertPriority.WATCH: "WATCH",
        AlertPriority.ADVISORY: "ADVISORY",
        AlertPriority.STATEMENT: "STATEMENT",
    }[priority]
