import sys
from datetime import UTC, date, datetime
from pathlib import Path

WORKER_DIR = Path(__file__).resolve().parents[1] / "cloudflare" / "worker" / "src"
sys.path.insert(0, str(WORKER_DIR))

from worker_time import localize_madrid, madrid_noon, to_madrid  # noqa: E402


def test_madrid_conversion_uses_cet_and_cest_offsets():
    assert to_madrid(datetime(2026, 1, 15, 8, tzinfo=UTC)).isoformat() == (
        "2026-01-15T09:00:00+01:00"
    )
    assert to_madrid(datetime(2026, 7, 15, 8, tzinfo=UTC)).isoformat() == (
        "2026-07-15T10:00:00+02:00"
    )


def test_madrid_conversion_switches_at_eu_transition_instants():
    assert to_madrid(datetime(2026, 3, 29, 0, 59, tzinfo=UTC)).isoformat() == (
        "2026-03-29T01:59:00+01:00"
    )
    assert to_madrid(datetime(2026, 3, 29, 1, 0, tzinfo=UTC)).isoformat() == (
        "2026-03-29T03:00:00+02:00"
    )
    assert to_madrid(datetime(2026, 10, 25, 0, 59, tzinfo=UTC)).isoformat() == (
        "2026-10-25T02:59:00+02:00"
    )
    assert to_madrid(datetime(2026, 10, 25, 1, 0, tzinfo=UTC)).isoformat() == (
        "2026-10-25T02:00:00+01:00"
    )


def test_local_values_receive_the_expected_offset():
    assert madrid_noon(date(2026, 9, 5)).isoformat().endswith("+02:00")
    assert localize_madrid(datetime(2026, 12, 5, 20)).isoformat().endswith("+01:00")
