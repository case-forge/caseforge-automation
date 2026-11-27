import datetime as dt
import os
import shutil
import sys
import time
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from vergil import uploads


class _FakeUpload:

    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getbuffer(self) -> bytes:
        return self._data



def test_constants_have_expected_values():
    assert uploads.MAX_ZIP_MEMBERS == 100
    assert uploads.MAX_ZIP_MEMBER_BYTES == 50 * 1024 * 1024
    assert uploads.MAX_EXTRACTED_TEXT_CHARS == 8_000
    assert ".exe" in uploads.UPLOAD_BLOCKLIST
    assert ".txt" in uploads.UPLOAD_TEXT_EXTENSIONS


def test_upload_limit_constants_have_expected_values():
    assert uploads.MAX_UPLOAD_FILES == 20
    assert uploads.MAX_UPLOAD_BYTES == 200 * 1024 * 1024



def test_unique_path_returns_same_path_when_absent(tmp_path):
    target = tmp_path / "file.txt"
    assert uploads.unique_path(target) == target


def test_unique_path_increments_on_single_collision(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("x")
    assert uploads.unique_path(target) == tmp_path / "file-1.txt"


def test_unique_path_increments_past_multiple_collisions(tmp_path):
    (tmp_path / "file.txt").write_text("x")
    (tmp_path / "file-1.txt").write_text("x")
    (tmp_path / "file-2.txt").write_text("x")
    assert uploads.unique_path(tmp_path / "file.txt") == tmp_path / "file-3.txt"



def test_is_blocked_upload_rejects_known_executable_extensions(tmp_path):
    for name in ("malware.exe", "script.sh", "run.ps1", "installer.msi", "thing.jar"):
        assert uploads.is_blocked_upload(tmp_path / name), name


def test_is_blocked_upload_is_case_insensitive(tmp_path):
    assert uploads.is_blocked_upload(tmp_path / "SCRIPT.SH")


def test_is_blocked_upload_allows_ordinary_documents(tmp_path):
    for name in ("notes.txt", "letter.docx", "figures.xlsx", "noextension"):
        assert not uploads.is_blocked_upload(tmp_path / name), name



def test_safe_zip_member_path_joins_relative_name(tmp_path):
    result = uploads.safe_zip_member_path(tmp_path, "folder/file.txt")
    assert result == tmp_path / "folder" / "file.txt"


def test_safe_zip_member_path_rejects_absolute_path(tmp_path):
    assert uploads.safe_zip_member_path(tmp_path, "/etc/passwd") is None


def test_safe_zip_member_path_rejects_leading_traversal(tmp_path):
    assert uploads.safe_zip_member_path(tmp_path, "../../etc/passwd") is None


def test_safe_zip_member_path_rejects_traversal_in_middle(tmp_path):
    assert uploads.safe_zip_member_path(tmp_path, "a/../b.txt") is None


def test_safe_zip_member_path_rejects_empty_name(tmp_path):
    assert uploads.safe_zip_member_path(tmp_path, "") is None



def test_extract_zip_upload_extracts_regular_member(tmp_path):
    zpath = tmp_path / "up.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("hello.txt", "hi there")
    extracted, notices = uploads.extract_zip_upload(zpath, tmp_path / "out")
    assert len(extracted) == 1
    assert extracted[0].read_text() == "hi there"
    assert notices == []


def test_extract_zip_upload_skips_unsafe_traversal_path(tmp_path):
    zpath = tmp_path / "evil.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../../evil.txt", "bad")
    extracted, notices = uploads.extract_zip_upload(zpath, tmp_path / "out2")
    assert extracted == []
    assert any("unsafe zip path" in n for n in notices)


def test_extract_zip_upload_skips_blocked_extension(tmp_path):
    zpath = tmp_path / "block.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("virus.exe", "MZ")
    extracted, notices = uploads.extract_zip_upload(zpath, tmp_path / "out3")
    assert extracted == []
    assert any("blocked file" in n for n in notices)


def test_extract_zip_upload_skips_oversized_member(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_ZIP_MEMBER_BYTES", 4)
    zpath = tmp_path / "big.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("big.txt", "way too much data")
    extracted, notices = uploads.extract_zip_upload(zpath, tmp_path / "out4")
    assert extracted == []
    assert any("too large" in n for n in notices)


def test_extract_zip_upload_caps_member_count(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_ZIP_MEMBERS", 1)
    zpath = tmp_path / "many.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a.txt", "a")
        zf.writestr("b.txt", "b")
    extracted, notices = uploads.extract_zip_upload(zpath, tmp_path / "out5")
    assert len(extracted) == 1
    assert any("only the first 1 files" in n for n in notices)


def test_extract_zip_upload_handles_corrupt_zip(tmp_path):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip file at all")
    extracted, notices = uploads.extract_zip_upload(bad, tmp_path / "out6")
    assert extracted == []
    assert any("could not be opened" in n for n in notices)



def test_extract_text_direct_reads_plain_text(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("Plain text content")
    assert uploads.extract_text_direct(p) == "Plain text content"


def test_extract_text_direct_truncates_to_max_chars(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_EXTRACTED_TEXT_CHARS", 5)
    p = tmp_path / "long.txt"
    p.write_text("abcdefghij")
    assert uploads.extract_text_direct(p) == "abcde"


def _write_minimal_docx(path: Path, text: str) -> None:
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", xml)


def _write_minimal_xlsx(path: Path, strings: list[str]) -> None:
    items = "".join(f"<si><t>{s}</t></si>" for s in strings)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{items}</sst>'
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/sharedStrings.xml", xml)


def test_extract_text_direct_reads_docx(tmp_path):
    p = tmp_path / "doc.docx"
    _write_minimal_docx(p, "Hello from docx")
    assert "Hello from docx" in uploads.extract_text_direct(p)


def test_extract_text_direct_reads_xlsx(tmp_path):
    p = tmp_path / "book.xlsx"
    _write_minimal_xlsx(p, ["Alpha", "Beta"])
    text = uploads.extract_text_direct(p)
    assert "Alpha" in text
    assert "Beta" in text


def test_extract_text_direct_xlsx_without_shared_strings_is_empty(tmp_path):
    p = tmp_path / "book.xlsx"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("xl/worksheets/sheet1.xml", "<worksheet/>")
    assert uploads.extract_text_direct(p) == ""


def test_extract_text_direct_unknown_extension_returns_empty(tmp_path):
    p = tmp_path / "image.png"
    p.write_bytes(b"\x89PNG\r\n")
    assert uploads.extract_text_direct(p) == ""


def test_extract_text_direct_missing_file_returns_empty(tmp_path):
    assert uploads.extract_text_direct(tmp_path / "does-not-exist.txt") == ""


def test_extract_text_direct_corrupt_docx_returns_empty(tmp_path):
    p = tmp_path / "broken.docx"
    p.write_bytes(b"not actually a zip")
    assert uploads.extract_text_direct(p) == ""



def test_extract_upload_text_rejects_unsupported_extension(tmp_path):
    p = tmp_path / "image.png"
    p.write_bytes(b"\x89PNG")
    text, mode = uploads.extract_upload_text(p)
    assert text == ""
    assert mode == ""


def test_extract_upload_text_real_run_returns_a_known_mode(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("Sandboxed content")
    text, mode = uploads.extract_upload_text(p)
    assert mode in ("bubblewrap", "direct", "sandbox-unavailable")
    if mode == "bubblewrap":
        assert "Sandboxed content" in text
    else:
        assert text == ""


def test_extract_upload_text_uses_bwrap_when_it_actually_works(tmp_path):
    import subprocess

    import pytest

    if shutil.which("bwrap") is None:
        pytest.skip("bwrap is not installed here")
    try:
        probe = subprocess.run(
            ["bwrap", "--ro-bind", "/usr", "/usr", "--proc", "/proc", "--dev", "/dev",
             "--unshare-net", "--unshare-pid", "--die-with-parent", "--",
             "/usr/bin/python3", "-c", "print('ok')"],
            capture_output=True, text=True, timeout=8, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pytest.skip("bwrap cannot be launched here")
    if probe.returncode != 0 or probe.stdout.strip() != "ok":
        pytest.skip("bwrap cannot run a sandboxed process on this box (nested container)")
    p = tmp_path / "notes.txt"
    p.write_text("Sandboxed content")
    text, mode = uploads.extract_upload_text(p)
    assert mode == "bubblewrap"
    assert "Sandboxed content" in text


def test_extract_upload_text_falls_back_to_direct_when_env_var_set(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads.shutil, "which", lambda name: None)
    monkeypatch.setenv("CASEFORGE_CHAT_ALLOW_DIRECT_UPLOAD_PARSE", "1")
    p = tmp_path / "notes.txt"
    p.write_text("Direct content")
    text, mode = uploads.extract_upload_text(p)
    assert mode == "direct"
    assert text == "Direct content"


def test_extract_upload_text_sandbox_unavailable_without_env_var(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads.shutil, "which", lambda name: None)
    monkeypatch.delenv("CASEFORGE_CHAT_ALLOW_DIRECT_UPLOAD_PARSE", raising=False)
    p = tmp_path / "notes.txt"
    p.write_text("Should not appear")
    text, mode = uploads.extract_upload_text(p)
    assert text == ""
    assert mode == "sandbox-unavailable"



def test_append_upload_context_returns_prompt_unchanged_when_nothing_to_add():
    assert uploads.append_upload_context("draft the letter", [], [], []) == "draft the letter"


def test_append_upload_context_lists_paths(tmp_path):
    path = tmp_path / "notes.txt"
    result = uploads.append_upload_context("draft the letter", [path], [], [])
    assert "draft the letter" in result
    assert str(path) in result
    assert "Attached files saved on the VM:" in result


def test_append_upload_context_includes_notices():
    result = uploads.append_upload_context("draft the letter", [], [], ["skipped one file"])
    assert "Upload handling notes:" in result
    assert "skipped one file" in result


def test_append_upload_context_includes_excerpts():
    result = uploads.append_upload_context("draft the letter", [], ["### notes.txt\ncontent"], [])
    assert "Sandboxed text extracted from uploaded files:" in result
    assert "### notes.txt\ncontent" in result
    assert "Use extracted text first." in result


def test_append_upload_context_truncates_long_path_list(tmp_path):
    paths = [tmp_path / f"file{i}.txt" for i in range(130)]
    result = uploads.append_upload_context("draft the letter", paths, [], [])
    assert "... 10 more extracted file(s)" in result


def test_append_upload_context_truncates_long_excerpt_list():
    excerpts = [f"### file{i}.txt\ncontent{i}" for i in range(15)]
    result = uploads.append_upload_context("draft the letter", [], excerpts, [])
    assert "... 3 more text excerpt(s) omitted." in result


def _age_dir(path: Path, days_old: int) -> None:
    stamp = time.time() - (days_old * 86400)
    os.utime(path, (stamp, stamp))


def test_cleanup_removes_batch_dirs_older_than_max_age(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_DIR", tmp_path)
    assert Path(uploads.UPLOAD_DIR).resolve() == tmp_path.resolve()

    old_batch = tmp_path / "alice" / "20260101-000000"
    old_batch.mkdir(parents=True)
    (old_batch / "upload.txt").write_text("stale", encoding="utf-8")
    _age_dir(old_batch, days_old=10)

    uploads.cleanup_old_uploads(max_age_days=7)

    assert not old_batch.exists()


def test_cleanup_keeps_batch_dirs_within_max_age(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_DIR", tmp_path)
    assert Path(uploads.UPLOAD_DIR).resolve() == tmp_path.resolve()

    recent_batch = tmp_path / "alice" / "20260803-000000"
    recent_batch.mkdir(parents=True)
    (recent_batch / "upload.txt").write_text("fresh", encoding="utf-8")
    _age_dir(recent_batch, days_old=1)

    uploads.cleanup_old_uploads(max_age_days=7)

    assert recent_batch.exists()


def test_cleanup_only_removes_old_batches_not_the_whole_user_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_DIR", tmp_path)
    assert Path(uploads.UPLOAD_DIR).resolve() == tmp_path.resolve()

    user_dir = tmp_path / "alice"
    old_batch = user_dir / "old-batch"
    recent_batch = user_dir / "recent-batch"
    old_batch.mkdir(parents=True)
    recent_batch.mkdir(parents=True)
    _age_dir(old_batch, days_old=30)
    _age_dir(recent_batch, days_old=0)

    uploads.cleanup_old_uploads(max_age_days=7)

    assert not old_batch.exists()
    assert recent_batch.exists()
    assert user_dir.exists()


def test_cleanup_ignores_non_directory_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOAD_DIR", tmp_path)
    assert Path(uploads.UPLOAD_DIR).resolve() == tmp_path.resolve()

    stray_file = tmp_path / "stray.txt"
    stray_file.write_text("not a user dir", encoding="utf-8")
    _age_dir(stray_file, days_old=30)

    uploads.cleanup_old_uploads(max_age_days=7)

    assert stray_file.exists()


def test_cleanup_is_silent_when_upload_dir_is_missing(tmp_path, monkeypatch):
    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr(uploads, "UPLOAD_DIR", missing)
    assert Path(uploads.UPLOAD_DIR).resolve() == missing.resolve()

    uploads.cleanup_old_uploads(max_age_days=7)
