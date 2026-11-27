from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil import workflow_actions


def test_actions_table_has_no_duplicate_labels():
    labels = [row[0] for row in workflow_actions.ACTIONS]
    assert len(labels) == len(set(labels))


def test_actions_table_entries_are_four_tuples():
    for row in workflow_actions.ACTIONS:
        assert len(row) == 4
        label, icon, prompt, auto_send = row
        assert isinstance(label, str) and label
        assert isinstance(icon, str) and icon.startswith(":material/")
        assert isinstance(prompt, str) and prompt
        assert isinstance(auto_send, bool)


def test_every_client_action_label_exists_in_actions_table():
    labels = {row[0] for row in workflow_actions.ACTIONS}
    assert workflow_actions.CLIENT_ACTION_LABELS <= labels


def test_every_start_task_action_label_exists_in_actions_table():
    labels = {row[0] for row in workflow_actions.ACTIONS}
    assert workflow_actions.START_TASK_ACTION_LABELS <= labels


def test_label_groups_do_not_overlap():
    groups = (
        workflow_actions.CLIENT_ACTION_LABELS,
        workflow_actions.START_TASK_ACTION_LABELS,
        workflow_actions.COUNSEL_ACTION_LABELS,
        workflow_actions.COURT_ACTION_LABELS,
    )
    for i, a in enumerate(groups):
        for b in groups[i + 1 :]:
            assert not (a & b)



def test_client_action_rows_returns_only_client_action_labels():
    rows = workflow_actions.client_action_rows()
    labels = {row[0] for row in rows}
    assert labels == workflow_actions.CLIENT_ACTION_LABELS


def test_client_action_rows_excludes_auto_send_actions():
    rows = workflow_actions.client_action_rows()
    auto_send_labels = {label for label, _icon, _prompt, auto_send in workflow_actions.ACTIONS if auto_send}
    labels = {row[0] for row in rows}
    assert not (labels & auto_send_labels)


def test_client_action_rows_rows_are_three_tuples():
    rows = workflow_actions.client_action_rows()
    for row in rows:
        assert len(row) == 3



def test_action_rows_for_returns_rows_matching_requested_labels():
    rows = workflow_actions.action_rows_for(workflow_actions.COUNSEL_ACTION_LABELS)
    assert {row[0] for row in rows} == workflow_actions.COUNSEL_ACTION_LABELS


def test_action_rows_for_court_labels_returns_all_four():
    rows = workflow_actions.action_rows_for(workflow_actions.COURT_ACTION_LABELS)
    assert {row[0] for row in rows} == workflow_actions.COURT_ACTION_LABELS


def test_action_rows_for_unknown_label_returns_nothing():
    rows = workflow_actions.action_rows_for({"Not A Real Label"})
    assert rows == []


def test_action_rows_for_empty_label_set_returns_nothing():
    assert workflow_actions.action_rows_for(set()) == []
