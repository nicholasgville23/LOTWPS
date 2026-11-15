from lotwps.bmh import LocalBMHQueue


def test_local_queue_adds_and_lists_items():
    queue = LocalBMHQueue()
    item = queue.add("WXJ75", "Local information", "Test message")

    assert item.station_id == "WXJ75"
    assert item.hazard == "Local information"
    assert item.text == "Test message"
    assert queue.items() == (item,)


def test_local_queue_clear_removes_items():
    queue = LocalBMHQueue()
    queue.add("KBB58", "Test", "Local preview")
    queue.clear()

    assert queue.items() == ()
