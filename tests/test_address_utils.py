import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("address_utils", ROOT / "tools" / "documents" / "address_utils.py")
address_utils = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = address_utils
SPEC.loader.exec_module(address_utils)


def test_keeps_country_when_address_fits():
    lines = address_utils.normalise_postal_address_lines(
        ["abc road", "london", "england", "AA1 1AA"],
        max_lines=4,
    )

    assert lines == ["abc road", "london", "england", "AA1 1AA"]


def test_drops_country_before_postcode_when_too_long():
    lines = address_utils.normalise_postal_address_lines(
        ["123 Road", "Greenwich", "London", "England", "ZZ99 9ZZ"],
        max_lines=4,
    )

    assert lines == ["123 Road", "Greenwich", "London", "ZZ99 9ZZ"]


def test_drops_country_after_postcode_when_too_long():
    lines = address_utils.normalise_postal_address_lines(
        ["123 Road", "Greenwich", "London", "ZZ99 9ZZ", "UK"],
        max_lines=4,
    )

    assert lines == ["123 Road", "Greenwich", "London", "ZZ99 9ZZ"]


def test_splits_comma_joined_address():
    lines = address_utils.normalise_postal_address_lines(
        ["123 Road, Greenwich, London, England, ZZ99 9ZZ"],
        max_lines=4,
    )

    assert lines == ["123 Road", "Greenwich", "London", "ZZ99 9ZZ"]
    assert address_utils.postcode_is_last_visible_line(lines)
