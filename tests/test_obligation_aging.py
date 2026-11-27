
import datetime as dt

from products.ikoro import obligation_aging as oa


def test_working_days_between_skips_weekends():
    start = dt.date(2026, 6, 19)
    end = dt.date(2026, 6, 26)
    assert oa.working_days_between(start, end) == 5


def test_working_days_between_is_symmetric_and_signed():
    a = dt.date(2026, 6, 1)
    b = dt.date(2026, 6, 5)
    assert oa.working_days_between(a, b) == 4
    assert oa.working_days_between(b, a) == -4
    assert oa.working_days_between(a, a) == 0


def test_working_days_respects_bank_holidays():
    start = dt.date(2026, 8, 28)
    end = dt.date(2026, 9, 1)
    assert oa.working_days_between(start, end, holidays=set()) == 2
    assert oa.working_days_between(start, end, holidays={dt.date(2026, 8, 31)}) == 1
    assert dt.date(2026, 8, 31) in oa.BANK_HOLIDAYS
    assert oa.working_days_between(start, end) == 1


def test_modelled_bank_holidays_all_fall_on_weekdays():
    assert oa.BANK_HOLIDAYS
    assert all(d.weekday() < 5 for d in oa.BANK_HOLIDAYS)
    assert oa.is_working_day(dt.date(2026, 8, 31)) is False


def test_bank_holidays_are_refreshed_at_least_a_year_ahead():
    current_year = dt.datetime.now(dt.timezone.utc).year
    assert max(d.year for d in oa.BANK_HOLIDAYS) >= current_year + 1


def test_parse_date_formats():
    assert oa.parse_date("20.05.2026") == dt.date(2026, 5, 20)
    assert oa.parse_date("FL404B received 20/05/26") == dt.date(2026, 5, 20)
    assert oa.parse_date("2026-05-20") == dt.date(2026, 5, 20)
    assert oa.parse_date("no order yet") is None
    assert oa.parse_date("") is None


def test_parse_open_obligations_vocabulary_only():
    tokens = oa.parse_open_obligations("send_to_client, book_counsel; nonsense")
    assert tokens == ["send_to_client", "book_counsel"]
    assert oa.parse_open_obligations("") == []


def test_parse_hearing_pipe_and_freeform():
    date, court = oa.parse_hearing("2026-07-01 | Central Family Court")
    assert date == dt.date(2026, 7, 1)
    assert court == "Central Family Court"
    date2, court2 = oa.parse_hearing("listed 01/07/2026 at Central Family Court")
    assert date2 == dt.date(2026, 7, 1)
    assert "Central Family Court" in court2


def _row(**kw):
    base = {
        "matter_id": 1,
        "matter_ref": "ZW26F11111",
        "client": "Test Client",
        "order_status": "Order received 2026-06-15",
        "awaiting_next_step": "send_to_client",
        "status_changed_at": "2026-06-15",
    }
    base.update(kw)
    return base


def test_send_to_client_within_sla_is_green():
    obs = oa.compute_obligations([_row()], now=dt.date(2026, 6, 16))
    assert len(obs) == 1
    assert obs[0]["urgency"] == "green"


def test_send_to_client_just_over_sla_is_amber():
    obs = oa.compute_obligations([_row()], now=dt.date(2026, 6, 18))
    assert obs[0]["age_working_days"] == 3
    assert obs[0]["urgency"] == "amber"


def test_send_to_client_well_over_sla_is_red():
    obs = oa.compute_obligations([_row()], now=dt.date(2026, 6, 19))
    assert obs[0]["age_working_days"] == 4
    assert obs[0]["urgency"] == "red"


def test_counsel_escalates_on_hearing_proximity():
    row = _row(
        awaiting_next_step="book_counsel",
        next_hearing_text="2026-06-24 | Central Family Court",
        order_status="Order received 2026-06-22",
        status_changed_at="2026-06-22",
    )
    obs = oa.compute_obligations([row], now=dt.date(2026, 6, 22))
    assert obs[0]["obligation"] == "book_counsel"
    assert obs[0]["urgency"] == "red"
    assert obs[0]["court"] == "Central Family Court"


def test_amend_draft_order_ages_and_escalates():
    row = _row(
        awaiting_next_step="amend_draft_order",
        order_status="Draft order returned by court 2026-06-15",
        status_changed_at="2026-06-15",
    )
    amber = oa.compute_obligations([row], now=dt.date(2026, 6, 18))
    assert amber[0]["obligation"] == "amend_draft_order"
    assert amber[0]["urgency"] == "amber"
    red = oa.compute_obligations([row], now=dt.date(2026, 6, 19))
    assert red[0]["urgency"] == "red"


def test_service_returned_closes_obligation():
    row = _row(
        awaiting_next_step="arrange_service",
        service_status="SOS returned 2026-06-16",
    )
    assert oa.compute_obligations([row], now=dt.date(2026, 6, 30)) == []


def test_brooke_replay_surfaces_overdue():
    brooke = {
        "matter_id": 111,
        "matter_ref": "ZW26F11111",
        "client": "Brooke Sedgepkinstest",
        "order_status": "FL404B received 20.05.2026",
        "awaiting_next_step": "send_to_client, book_counsel",
        "status_changed_at": "2026-05-21",
        "next_hearing_text": "",
        "has_c8": False,
    }
    obs = oa.compute_obligations([brooke], now=dt.date(2026, 6, 18))
    assert {o["obligation"] for o in obs} == {"send_to_client", "book_counsel"}
    assert all(o["urgency"] == "red" for o in obs)
    assert all(o["age_working_days"] >= 18 for o in obs)

    overdue = oa.overdue_obligations(obs)
    assert len(overdue) == 2


def test_pii_safe_alert_text_excludes_client_name():
    brooke = {
        "matter_id": 111,
        "matter_ref": "ZW26F11111",
        "client": "Brooke Sedgepkinstest",
        "order_status": "FL404B received 20.05.2026",
        "awaiting_next_step": "send_to_client",
        "status_changed_at": "2026-05-21",
    }
    ob = oa.compute_obligations([brooke], now=dt.date(2026, 6, 18))[0]
    text = oa.pii_safe_alert_text(ob)
    assert "Brooke" not in text
    assert "Sedgepkinstest" not in text
    assert "ZW26F11111" in text
    assert "Send order to client" in text


def _key(ob):
    return f"{ob.get('matter_id')}|{ob.get('obligation')}|{ob.get('urgency')}"


def test_select_pushable_pushes_unacked_and_returns_current_keys():
    overdue = [
        {"matter_id": "1", "obligation": "send_to_client", "urgency": "red"},
        {"matter_id": "2", "obligation": "book_counsel", "urgency": "amber"},
    ]
    to_push, keep = oa.select_pushable(overdue, set(), _key)
    assert len(to_push) == 2
    assert keep == {"1|send_to_client|red", "2|book_counsel|amber"}


def test_select_pushable_skips_already_acked():
    overdue = [
        {"matter_id": "1", "obligation": "send_to_client", "urgency": "red"},
        {"matter_id": "2", "obligation": "book_counsel", "urgency": "amber"},
    ]
    acks = {"1|send_to_client|red"}
    to_push, keep = oa.select_pushable(overdue, acks, _key)
    assert [ob["matter_id"] for ob in to_push] == ["2"]
    assert keep == {"1|send_to_client|red", "2|book_counsel|amber"}


def test_select_pushable_escalation_amber_to_red_repushes():
    acks = {"1|book_counsel|amber"}
    overdue = [{"matter_id": "1", "obligation": "book_counsel", "urgency": "red"}]
    to_push, keep = oa.select_pushable(overdue, acks, _key)
    assert [ob["urgency"] for ob in to_push] == ["red"]
    assert keep == {"1|book_counsel|red"}


def test_select_pushable_drops_resolved_keys_from_persisted_set():
    acks = {"1|send_to_client|red", "9|arrange_service|red"}
    overdue = [{"matter_id": "1", "obligation": "send_to_client", "urgency": "red"}]
    to_push, keep = oa.select_pushable(overdue, acks, _key)
    assert to_push == []
    assert keep == {"1|send_to_client|red"}


def test_an_order_not_sent_to_the_client_is_amber_after_two_calendar_days_and_red_after_four():
    from products.ikoro import obligation_aging as oa

    def urgency(received):
        row = {"matter_id": 1, "awaiting_next_step": "send_to_client", "order_status": f"received {received}"}
        return oa.compute_obligations([row], dt.date(2026, 10, 19))[0]["urgency"]

    assert urgency("17.10.2026") == "green"
    assert urgency("16.10.2026") == "amber"
    assert urgency("15.10.2026") == "red"
