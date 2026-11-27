import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil.schemas import ClientMatch


def test_from_row_accepts_string_dates():
    match = ClientMatch.from_row({"dob_iso": "1990-01-01", "closed_at": "2026-01-15"})
    assert match.dob_iso == "1990-01-01"
    assert match.closed_at == "2026-01-15"


def test_from_row_stringifies_a_live_datetime_value_instead_of_raising():
    match = ClientMatch.from_row(
        {
            "dob_iso": dt.date(1990, 1, 1),
            "closed_at": dt.datetime(2026, 7, 19, 2, 27, 13, 669374),
        }
    )
    assert match.dob_iso == "1990-01-01"
    assert match.closed_at == "2026-07-19T02:27:13.669374"


def test_from_row_leaves_none_dates_alone():
    match = ClientMatch.from_row({"dob_iso": None, "closed_at": None})
    assert match.dob_iso is None
    assert match.closed_at is None


def test_from_row_does_not_touch_datetime_values_riding_in_extra():
    match = ClientMatch.from_row({"referral_sent_at": dt.datetime(2026, 8, 1, 9, 0)})
    assert match.extra["referral_sent_at"] == dt.datetime(2026, 8, 1, 9, 0)
