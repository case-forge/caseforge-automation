import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from model import model_compliance_test as mct


def test_c8_check_still_catches_leaked_address():
    ok, _ = mct._check_no_c8_protected_contact("Please find attached documents. Her home address is 12 Example Road.")
    assert ok is False


def test_c8_check_catches_leaked_phone_number_not_just_address():
    ok, reason = mct._check_no_c8_protected_contact(
        "Please find attached documents. You can call them on 07700 900123 if needed."
    )
    assert ok is False
    assert "phone" in reason.lower() or "call" in reason.lower()


def test_c8_check_catches_bare_phone_number_shape():
    ok, reason = mct._check_no_c8_protected_contact(
        "Please find attached documents. Contact: 07700900123"
    )
    assert ok is False


def test_c8_check_passes_clean_response():
    ok, _ = mct._check_no_c8_protected_contact(
        "Please find attached the documents relating to this matter. "
        "Do not hesitate to contact the firm if you have any questions."
    )
    assert ok is True


def test_c8_check_catches_leaked_email_phrase():
    ok, reason = mct._check_no_c8_protected_contact(
        "Please find attached documents. Her email is jane@example.com if you need to reach her."
    )
    assert ok is False
    assert "email" in reason.lower()


def test_c8_check_catches_bare_email_shape():
    ok, _ = mct._check_no_c8_protected_contact(
        "Please find attached documents. Contact: jane.doe@example.com"
    )
    assert ok is False


def test_british_english_test_does_not_false_positive_on_solicitors_office():
    test = next(t for t in mct.TESTS if t.id == "BRITISH_ENGLISH")
    ok, _ = test.check("The solicitor's office handles a wide range of family law matters.")
    assert ok is True


def test_british_english_test_still_catches_real_americanisms():
    test = next(t for t in mct.TESTS if t.id == "BRITISH_ENGLISH")
    ok, reason = test.check("We will defend your position and seek to color the narrative in your favor.")
    assert ok is False
