from datetime import datetime, timezone

import pytest

from lotwps.workstation import build_product_draft, make_product_id, make_wmo_header


def test_wmo_header_contains_utc_day_hour_minute():
    stamp = datetime(2026, 11, 15, 20, 5, tzinfo=timezone.utc)
    assert make_wmo_header("TTAAii", "KLOT", "NOR", stamp) == "TTAAII KLOT 152005 NOR"


def test_product_id():
    assert make_product_id("SVR", "LOT") == "SVRLOT"


def test_bad_cccc_rejected():
    with pytest.raises(ValueError):
        make_wmo_header("TTAAii", "LOT", "NOR")


def test_draft_is_labelled_not_official():
    draft = build_product_draft("Test body", "SPS", "LOT")
    assert "DRAFT ONLY" in draft
    assert "NOT AN OFFICIAL NWS PRODUCT" in draft
    assert "SPSLOT" in draft
