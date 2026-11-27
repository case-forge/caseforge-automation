from __future__ import annotations

import os
import sys

from conftest import snapshot_process_state


def test_environment_cwd_and_purged_modules_are_put_back(tmp_path):
    import vergil.primitives

    before = sys.modules["vergil.primitives"]
    os.environ["CASEFORGE_LEAK_CHECK_SET"] = "x"
    restore = snapshot_process_state()
    os.environ["CASEFORGE_LEAK_CHECK_NEW"] = "1"
    os.environ["CASEFORGE_LEAK_CHECK_SET"] = "changed"
    os.chdir(tmp_path)
    for name in [m for m in sys.modules if m == "vergil" or m.startswith("vergil.")]:
        del sys.modules[name]
    import vergil.primitives as fresh

    assert fresh is not before
    restore()
    assert "CASEFORGE_LEAK_CHECK_NEW" not in os.environ and os.environ["CASEFORGE_LEAK_CHECK_SET"] == "x"
    assert os.getcwd() != str(tmp_path)
    assert sys.modules["vergil.primitives"] is before
    del os.environ["CASEFORGE_LEAK_CHECK_SET"]


def test_modules_added_normally_are_kept():
    restore = snapshot_process_state()
    import json.tool

    restore()
    assert "json.tool" in sys.modules
