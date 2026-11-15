from lotwps.models import AlertPriority, Station, alert_priority


def test_priority_order():
    assert alert_priority("Tornado Emergency") == AlertPriority.EMERGENCY
    assert alert_priority("Tornado Warning") == AlertPriority.WARNING
    assert alert_priority("Severe Thunderstorm Watch") == AlertPriority.WATCH
    assert alert_priority("Wind Advisory") == AlertPriority.ADVISORY
    assert alert_priority("Special Weather Statement") == AlertPriority.STATEMENT


def test_tornado_emergency_in_headline_overrides_warning_event():
    assert alert_priority("Tornado Warning", "Tornado Emergency declared") == AlertPriority.EMERGENCY


def test_station_uses_configured_local_timezone():
    station = Station(
        station_id="WXJ75",
        location="Valparaiso, Indiana",
        latitude=41.47,
        longitude=-87.06,
        timezone="America/Chicago",
    )
    assert station.local_time().tzinfo is not None
    assert station.local_time().tzname() in ("CST", "CDT")
