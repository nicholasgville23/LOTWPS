from datetime import datetime, timezone
import pytest
from lotwps.engine import BroadcastQueue
from lotwps.models import AlertPriority, Station, WeatherProduct

def make_product(product_id: str, priority: AlertPriority) -> WeatherProduct:
    return WeatherProduct(product_id, product_id, f"Test message {product_id}", priority=priority)

def test_priority_order_is_emergency_first() -> None:
    queue = BroadcastQueue()
    queue.enqueue(make_product("statement", AlertPriority.STATEMENT))
    queue.enqueue(make_product("warning", AlertPriority.WARNING))
    queue.enqueue(make_product("emergency", AlertPriority.EMERGENCY))
    assert [p.product_id for p in queue.snapshot()] == ["emergency", "warning", "statement"]

def test_station_local_time_uses_iana_timezone() -> None:
    station = Station("WXK75", "Valparaiso", "America/Indiana/Indianapolis")
    utc = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert station.local_time(utc).hour == 7

def test_queue_rejects_non_test_products() -> None:
    with pytest.raises(ValueError):
        WeatherProduct("LIVE", "Live", "Not allowed", test_only=False)

def test_queue_start_stop_is_manual() -> None:
    queue = BroadcastQueue()
    assert queue.start() is True
    assert queue.start() is False
    queue.stop()
