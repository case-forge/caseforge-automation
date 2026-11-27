from __future__ import annotations

from pathlib import Path

import ops_db


def _item(path: str, item_id: str, *, parent: str = "", item_type: str = "folder") -> dict:
    return {
        "path": path, "name": path.rsplit("/", 1)[-1], "item_id": item_id,
        "drive_id": "drive-1", "parent_item_id": parent, "root_name": "Clients - Alex",
        "type": item_type, "modified": "2026-05-18T12:00:00Z",
        "size": 10 if item_type == "file" else None,
    }


def test_list_onedrive_subtree_returns_everything_under_root_sorted(tmp_path: Path):
    db = tmp_path / "ops.sqlite3"
    root = "Company_Data/Clients Live Files - Example/Clients - Alex/Jane Ashtest"
    ops_db.upsert_onedrive_items(
        [
            _item(root, "root"),
            _item(f"{root}/Correspondences - SMITH", "corr", parent="root"),
            _item(f"{root}/Correspondences - SMITH/b.pdf", "f2", parent="corr", item_type="file"),
            _item(f"{root}/Correspondences - SMITH/a.pdf", "f1", parent="corr", item_type="file"),
            _item("Company_Data/Clients Live Files - Example/Clients - Alex/Other Client", "other"),
        ],
        db_path=db,
    )
    items = ops_db.list_onedrive_subtree(root, db_path=db)
    paths = [i["path"] for i in items]
    assert paths == sorted(paths, key=str.lower)
    assert all(p.startswith(root + "/") for p in paths)
    assert not any("Other Client" in p for p in paths)
    assert len(items) == 3
