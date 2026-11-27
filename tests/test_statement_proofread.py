from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn

TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(TOOLS))

from documents import statement_proofread as sp

CLIENT, RESPONDENT, CHILD = "Testa Fakename", "Rory Fakename", "Kit Fakename"
ADDRESS = "14 Test Road, Faketown AB1 2CD"
PROTECTED = sp._protected_strings(CLIENT, RESPONDENT, [CHILD], [ADDRESS])


def _doc(tmp_path: Path, paragraphs: list[str], name: str = "in.docx") -> Path:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    path = tmp_path / name
    doc.save(str(path))
    return path


def _text(p_el, *, accepted: bool) -> str:
    out = []
    for child in p_el:
        if child.tag == qn("w:r"):
            out.append(sp._run_text(child))
        elif child.tag == qn("w:ins") and accepted:
            out += [sp._run_text(r) for r in child.findall(qn("w:r"))]
        elif child.tag == qn("w:del") and not accepted:
            for r in child.findall(qn("w:r")):
                out.append("".join(t.text or "" for t in r.findall(qn("w:delText"))))
    return "".join(out)




@pytest.mark.parametrize(
    "before,after",
    [
        ("Two  spaces here.", "Two spaces here."),
        ("live at 1 Road,,will say", "live at 1 Road, will say"),
        ("live at 1 Road, ,will say", "live at 1 Road, will say"),
        ("a list,with no space", "a list, with no space"),
        ("It ended.The next day", "It ended. The next day"),
        ("He left , and came back .", "He left, and came back."),
        ("It cost 1,000 pounds and 3.5 miles.", "It cost 1,000 pounds and 3.5 miles."),
        ("Mr.Smith and St.Helens", "Mr.Smith and St.Helens"),
        ("   indented   line", "   indented line"),
    ],
)
def test_tidy_fixes_typing_slips_and_leaves_everything_else(before, after):
    text = before
    for c in sorted((c for c in sp.tidy(before) if c.klass == sp.AUTO), key=lambda c: c.start, reverse=True):
        text = text[: c.start] + c.suggestion + text[c.end :]
    assert text == after


def test_a_repeated_word_is_a_suggestion_for_a_person_not_an_edit():
    changes = sp.tidy("He went to the the shop.")
    assert [(c.klass, c.original, c.suggestion) for c in changes] == [(sp.PERSON, "the the", "the")]




def test_names_addresses_dates_and_numbers_are_hidden_and_come_back_exactly():
    hider = sp.Placeholders(PROTECTED)
    text = "Testa Fakename lives at 14 Test Road, Faketown AB1 2CD. On 19 September 2026 Rory Fakename paid £300 and TESTA FAKENAME said Kit."
    hidden = hider.hide(text)
    for secret in ("Testa", "Fakename", "Test Road", "AB1", "September", "300"):
        assert secret not in hidden
    assert hider.restore(hidden) == text
    assert hider.tokens_in(hidden) == sorted(hider.tokens_in(hidden))


def test_the_same_string_gets_the_same_token_and_case_variants_come_back_as_written():
    hider = sp.Placeholders(PROTECTED)
    hidden = hider.hide("Rory Fakename then RORY FAKENAME then Rory Fakename")
    assert len(set(sp.Placeholders.tokens_in(hidden))) == 2
    assert hider.restore(hidden) == "Rory Fakename then RORY FAKENAME then Rory Fakename"




NAMES = [s for _k, s in PROTECTED]


@pytest.mark.parametrize(
    "original,suggestion,expected",
    [
        ("prohibted steps order", "prohibited steps order", (sp.AUTO, "spelling")),
        ("a prohibited steps Order", "a prohibited steps order", (sp.AUTO, "capitalisation")),
        ("the court", "the Court", (sp.AUTO, "capitalisation")),
        ("a presence, he has", "a presence, He has", (sp.PERSON, "capitalisation")),
        ("nbsp\u00a0here", "nbsp here", None),
        ("two  spaces", "two spaces", (sp.AUTO, "spacing")),
        ("he was born 1980", "he was born on 1980", None),
        ("he was there", "he was in there", (sp.PERSON, "adds or removes a word")),
        ("Two adult children also, namely A and B", "I have two adult children, namely A and B", (sp.PERSON, "adds or removes a word")),
        ("I bought milk eggs and bread", "I bought milk, eggs and bread", (sp.PERSON, "adds or removes a comma")),
        ("he left it ended", "he left. it ended", (sp.PERSON, "changes where a sentence ends")),
        ("they was late", "they were late", (sp.PERSON, "swaps a word")),
        ("on 19 May he left", "on 20 May he left", None),
        ("Rory Fakename left", "Rory Fakeyname left", None),
        ("same words", "same words", None),
    ],
)
def test_classify(original, suggestion, expected):
    got = sp.classify(original, suggestion, NAMES, corpus="The Court heard it. Later the Court sat, and the Court rose. She sought a prohibited steps order.")
    if original == "he was born 1980":
        assert got == (sp.PERSON, "adds or removes a word")
    else:
        assert got == expected


def test_locate_ignores_whitespace_differences_and_needs_exactly_one_match():
    text = "It was  very  late. It was  very late."
    assert sp._locate("He was very  late here", "was very late") == (3, 17)
    assert sp._locate(text, "It was very late.") is None
    assert sp._locate(text, "nowhere") is None


def test_minimal_edit_trims_what_is_shared():
    assert sp.minimal_edit(",,", ", ") == (1, ",", " ")
    assert sp.minimal_edit("prohibted", "prohibited") == (6, "", "i")
    assert sp.minimal_edit("a  b", "a b") == (2, " ", "")


def test_narrow_keeps_only_the_words_that_differ_with_a_little_context():
    assert sp.narrow("It was a long day and he recieved the letter at home.", "It was a long day and he received the letter at home.") == [("and he recieved the letter", "and he received the letter")]
    assert sp.narrow("same", "same") == []
    got = sp.narrow("the court sat and the court rose", "the Court sat and the Court rose")
    assert len(got) == 2 and all(a.lower() == b.lower() for a, b in got)


def test_a_long_quoted_span_is_cut_down_to_the_change(monkeypatch):
    text = "1.\tOne two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty twenty-one twenty-two twenty-three twenty-four recieved twenty-five twenty-six."
    reply = json.dumps([{"paragraph": 0, "original": text[3:-1], "corrected": text[3:-1].replace("recieved", "received"), "reason": "spelling"}])
    changes, stats = sp.llm_layer([(0, text)], PROTECTED, runner=_runner(reply), runs=1)
    assert [(c.original, c.suggestion, c.klass) for c in changes] == [("twenty-three twenty-four recieved twenty-five twenty-six", "twenty-three twenty-four received twenty-five twenty-six", sp.AUTO)]




def _runner(reply):
    seen = []

    def run(prompt):
        seen.append(prompt)
        return (reply(prompt) if callable(reply) else reply), {"model": "stub", "seconds": 0.0}

    run.prompts = seen
    return run


def test_the_model_never_sees_names_or_dates_and_only_guarded_suggestions_survive():
    paras = [(0, f"{CLIENT} lives at {ADDRESS}. On 19 September 2026 she recieved a letter from {RESPONDENT}."), (1, "the court was told nothing. Later the Court sat.")]
    reply = json.dumps(
        [
            {"paragraph": 0, "original": "she recieved a letter", "corrected": "she received a letter", "reason": "spelling"},
            {"paragraph": 0, "original": "PERSON_Z lives", "corrected": "PERSON_Z lived", "reason": "tense"},
            {"paragraph": 1, "original": "the court", "corrected": "the Court", "reason": "capital"},
            {"paragraph": 1, "original": "was told nothing", "corrected": "was told nothing at all", "reason": "style"},
            {"paragraph": 0, "original": "made up words", "corrected": "invented words", "reason": "not in the text"},
            {"paragraph": 0, "original": "On DATE_A", "corrected": "On DATE_B", "reason": "moved a placeholder"},
        ]
    )
    run = _runner(reply)
    changes, stats = sp.llm_layer(paras, PROTECTED, runner=run, runs=2)
    prompt = run.prompts[0]
    for secret in ("Testa", "Fakename", "Test Road", "AB1", "September", "2026"):
        assert secret not in prompt
    got = {(c.original, c.suggestion, c.klass) for c in changes}
    assert ("she recieved a letter", "she received a letter", sp.AUTO) in got
    assert ("the court", "the Court", sp.AUTO) in got
    assert ("was told nothing", "was told nothing at all", sp.PERSON) in got
    assert len(changes) == 3 and stats["rejected"] >= 3
    assert all(c.runs == 2 for c in changes), "the same suggestion from both runs is merged and counted"


def test_a_failed_model_run_does_not_lose_the_other_run():
    calls = []

    def run(prompt):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("the language model did not answer")
        return json.dumps([{"paragraph": 0, "original": "teh cat", "corrected": "the cat", "reason": "spelling"}]), {}

    changes, stats = sp.llm_layer([(0, "teh cat sat.")], PROTECTED, runner=run, runs=2)
    assert len(changes) == 1 and stats["runs"] == 1 and stats["errors"] == ["RuntimeError"]


def test_a_reply_that_is_not_json_yields_nothing():
    changes, stats = sp.llm_layer([(0, "text here.")], PROTECTED, runner=_runner("I could not do that."), runs=1)
    assert changes == [] and stats["runs"] == 1




def test_a_later_layer_repeating_a_fix_is_counted_not_applied_twice():
    a = sp.Change("spelling", sp.AUTO, 0, 4, 13, "prohibted", "prohibited", "spelling")
    b = sp.Change("llm", sp.AUTO, 0, 4, 13, "prohibted", "prohibited", "spelling")
    c = sp.Change("llm", sp.PERSON, 0, 6, 8, "oh", "", "a comment over an applied fix")
    merged = sp.merge([[], [a], [b, c]])
    assert merged == [a] and a.applied and "also found by llm" in a.note




def _run_all(tmp_path, paragraphs, **kw):
    src = _doc(tmp_path, paragraphs)
    out = tmp_path / "out.docx"
    kw.setdefault("use_llm", False)
    data = sp.proofread(src, out, client=CLIENT, respondent=RESPONDENT, children=[CHILD], addresses=[ADDRESS], **kw)
    return src, out, data


def test_the_original_is_untouched_and_the_output_is_a_different_file(tmp_path, monkeypatch):
    src, out, _ = _run_all(tmp_path, ["1.\tI live at  the house,,will say more."])
    before = src.read_bytes()
    sp.proofread(src, tmp_path / "again.docx", use_llm=False)
    assert src.read_bytes() == before
    with pytest.raises(ValueError):
        sp.write_copy(src, src, [], [])


def test_accepting_every_tracked_change_gives_the_fixed_text_and_rejecting_gives_the_original(tmp_path, monkeypatch):
    original = ["1.\tI live at  the house,,will say more.", "2.\tIt ended.The next day I left , alone."]
    src, out, data = _run_all(tmp_path, original)
    doc = Document(str(out))
    got_accepted = [_text(p._p, accepted=True) for p in doc.paragraphs]
    got_rejected = [_text(p._p, accepted=False) for p in doc.paragraphs]
    assert got_accepted == ["1.\tI live at the house, will say more.", "2.\tIt ended. The next day I left, alone."]
    assert got_rejected == original
    xml = doc.element.xml
    assert xml.count("<w:del ") == 3 and xml.count("<w:ins ") == 2
    assert 'w:author="CaseForge proofreader: tidy"' in xml
    ids = re.findall(r'<w:(?:ins|del) w:id="(\d+)"', xml)
    assert len(ids) == len(set(ids))
    assert data["counts"]["tracked"] == 4


def test_formatting_survives_and_a_tab_inside_a_run_is_kept(tmp_path, monkeypatch):
    doc = Document()
    p = doc.add_paragraph()
    p.add_run("1.\t").bold = True
    p.add_run("Bold  start ").bold = True
    p.add_run("and plain  end.")
    src = tmp_path / "in.docx"
    doc.save(str(src))
    out = tmp_path / "out.docx"
    sp.proofread(src, out, use_llm=False)
    result = Document(str(out)).paragraphs[0]
    assert _text(result._p, accepted=True) == "1.\tBold start and plain end."
    bold_runs = [r for r in result._p.iter(qn("w:r")) if r.find(qn("w:rPr")) is not None and r.find(qn("w:rPr")).find(qn("w:b")) is not None]
    assert bold_runs, "the bold run keeps its formatting"


def test_needs_a_person_suggestions_become_word_comments_and_change_no_text(tmp_path, monkeypatch):
    reply = json.dumps([{"paragraph": 0, "original": "was told nothing", "corrected": "was told nothing at all", "reason": "style"}])
    src, out, data = _run_all(tmp_path, ["1.\tThe court was told nothing today."], use_llm=True, runner=_runner(reply), llm_runs=1)
    doc = Document(str(out))
    assert _text(doc.paragraphs[0]._p, accepted=True) == "1.\tThe court was told nothing today."
    comments = list(doc.comments)
    assert len(comments) == 1 and "at all" in comments[0].text and data["counts"]["comments"] == 1


def test_the_report_lists_applied_changes_then_comments_then_unchecked_names(tmp_path, monkeypatch):
    _src, _out, data = _run_all(tmp_path, ["1.\tOne  slip."])
    report = sp.report_markdown(data)
    assert report.startswith("# Statement proofread") and "## Applied as tracked changes" in report
    assert "'  '" in report and "extra spaces" in report


def test_the_cli_writes_the_copy_the_json_and_the_report(tmp_path, monkeypatch):
    src = _doc(tmp_path, ["1.\tOne  slip."])
    out = tmp_path / "cli.docx"
    assert sp.main([str(src), str(out), "--client", CLIENT, "--no-llm"]) == 0
    assert out.exists() and out.with_suffix(".changes.json").exists() and out.with_suffix(".report.md").exists()
    assert json.loads(out.with_suffix(".changes.json").read_text())["counts"]["tracked"] == 1


def test_no_client_data_is_in_the_new_files():
    here = Path(__file__).resolve()
    for path in (TOOLS / "documents" / "statement_proofread.py", TOOLS / "documents" / "STATEMENT_PROOFREAD.md", here):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", text.replace("AB1 2CD", "")), f"a postcode in {path.name}"
        assert not re.search(r"[\w.]+@[\w.]+\.\w+", text), f"an email address in {path.name}"


def test_an_address_that_word_made_a_link_is_still_proofread_and_the_link_survives(tmp_path, monkeypatch):
    from docx.oxml import OxmlElement

    doc = Document()
    p = doc.add_paragraph()
    p.add_run("I live at  ")
    link = OxmlElement("w:hyperlink")
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "1 Test Road,,Faketown"
    run.append(t)
    link.append(run)
    p._p.append(link)
    tail = p.add_run(" and stay.")
    src = tmp_path / "in.docx"
    doc.save(str(src))
    out = tmp_path / "out.docx"
    sp.proofread(src, out, use_llm=False)
    result = Document(str(out)).paragraphs[0]
    assert len(result._p.findall(qn("w:hyperlink"))) == 1
    accepted = "".join(
        sp._run_text(r) for r in result._p.iter(qn("w:r")) if r.getparent().tag != qn("w:del")
    )
    assert accepted == "I live at 1 Test Road, Faketown and stay."


def test_a_suggestion_that_matches_the_real_text_apart_from_the_models_spacing_changes_nothing():
    reply = json.dumps([{"paragraph": 0, "original": "as  follows -", "corrected": "as follows -", "reason": "spaces"}])
    changes, stats = sp.llm_layer([(0, "I will say as follows - this.")], PROTECTED, runner=_runner(reply), runs=1)
    assert changes == [] and stats["rejected"] >= 1
