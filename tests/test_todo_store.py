from __future__ import annotations

import datetime as dt

import pytest

import clientdb_sql
from todos import todo_store as ts

NOW = dt.datetime(2026, 9, 25, 11, 0, tzinfo=dt.timezone.utc)
LATER = NOW + dt.timedelta(days=1)

ME, THIRD = "Sam", "Alex"
USER_A, USER_B = "user-a@example.test", "user-b@example.test"


def _make(title="ring court", **kw):
    return ts.create(title, created_by=kw.pop("created_by", ME), now=kw.pop("now", NOW), **kw)


def test_a_task_is_stored_with_its_fields_and_starts_open():
    todo = _make("ring the court", starred=True, matter_id=601, notes="  ask about the order ")
    assert todo["title"] == "ring the court" and todo["assignee"] == "", "a task is assigned to nobody"
    assert todo["starred"] is True and todo["matter_id"] == 601 and todo["notes"] == "ask about the order"
    assert todo["is_done"] is False and todo["is_overdue"] is False and todo["created_by"] == ME
    assert ts.get(todo["todo_id"], now=NOW)["title"] == "ring the court"


def test_a_task_needs_a_title_but_no_maker():
    with pytest.raises(ts.TodoError, match="title"):
        _make("   ")
    assert ts.create("x", created_by=" ", now=NOW)["created_by"] == "CaseForge"
    with pytest.raises(TypeError):
        _make(assignee="Sam")


def test_a_date_only_task_is_due_at_the_end_of_that_london_day_and_never_early():
    todo = _make(due="2026-09-25")
    assert todo["due_utc"] == "2026-09-25T22:59:00Z" and todo["due_has_time"] is False
    assert ts.get(todo["todo_id"], now=NOW)["is_overdue"] is False
    late = dt.datetime(2026, 9, 25, 23, 0, tzinfo=dt.timezone.utc)
    assert ts.get(todo["todo_id"], now=late)["is_overdue"] is True


def test_a_task_with_a_time_is_due_at_that_moment():
    todo = _make(due="2026-09-25T14:30:00Z", due_has_time=True)
    assert todo["due_utc"] == "2026-09-25T14:30:00Z" and todo["due_has_time"] is True
    assert ts.get(todo["todo_id"], now=dt.datetime(2026, 9, 25, 14, 31, tzinfo=dt.timezone.utc))["is_overdue"] is True


def test_a_bad_due_is_refused():
    with pytest.raises(ts.TodoError, match="due"):
        _make(due="next tuesday")


def test_a_done_task_is_never_overdue_and_can_be_reopened():
    todo = _make(due="2026-09-24")
    assert ts.get(todo["todo_id"], now=NOW)["is_overdue"] is True
    done = ts.complete(todo["todo_id"], True, by="Sam", now=NOW)
    assert done["is_done"] and done["is_overdue"] is False and done["done_by"] == "Sam"
    assert ts.complete(todo["todo_id"], False, by="Sam", now=NOW)["is_done"] is False


def test_my_day_is_a_date_that_stops_counting_tomorrow():
    todo = _make("today's job", my_day=True, owner=USER_A)
    assert [t["todo_id"] for t in ts.list_todos(view="my_day", owner=USER_A, now=NOW)] == [todo["todo_id"]]
    assert ts.list_todos(view="my_day", owner=USER_A, now=LATER) == [], "yesterday's my day does not carry over"


def test_views_important_and_planned():
    star = _make("star", starred=True)
    plan = _make("plan", due="2026-09-30")
    _make("plain")
    assert [t["todo_id"] for t in ts.list_todos(view="important", now=NOW)] == [star["todo_id"]]
    assert [t["todo_id"] for t in ts.list_todos(view="planned", now=NOW)] == [plan["todo_id"]]
    for gone in ("assigned", "person", "everything"):
        with pytest.raises(ts.TodoError, match="view"):
            ts.list_todos(view=gone, now=NOW)


def test_a_clients_tasks_are_listed_by_matter():
    a, b = _make("for 601", matter_id=601), _make("for 598", matter_id=598)
    assert [t["todo_id"] for t in ts.list_todos(view="all", matter_id=601, now=NOW)] == [a["todo_id"]]
    assert {t["todo_id"] for t in ts.list_todos(view="all", now=NOW)} == {a["todo_id"], b["todo_id"]}


def test_open_tasks_come_first_soonest_due_first_and_undated_last():
    later = _make("later", due="2026-10-10")
    sooner = _make("sooner", due="2026-09-26")
    undated = _make("undated")
    done = _make("done", due="2026-09-01")
    ts.complete(done["todo_id"], True, by="Sam", now=NOW)
    order = [t["todo_id"] for t in ts.list_todos(view="all", include_done=True, now=NOW)]
    assert order == [sooner["todo_id"], later["todo_id"], undated["todo_id"], done["todo_id"]]


def test_update_changes_only_what_it_is_given_and_can_clear_a_due():
    todo = _make("old", due="2026-09-30", starred=True)
    changed = ts.update(todo["todo_id"], {"title": "new", "my_day": True}, by="Sam", now=NOW)
    assert changed["title"] == "new" and changed["on_my_day_today"] is True
    assert changed["due_utc"] == todo["due_utc"] and changed["starred"] is True
    cleared = ts.update(todo["todo_id"], {"due_utc": None, "my_day": False, "starred": False}, by="Sam", now=NOW)
    assert cleared["due_utc"] is None and cleared["due_has_time"] is False and cleared["on_my_day_today"] is False
    with pytest.raises(ts.TodoError, match="cannot change"):
        ts.update(todo["todo_id"], {"assignee": ME}, by="Sam", now=NOW)
    with pytest.raises(ts.TodoError, match="no such task"):
        ts.update("nope", {"title": "x"}, by="Sam", now=NOW)


def _row(todo_id):
    with clientdb_sql.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT deleted_utc FROM client_todos WHERE todo_id = ?", (todo_id,))
        return cursor.fetchone()


def test_delete_erases_a_task_a_person_made():
    todo = _make("gone")
    ts.delete(todo["todo_id"], now=NOW)
    assert ts.list_todos(view="all", include_done=True, now=NOW) == []
    assert _row(todo["todo_id"]) is None, "the row is gone, not hidden"
    with pytest.raises(ts.TodoError, match="no such task"):
        ts.delete(todo["todo_id"], now=NOW)


def test_delete_only_hides_an_automatic_task_so_the_same_event_cannot_make_it_again():
    auto = _make("chase the court", source="nudge", source_ref="court_reply|601|2026-09-20")
    ts.delete(auto["todo_id"], now=NOW)
    assert ts.list_todos(view="all", include_done=True, now=NOW) == []
    assert _row(auto["todo_id"])[0], "kept, hidden"
    again = _make("chase the court", source="nudge", source_ref="court_reply|601|2026-09-20")
    assert again["todo_id"] == auto["todo_id"] and ts.list_todos(view="all", include_done=True, now=NOW) == []


def test_no_name_is_needed_to_add_finish_reopen_or_delete_a_task():
    todo = ts.create("no name given", now=NOW)
    assert todo["created_by"] == ts.ACTOR == "CaseForge"
    done = ts.complete(todo["todo_id"], True, now=NOW)
    assert done["is_done"] and done["done_by"] == "CaseForge"
    assert ts.complete(todo["todo_id"], False, now=NOW)["is_done"] is False
    ts.update(todo["todo_id"], {"starred": True}, now=NOW)
    ts.delete(todo["todo_id"], now=NOW)
    assert ts.get(todo["todo_id"]) is None


def test_an_automatic_task_is_made_once_per_source():
    first = _make("complaint from email", source="mail_triage", source_ref="CaseForge-MAIL-TASK:abc")
    again = _make("complaint from email, second look", source="mail_triage", source_ref="CaseForge-MAIL-TASK:abc")
    assert again["todo_id"] == first["todo_id"] and len(ts.list_todos(view="all", now=NOW)) == 1
    assert _make("other", source="mail_triage", source_ref="CaseForge-MAIL-TASK:def")["todo_id"] != first["todo_id"]


def test_the_summary_counts_and_the_badge_are_the_owners_own():
    _make("overdue", due="2026-09-24", owner=USER_A)
    _make("due today", due="2026-09-25", owner=USER_A)
    _make("due next week", due="2026-10-02", owner=USER_A)
    _make("starred", starred=True, my_day=True, owner=USER_A)
    _make("overdue, the other login's", due="2026-09-20", owner=USER_B)
    mine = ts.summary(owner=USER_A, now=NOW)
    assert mine["open"] == 4 and mine["overdue"] == 1 and mine["important"] == 1 and mine["my_day"] == 1 and mine["planned"] == 3
    assert mine["attention"] == 2, "the overdue one and the due-today one, not the other login's"
    assert "assigned_to_me" not in mine and not any(k.startswith("person_") for k in mine)
    assert ts.summary(owner="", now=NOW)["open"] == 0, "no login, nothing"


def test_a_personal_task_is_seen_and_changed_only_by_its_owner():
    mine = _make("mine", owner=USER_A, matter_id=601)
    assert mine["assignee"] == "", "nothing is assigned to another person"
    assert [t["todo_id"] for t in ts.list_todos(view="all", owner=USER_A, now=NOW)] == [mine["todo_id"]]
    assert ts.list_todos(view="all", owner=USER_B, now=NOW) == [] and ts.list_todos(view="all", owner="", now=NOW) == []
    assert ts.get(mine["todo_id"], owner=USER_B) is None
    for call in (
        lambda: ts.update(mine["todo_id"], {"title": "x"}, owner=USER_B),
        lambda: ts.complete(mine["todo_id"], True, owner=USER_B),
        lambda: ts.delete(mine["todo_id"], owner=USER_B),
        lambda: ts.set_draft_link(mine["todo_id"], "https://x.test", owner=USER_B),
    ):
        with pytest.raises(ts.TodoError, match="no such task"):
            call()
    assert ts.complete(mine["todo_id"], True, owner=USER_A, now=NOW)["is_done"]
    assert [t["todo_id"] for t in ts.list_todos(view="completed", owner=USER_A, now=NOW)] == [mine["todo_id"]]
    assert ts.list_todos(view="completed", owner=USER_B, now=NOW) == []
    assert ts.summary(owner=USER_B, now=NOW)["completed"] == 0 and ts.summary(owner=USER_A, now=NOW)["completed"] == 1
    with pytest.raises(ts.TodoError, match="owner"):
        ts.create("no login", owner="  ", now=NOW)


def test_automatic_and_ownerless_tasks_never_appear_in_a_personal_list():
    auto = _make("chase", source="nudge", source_ref="r|1", owner=USER_A)
    legacy = _make("pre-personal")
    assert ts.list_todos(view="all", owner=USER_A, now=NOW) == []
    assert ts.get(auto["todo_id"], owner=USER_A) is None and ts.get(legacy["todo_id"], owner=USER_A) is None
    assert {t["todo_id"] for t in ts.list_todos(view="all", now=NOW)} == {auto["todo_id"], legacy["todo_id"]}, "the system still reads them"




def _done(title, when, **kw):
    todo = _make(title, **kw)
    ts.complete(todo["todo_id"], True, by=THIRD, now=when)
    return todo


def test_tasks_is_every_open_task_and_never_a_completed_one():
    open_one, open_two = _make("still to do"), _make("also open", starred=True)
    done = _done("finished", NOW)
    ids = {t["todo_id"] for t in ts.list_todos(view="tasks", now=NOW)}
    assert ids == {open_one["todo_id"], open_two["todo_id"]} and done["todo_id"] not in ids
    assert {t["todo_id"] for t in ts.list_todos(view="tasks", include_done=True, now=NOW)} == ids


def test_completed_lists_only_finished_tasks_newest_finished_first():
    _make("open")
    first = _done("finished early", NOW)
    second = _done("finished later", LATER)
    listed = ts.list_todos(view="completed", now=LATER)
    assert [t["todo_id"] for t in listed] == [second["todo_id"], first["todo_id"]]
    assert all(t["is_done"] for t in listed) and listed[0]["done_by"] == THIRD


def test_a_hidden_task_is_in_no_list_even_completed():
    gone = _done("removed after finishing", NOW, source="nudge", source_ref="x|1|2026-09-01")
    ts.delete(gone["todo_id"], by="Sam", now=NOW)
    assert ts.list_todos(view="completed", now=NOW) == []
    assert ts.list_todos(view="all", include_done=True, now=NOW) == []


def test_all_with_completed_included_is_open_and_finished_together():
    a = _make("open")
    b = _done("finished", NOW)
    assert {t["todo_id"] for t in ts.list_todos(view="all", include_done=True, now=NOW)} == {a["todo_id"], b["todo_id"]}
    assert {t["todo_id"] for t in ts.list_todos(view="all", now=NOW)} == {a["todo_id"]}, "without the flag it is open only, as before"


def test_reopening_a_completed_task_moves_it_back_to_tasks():
    todo = _done("finished", NOW)
    ts.complete(todo["todo_id"], False, by="Sam", now=LATER)
    assert ts.list_todos(view="completed", now=LATER) == []
    assert [t["todo_id"] for t in ts.list_todos(view="tasks", now=LATER)] == [todo["todo_id"]]


def test_the_summary_counts_the_new_lists():
    _make("one"), _make("two")
    _done("three", NOW)
    counts = ts.summary(now=NOW)
    assert counts["tasks"] == 2 and counts["open"] == 2 and counts["completed"] == 1 and counts["all"] == 3


def test_task_sizes_are_capped_at_the_stated_limits():
    todo = _make("x" * 500, notes="n" * 5000)
    assert len(todo["title"]) == ts.TITLE_MAX == 300
    assert len(todo["notes"]) == ts.NOTES_MAX == 4000


def test_a_task_for_a_case_is_assigned_to_nobody():
    assert _make(matter_id=777)["assignee"] == ""
    assert _make()["assignee"] == ""




def _rule(rule, matter=601, **kw):
    return _make(f"chase {rule}", source="nudge", source_ref=f"{rule}|{matter}|2026-09-20", **kw)


def test_every_nudge_rule_belongs_to_one_category():
    import json
    from pathlib import Path

    rules = json.loads((Path(ts.__file__).resolve().parents[2] / "runtime-data" / "nudge-rules.json").read_text(encoding="utf-8"))["rules"]
    mapped = [rule for _, _, rules_ in ts.CATEGORIES for rule in rules_]
    assert sorted(r["id"] for r in rules) == sorted(mapped) and len(mapped) == len(set(mapped))


def test_automatic_tasks_show_to_everyone_only_in_their_category_and_all():
    court = _rule("court_reply_overdue")
    _rule("draft_unsent", matter=602)
    mine = _make("mine", owner=USER_A, starred=True, due="2026-10-01", my_day=True)
    for user in (USER_A, USER_B):
        assert [t["todo_id"] for t in ts.list_todos(view="auto_court", owner=user, now=NOW)] == [court["todo_id"]]
        assert {t["title"] for t in ts.list_todos(view="auto_drafts", owner=user, now=NOW)} == {"chase draft_unsent"}
    for view in ("my_day", "important", "planned", "tasks"):
        ids = {t["todo_id"] for t in ts.list_todos(view=view, owner=USER_A, now=NOW)}
        assert court["todo_id"] not in ids, view
    assert {t["todo_id"] for t in ts.list_todos(view="all", owner=USER_A, now=NOW)} >= {mine["todo_id"], court["todo_id"]}
    assert mine["todo_id"] not in {t["todo_id"] for t in ts.list_todos(view="all", owner=USER_B, now=NOW)}
    assert court["todo_id"] not in {t["todo_id"] for t in ts.list_todos(view="all", matter_id=601, owner=USER_A, now=NOW)}
    counts = ts.summary(owner=USER_B, now=NOW)
    assert counts["cat_court"] == 1 and counts["cat_drafts"] == 1 and counts["all"] == 2 and counts["open"] == 0 and counts["auto_on"] == 1
    with pytest.raises(ts.TodoError, match="owner"):
        ts.list_todos(view="auto_court", now=NOW)


def test_the_firm_switches_hide_automatic_tasks_for_everyone():
    court = _rule("court_reply_overdue")
    _rule("final_hearing_bundle", matter=602)
    import app_settings

    app_settings.apply_changes("user-b", {"todo_hidden_categories": "court"})
    assert ts.list_todos(view="auto_court", owner=USER_A, now=NOW) == []
    assert ts.summary(owner=USER_A, now=NOW)["hide_court"] == 1 and ts.summary(owner=USER_A, now=NOW)["cat_court"] == 0
    assert len(ts.list_todos(view="auto_bundle", owner=USER_A, now=NOW)) == 1
    with pytest.raises(ts.TodoError, match="no such task"):
        ts.complete(court["todo_id"], True, owner=USER_A, now=NOW)
    app_settings.apply_changes("user-b", {"todo_show_automatic": False})
    assert ts.list_todos(view="auto_bundle", owner=USER_A, now=NOW) == [] and ts.list_todos(view="all", owner=USER_A, now=NOW) == []
    assert ts.summary(owner=USER_A, now=NOW)["auto_on"] == 0
    app_settings.apply_changes("user-b", {"todo_show_automatic": True, "todo_hidden_categories": ""})
    assert len(ts.list_todos(view="all", owner=USER_A, now=NOW)) == 2


def test_a_login_can_tick_an_automatic_task_but_not_change_or_delete_it():
    auto = _rule("signing_ccl")
    assert ts.complete(auto["todo_id"], True, owner=USER_B, now=NOW)["is_done"]
    assert ts.list_todos(view="auto_signing", owner=USER_A, now=NOW) == [], "done, so off the open category"
    for call in (lambda: ts.update(auto["todo_id"], {"starred": True}, owner=USER_A), lambda: ts.delete(auto["todo_id"], owner=USER_A)):
        with pytest.raises(ts.TodoError, match="no such task"):
            call()


def test_tasks_is_every_open_task_and_planned_the_dated_subset():
    dated = _make("dated", due="2026-10-05", owner=USER_A)
    plain = _make("undated", owner=USER_A)
    assert {t["todo_id"] for t in ts.list_todos(view="tasks", owner=USER_A, now=NOW)} == {dated["todo_id"], plain["todo_id"]}
    assert [t["todo_id"] for t in ts.list_todos(view="planned", owner=USER_A, now=NOW)] == [dated["todo_id"]]
    counts = ts.summary(owner=USER_A, now=NOW)
    assert counts["tasks"] == 2 and counts["planned"] == 1 and counts["open"] == 2


def test_a_blocked_case_flow_step_is_the_case_flow_category():
    blocked = _make("Auto mode could not do the court pack step", source="auto-blocked", source_ref="601|court_pack|2026-09-20", matter_id=601)
    for user in (USER_A, USER_B):
        assert [t["todo_id"] for t in ts.list_todos(view="auto_caseflow", owner=user, now=NOW)] == [blocked["todo_id"]]
        assert blocked["todo_id"] in {t["todo_id"] for t in ts.list_todos(view="all", owner=user, now=NOW)}
        assert ts.list_todos(view="tasks", owner=user, now=NOW) == []
    assert ts.summary(owner=USER_A, now=NOW)["cat_caseflow"] == 1
    import app_settings

    app_settings.apply_changes("user-b", {"todo_hidden_categories": "caseflow"})
    assert ts.list_todos(view="auto_caseflow", owner=USER_A, now=NOW) == [] and ts.list_todos(view="all", owner=USER_A, now=NOW) == []
