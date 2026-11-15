from datetime import datetime, timezone

from lotwps.models import Alert, AlertPriority, Station
from lotwps.priority import sort_alerts
from lotwps.regional import alert_matches_station, marine_allowed, station_local_time
from lotwps.same import build_same_header, normalize_same_area_code, write_test_alert_wav


def test_priority_order():
    alerts = [
        Alert("s", "Special Weather Statement"),
        Alert("w", "Tornado Warning"),
        Alert("e", "Tornado Emergency"),
        Alert("a", "Wind Advisory"),
        Alert("k", "Tornado Watch"),
    ]
    assert [x.identifier for x in sort_alerts(alerts)] == ["e", "w", "k", "a", "s"]
    assert alerts[2].priority == AlertPriority.EMERGENCY


def test_same_code_and_header():
    assert normalize_same_area_code("INC127") == "018127"
    header = build_same_header("Tornado Warning", ["018127"], 30,
        issued_at=datetime(2026, 11, 14, 21, 2, tzinfo=timezone.utc), station_id="WXK75")
    assert header.startswith("ZCZC-WXR-TOR-018127+0030-")
    assert "WXK75" in header


def test_station_timezone_and_dst():
    station = Station("WXK75", "Valparaiso", "Indiana", "America/Chicago")
    local = station_local_time(station, datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc))
    assert local.hour == 7
    assert local.tzname() == "CDT"


def test_listening_area_and_marine_gate():
    station = Station("WXK75", "Valparaiso", "Indiana", "America/Chicago", listening_area_ugc=["INC127"])
    assert alert_matches_station(Alert("1", "Tornado Warning", ugc_codes=["INC127"]), station)
    assert not alert_matches_station(Alert("2", "Tornado Warning", ugc_codes=["ILC031"]), station)
    assert marine_allowed(station, coastal_only=True) is False


def test_test_wav_builder(tmp_path):
    import wave
    header = build_same_header("Required Weekly Test", ["018127"], 15, station_id="WXK75")
    output = write_test_alert_wav(tmp_path / "rwt_test.wav", header, sample_rate=8000,
        header_repeats=1, eom_repeats=1, attention_tone_seconds=0.25)
    with wave.open(str(output), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 8000
        assert wav.getnframes() > 0
