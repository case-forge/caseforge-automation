from __future__ import annotations

import sys
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import email_pdf_label as lab


def _msg(subject="Re: question", body="Could you explain the next step?", sender="client@example.test"):
    return {"subject": subject, "body": {"contentType": "text", "content": body}, "from": {"emailAddress": {"address": sender}}}


def _no_model(prompt):
    raise AssertionError("a routed email must not reach the model")


def test_four_words_is_the_hard_cap():
    assert lab.MAX_WORDS == 4
    out = lab.describe_email(_msg(), runner=lambda p: "client-asks-to-amend-paras-and-the-hearing-date")
    assert out == "client-asked-to-amend" and len(out.split("-")) <= 4


def test_new_text_drops_the_quoted_thread_and_the_signature():
    body = "Please change paragraph 3. Kind regards, Amy  From: Solicitor Sent: Monday Subject: Statement the long quoted thread"
    assert lab.new_text(_msg(body=body)) == "Please change paragraph 3."


def test_new_text_strips_html_and_trims_to_the_limit():
    html = "<html><body><p>" + "word " * 400 + "</p></body></html>"
    out = lab.new_text(_msg(body=html))
    assert "<" not in out and len(out) <= lab.BODY_CHARS


def test_slug_is_lowercase_hyphenated_with_digit_tokens_and_names_dropped():
    assert lab.slug("Client WANTS changes to FL401 statement paragraphs 3 and 18 today") == "client-wants-changes-to"
    assert lab.slug("Amy Hawthorntest approves", drop=["amy", "hawthorntest"]) == "approves"



ROUTED = [
    ("Re: Statement", "I approve it, thank you.", "Client", "in", {}, "approved-statement"),
    ("Re: Statement", "Please change paragraph 3, it is wrong.", "Client", "in", {}, "statement-amendments"),
    ("Re: Statement", "I approve it but please change paragraph 3.", "Client", "in", {}, "statement-amendments"),
    ("anything", "ok", "Client", "in", {"statement_reply": "approved"}, "approved-statement"),
    ("anything", "ok", "Client", "in", {"statement_reply": "amend"}, "statement-amendments"),
    ("Letter of Authority and Statement for Signature & Approval", "Please sign: https://sign.example.test/d/abc", "Client", "out", {}, "sent-loa-and-statement"),
    ("Your Letter of Authority", "Sign here: https://sign.example.test/d/abc", "Client", "out", {}, "sent-loa-link"),
    ("Your Witness Statement for Signature", "Sign here: https://sign.example.test/d/abc", "Client", "out", {}, "sent-statement-to-sign"),
    ("Your Client Care Letter", "Your letter is here: https://sign.example.test/d/abc", "Client", "out", {}, "sent-ccl"),
    ("ZW26F00000 || Request for Counsel || Hearing", "Please act.", "Counsel", "out", {}, "requested-counsel"),
    ("Signing Complete!", "Your document was signed.", "Client", "in", {}, "signing-complete"),
    ("Wolverhampton Court Automatic Response", "Received by the court.", "Court", "in", {}, "court-acknowledged-email"),
    ("Notice of Hearing - ZW26F11111", "Listed.", "Court", "in", {}, "hearing-notice"),
    ("Order made", "A sealed order is attached.", "Court", "in", {}, "sealed-order"),
    ("Re: Request for Counsel", "We have booked an advocate to attend.", "Counsel", "in", {}, "counsel-booked"),
    ("Re: Request for Counsel", "Sorry, we are unable to help on this occasion.", "Counsel", "in", {}, "counsel-declined"),
    ("Re: Request for Counsel", "I am afraid we are fully booked on that date.", "Counsel", "in", {}, "counsel-declined"),
    ("Re: Request for Counsel", "Sorry, chambers is fully-booked that week.", "Counsel", "in", {}, "counsel-declined"),
    ("Re: Request for Counsel", "All of our counsel are booked up on that day.", "Counsel", "in", {}, "counsel-declined"),
    ("Re: Request for Counsel", "Unfortunately we have no availability on that date.", "Counsel", "in", {}, "counsel-declined"),
    ("Re: Request for Counsel", "Unfortunately counsel is not available on that date.", "Counsel", "in", {}, "counsel-declined"),
    ("Re: Request for Counsel", "We are unable to assist on this occasion.", "Counsel", "in", {}, "counsel-declined"),
    ("Re: Request for Counsel", "We are unable to accept the brief, sorry.", "Counsel", "in", {}, "counsel-declined"),
    ("Re: Request for Counsel", "We are fully booked and have no availability; counsel cannot be booked for that date.", "Counsel", "in", {}, "counsel-declined"),
    ("Re: Request for Counsel", "Counsel is booked for the hearing and will attend.", "Counsel", "in", {}, "counsel-booked"),
    ("Re: Request for Counsel", "We accept the brief; counsel is available to attend.", "Counsel", "in", {}, "counsel-booked"),
    ("Re: Request for Counsel", "Our first choice is not available, so we have booked another member of chambers.", "Counsel", "in", {}, "counsel-booked"),
    ("Re: Request for Counsel", "We were nearly fully booked but have booked counsel for you.", "Counsel", "in", {}, "counsel-booked"),
]


@pytest.mark.parametrize(("subject", "body", "category", "direction", "signals", "expected"), ROUTED)
def test_a_common_email_gets_its_fixed_label_without_asking_the_model(subject, body, category, direction, signals, expected):
    out = lab.describe_email(_msg(subject=subject, body=body), category=category, direction=direction, signals=signals, runner=_no_model)
    assert out == expected
    assert len(expected.split("-")) <= lab.MAX_WORDS


def test_every_route_label_fits_the_cap_and_has_a_unique_name():
    names = [name for name, _t, _l in lab.ROUTES]
    assert len(names) == len(set(names))
    assert all(len(label.split("-")) <= lab.MAX_WORDS and label == label.lower() for _n, _t, label in lab.ROUTES)


def test_an_approval_word_on_a_non_statement_thread_is_not_a_route():
    out = lab.describe_email(_msg(subject="Re: Hearing date", body="I approve of that date."), category="Client", runner=lambda p: "confirms-hearing-date")
    assert out == "confirmed-hearing-date"




@pytest.mark.parametrize(
    ("given", "wanted"),
    [
        ("sends-application-for-order", "sent-application-for-order"),
        ("court-refers-case-judge", "court-referred-case-judge"),
        ("requests-counsel", "requested-counsel"),
        ("counsel-declines-brief", "counsel-declined-brief"),
        ("court-lists-hearing", "court-listed-hearing"),
        ("court-issues-order", "court-issued-order"),
        ("opponent-seeks-adjournment", "opponent-sought-adjournment"),
        ("asks-client-to-approve", "asked-client-to-approve"),
        ("sent-draft-order", "sent-draft-order"),
        ("court-referred-case", "court-referred-case"),
        ("hearing-notice", "hearing-notice"),
        ("sealed-order", "sealed-order"),
        ("court-orders-enclosed", "court-orders-enclosed"),
        ("issues-with-statement", "issues-with-statement"),
        ("request-for-counsel", "request-for-counsel"),
        ("statement-sends-wrongly", "statement-sends-wrongly"),
        ("", ""),
    ],
)
def test_a_description_is_put_in_the_past_tense(given, wanted):
    assert lab.past_tense(given) == wanted


@pytest.mark.parametrize("direction", ["in", "out"])
def test_the_past_tense_holds_when_the_model_ignores_the_instruction(direction):
    out = lab.describe_email(_msg(subject="Application for order"), category="Court", direction=direction, runner=lambda p: "sends-application-for-order")
    assert out == "sent-application-for-order"


def test_the_model_is_asked_for_the_past_tense_in_both_directions():
    for direction in ("in", "out"):
        prompt = lab._prompt("Subject", "Text", "Court", direction)
        assert "Always use the past tense" in prompt and "sent-email" in prompt
        assert not any(word in prompt.split("for example", 1)[1].split(".")[0] for word in ("sends-", "asks-", "lists-", "approves-"))


def test_no_fixed_label_is_in_the_present_tense():
    for _name, _test, label in lab.ROUTES:
        assert lab.past_tense(label) == label, label
        assert not label.split("-")[-1].endswith(("declines", "acknowledges"))


def test_a_broken_route_never_stops_filing(monkeypatch):
    def broken(ctx):
        raise RuntimeError("bad pattern")

    monkeypatch.setattr(lab, "ROUTES", [("broken", broken, "x-y")])
    out = lab.describe_email(_msg(), runner=lambda p: "asks-about-next-steps")
    assert out == "asked-about-next-steps"



def test_the_models_description_is_used_when_no_route_matches():
    out = lab.describe_email(_msg(), category="Client", client_name="Amy Hawthorntest", runner=lambda prompt: "asks-about-next-steps\n")
    assert out == "asked-about-next-steps"


def test_a_repeated_in_or_out_is_trimmed():
    assert lab.describe_email(_msg(), runner=lambda p: "in-asks-about-steps") == "asked-about-steps"


def test_the_clients_name_never_appears():
    out = lab.describe_email(_msg(), client_name="Amy Hawthorntest", runner=lambda p: "amy-hawthorntest-asks-about-steps")
    assert "amy" not in out and "hawthorntest" not in out


@pytest.mark.parametrize("answer", ["", "sorry", "I cannot help with that", "oops", "As an AI model I will not"])
def test_an_unusable_answer_falls_back_to_the_subject(answer):
    out = lab.describe_email(_msg(subject="Re: Updated information on housing"), category="Court", runner=lambda p: answer)
    assert out == "court-updated-information-on"


def test_a_failing_model_never_stops_filing():
    def boom(prompt):
        raise RuntimeError("model is down")

    out = lab.describe_email(_msg(subject="Fwd: Housing duty recommendation"), category="Client", direction="in", runner=boom)
    assert out == "housing-duty-recommendation"


def test_an_outgoing_fallback_has_no_speaker():
    out = lab.describe_email(_msg(subject="Draft bundle index"), category="Client", direction="out", runner=lambda p: "")
    assert out == "draft-bundle-index"


def test_a_subject_with_nothing_usable_still_gets_a_name():
    out = lab.describe_email(_msg(subject="12345"), category="Court", runner=lambda p: "")
    assert out == "court-sent-email"


def test_the_prompt_asks_for_two_to_four_words_and_carries_the_new_text_only():
    seen = {}

    def runner(prompt):
        seen["p"] = prompt
        return "asks-about-steps"

    lab.describe_email(_msg(body="Could you help? Kind regards, Amy From: Solicitor the old thread"), runner=runner)
    assert "two to four" in seen["p"] and "untrusted" in seen["p"]
    assert "Could you help?" in seen["p"]
    assert "the old thread" not in seen["p"]



FOOTER = (
    "Sam Example\nReferrals Co-ordinator\nExample Support Charity\n"
    "Download our new app from the app store to track your referral\n"
    "Follow us on social media\nRegistered Charity No. 0000000 | Patron: A N Other\n"
    "CONFIDENTIAL: This email and any attachments are intended for the addressee only. "
    "If you have received this email in error please delete it."
)


def _never(prompt):
    raise AssertionError("the model must not be asked: there is nothing of the sender's own to describe")


@pytest.mark.parametrize(
    "body",
    [
        f"Thanks\n\n{FOOTER}",
        f"Hi,\n\nThank you.\n\nKind regards,\n{FOOTER}",
        f"Many thanks,\n{FOOTER}",
        "Thanks, Sam Example Download our new app from the app store to track your referral Registered Charity No. 0000000",
        f"Noted, thank you.\n\nRegards\n{FOOTER}",
    ],
)
def test_an_email_that_only_says_thanks_above_a_footer_is_acknowledged(body):
    out = lab.describe_email(_msg(subject="Re: Referral", body=body), category="Client", runner=_never)
    assert out == "acknowledged"
    assert not {"app", "download", "charity", "referral", "patron", "confidential"} & set(out.split("-"))


def test_a_reply_that_is_nothing_but_a_signature_is_replied():
    assert lab.describe_email(_msg(subject="RE: Referral", body=f"Kind regards,\n{FOOTER}"), runner=_never) == "replied"
    assert lab.describe_email(_msg(subject="RE: Referral", body=FOOTER.split("\n", 3)[3]), runner=_never) == "replied"


def test_an_empty_email_that_is_not_a_reply_is_named_from_its_subject():
    out = lab.describe_email(_msg(subject="Sealed order enclosed", body=f"Regards,\n{FOOTER}"), category="Court", runner=_never)
    assert out == "sealed-order"
    assert lab.describe_email(_msg(subject="Costs schedule", body=f"Regards,\n{FOOTER}"), runner=_never) == "costs-schedule"


def test_the_model_never_sees_the_footer_and_real_content_keeps_its_summary():
    seen = []

    def runner(prompt):
        seen.append(prompt)
        return "asks-to-move-hearing"

    body = f"Dear Sirs,\n\nI cannot attend on Friday. Please can the hearing be moved to the following week?\n\nKind regards,\n{FOOTER}\n\n" + "footer padding line\n" * 60
    out = lab.describe_email(_msg(subject="Re: Hearing", body=body), category="Client", runner=runner)

    assert out == "asked-to-move-hearing"
    text = seen[0].split("Text:", 1)[1]
    assert "hearing be moved" in text
    assert not any(word in text for word in ("Download", "app store", "Charity", "Patron", "CONFIDENTIAL", "Sam Example", "Co-ordinator", "padding"))
    assert "Ignore any signature" in seen[0]


@pytest.mark.parametrize(
    ("text", "kept"),
    [
        ("Please find the order attached.\n\nKind regards\nSam Example\nClerk", "Please find the order attached."),
        ("I agree.\nThanks\nSam", "I agree."),
        ("Thanks for this. I will sign it today.\n\nSam", "Thanks for this. I will sign it today. Sam"),
        ("Please download the form and send it back, this is confidential.", "Please download the form and send it back, this is confidential."),
        ("See below.\n\nFrom: Someone Else\nSent: Monday\nSubject: Earlier\n\nDownload it", "See below."),
        ("My reply.\n> quoted line\n> another", "My reply."),
        ("Yes that is fine.\n-----Original Message-----\nold text", "Yes that is fine."),
        ("Yes that is fine. Yours sincerely, Sam Example Example Support Charity", "Yes that is fine."),
        ("The hearing is on Friday. This email and any attachments are confidential.", "The hearing is on Friday."),
        ("Kind regards,\nSam", ""),
        ("", ""),
    ],
)
def test_own_words_stops_at_the_sign_off_the_footer_or_the_quoted_thread(text, kept):
    assert lab.own_words(text) == kept


def test_html_bodies_are_cut_the_same_way():
    html = "<div>Thank you</div><div><br></div><div>Kind regards,</div><div>Sam Example</div><p>Download our app</p>"
    assert lab.describe_email({"subject": "Re: Referral", "body": {"contentType": "html", "content": html}}, runner=_never) == "acknowledged"



LIVE_REPLIES = [
    ("Re: Your Witness Statement for Signature", "We will update you by email.", "updated-by-email"),
    (
        "RE: Your Witness Statement for Signature",
        "Your application has been sent to court. We are waiting for the Court Order or Hearing Date and will be in touch.",
        "sent-application-to-court",
    ),
]


@pytest.mark.parametrize(("subject", "body", "model_says"), LIVE_REPLIES)
def test_a_reply_on_the_statement_thread_is_named_from_what_it_says(subject, body, model_says):
    seen = []

    def runner(prompt):
        seen.append(prompt)
        return model_says

    out = lab.describe_email(_msg(subject=subject, body=body, sender="solicitor@example.org"), category="Client", direction="out", runner=runner)

    assert out == model_says and out != "sent-statement-to-sign"
    assert "reply on a thread" in seen[0] and "never say it sends or encloses what the subject names" in seen[0]
    assert "Use the subject for the topic" not in seen[0]


@pytest.mark.parametrize(("subject", "body", "model_says"), LIVE_REPLIES)
def test_a_reply_is_named_from_its_own_words_when_the_model_is_down(subject, body, model_says):
    out = lab.describe_email(_msg(subject=subject, body=body), category="Client", direction="out", runner=lambda p: "")

    assert out in ("update-email", "application-sent-court-waiting")
    assert "statement" not in out and "sign" not in out


def test_a_reply_that_wrongly_gets_a_present_tense_answer_is_still_past_tense():
    out = lab.describe_email(_msg(subject="Re: Your Witness Statement for Signature", body="We will update you by email."), direction="out", runner=lambda p: "confirms-update-by-email")
    assert out == "confirmed-update-by-email"


@pytest.mark.parametrize(
    ("subject", "label"),
    [
        ("Your Witness Statement for Signature", "sent-statement-to-sign"),
        ("Your Letter of Authority", "sent-loa-link"),
        ("Letter of Authority and Statement for Signature & Approval", "sent-loa-and-statement"),
        ("Your Client Care Letter", "sent-ccl"),
    ],
)
def test_a_sent_label_needs_the_original_message_carrying_what_it_names(subject, label):
    def name(subject, **message):
        base = {"subject": subject, "from": {"emailAddress": {"address": "solicitor@example.org"}}, **message}
        return lab.describe_email(base, category="Client", direction="out", runner=lambda p: "explained-next-steps")

    link = {"body": {"contentType": "text", "content": "Please sign here: https://sign.example.test/d/abc"}}
    plain = {"body": {"contentType": "text", "content": "We have explained the next steps to you."}}
    assert name(subject, **link) == label
    assert name(subject, **plain, hasAttachments=True) == label
    assert name(subject, **plain, hasAttachments=False) == "explained-next-steps"
    for prefix in ("Re: ", "RE: ", "Fw: ", "FW: RE: "):
        assert name(prefix + subject, **link) == "explained-next-steps", prefix
    assert name(subject) == label


def test_the_other_subject_made_labels_are_not_given_to_replies_either():
    def name(subject, body, category, direction, **extra):
        return lab.describe_email({**_msg(subject=subject, body=body), **extra}, category=category, direction=direction, runner=lambda p: "explained-next-steps")

    assert name("Request for Counsel - hearing", "Please act.", "Counsel", "out") == "requested-counsel"
    assert name("Re: Request for Counsel - hearing", "We have explained the next steps.", "Counsel", "out") == "explained-next-steps"
    assert name("Notice of Hearing", "Listed.", "Court", "in") == "hearing-notice"
    assert name("RE: Notice of Hearing", "The notice is attached.", "Court", "in", hasAttachments=True) == "hearing-notice"
    assert name("RE: Notice of Hearing", "We have explained the next steps.", "Court", "out") == "explained-next-steps"
    assert name("Sealed order", "Please see the order.", "Court", "in") == "sealed-order"
    assert name("RE: Sealed order", "We have explained the next steps.", "Court", "out") == "explained-next-steps"
    assert name("RE: Application", "The sealed order is attached.", "Court", "in") == "sealed-order"
