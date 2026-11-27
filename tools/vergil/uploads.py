
from __future__ import annotations

import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from vergil.primitives import safe_upload_name
from zip_safe import read_member

MAX_ZIP_MEMBERS = 100
MAX_ZIP_MEMBER_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_TEXT_CHARS = 8_000
UPLOAD_BLOCKLIST = {
    ".app", ".bat", ".cmd", ".com", ".dmg", ".exe", ".jar", ".js", ".jse",
    ".lnk", ".msi", ".ps1", ".scr", ".sh", ".vbe", ".vbs", ".wsf",
}
UPLOAD_TEXT_EXTENSIONS = {
    ".csv", ".eml", ".json", ".log", ".md", ".rtf", ".text", ".txt", ".xml", ".yaml", ".yml",
}
UPLOAD_DIR = Path.home() / ".caseforge-chat-uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_FILES = 20
MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def unique_path(path: Path) -> Path:
    target = path
    stem = target.stem
    suffix = target.suffix
    counter = 1
    while target.exists():
        target = path.with_name(f"{stem}-{counter}{suffix}")
        counter += 1
    return target


def is_blocked_upload(path: Path) -> bool:
    return path.suffix.lower() in UPLOAD_BLOCKLIST


def safe_zip_member_path(base_dir: Path, name: str) -> Path | None:
    raw = Path(name)
    if raw.is_absolute() or any(part in {"", ".", ".."} for part in raw.parts):
        return None
    parts = [safe_upload_name(part) for part in raw.parts]
    if not parts:
        return None
    return base_dir.joinpath(*parts)


def extract_zip_upload(zip_path: Path, extract_dir: Path) -> tuple[list[Path], list[str]]:
    extracted: list[Path] = []
    notices: list[str] = []
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members = [m for m in zf.infolist() if not m.is_dir()]
            if len(members) > MAX_ZIP_MEMBERS:
                notices.append(f"{zip_path.name}: only the first {MAX_ZIP_MEMBERS} files were extracted from the zip.")
                members = members[:MAX_ZIP_MEMBERS]
            extract_dir.mkdir(parents=True, exist_ok=True)
            total_bytes = 0
            for member in members:
                target = safe_zip_member_path(extract_dir, member.filename)
                if target is None:
                    notices.append(f"{zip_path.name}: skipped unsafe zip path {member.filename!r}.")
                    continue
                if is_blocked_upload(target):
                    notices.append(f"{zip_path.name}: skipped blocked file {member.filename!r}.")
                    continue
                if member.file_size > MAX_ZIP_MEMBER_BYTES:
                    notices.append(f"{zip_path.name}: skipped {member.filename!r}; it is too large.")
                    continue
                total_bytes += member.file_size
                if total_bytes > MAX_UPLOAD_BYTES:
                    notices.append(f"{zip_path.name}: stopped extracting at the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB total limit.")
                    break
                target = unique_path(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as source, open(target, "wb") as dest:
                    shutil.copyfileobj(source, dest, length=1024 * 1024)
                target.chmod(0o600)
                extracted.append(target)
    except zipfile.BadZipFile:
        notices.append(f"{zip_path.name}: zip file could not be opened.")
    except Exception as exc:
        notices.append(f"{zip_path.name}: zip extraction failed ({exc}).")
    return extracted, notices


def extract_text_direct(path: Path) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix in UPLOAD_TEXT_EXTENSIONS:
            return path.read_text(encoding="utf-8", errors="replace")[:MAX_EXTRACTED_TEXT_CHARS]
        if suffix == ".docx":
            import xml.etree.ElementTree as ET
            with zipfile.ZipFile(path) as zf:
                xml = read_member(zf, "word/document.xml")
            root = ET.fromstring(xml)
            text = "\n".join(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
            return text[:MAX_EXTRACTED_TEXT_CHARS]
        if suffix == ".xlsx":
            import xml.etree.ElementTree as ET
            chunks: list[str] = []
            with zipfile.ZipFile(path) as zf:
                if "xl/sharedStrings.xml" in zf.namelist():
                    root = ET.fromstring(read_member(zf, "xl/sharedStrings.xml"))
                    chunks.extend(node.text or "" for node in root.iter() if node.tag.endswith("}t"))
            return "\n".join(chunks)[:MAX_EXTRACTED_TEXT_CHARS]
        if suffix == ".pdf":
            data = path.read_bytes()[:2_000_000]
            text = re.sub(rb"[^A-Za-z0-9.,;:!?@#%&()\[\]{}_\-+=/\\'\"\s]+", b" ", data)
            return text.decode("utf-8", errors="replace")[:MAX_EXTRACTED_TEXT_CHARS]
    except Exception:
        return ""
    return ""


_BWRAP_EXTRACTOR = r"""
import pathlib, re, sys, zipfile, xml.etree.ElementTree as ET
p = pathlib.Path(sys.argv[1])
limit = 8000
max_member = 20 * 1024 * 1024

def member(zf, name):
    if zf.getinfo(name).file_size > max_member:
        raise ValueError('member too large')
    return zf.read(name)
s = p.suffix.lower()
try:
    if s in {'.csv','.eml','.json','.log','.md','.rtf','.text','.txt','.xml','.yaml','.yml'}:
        print(p.read_text(encoding='utf-8', errors='replace')[:limit])
    elif s == '.docx':
        with zipfile.ZipFile(p) as zf:
            root = ET.fromstring(member(zf, 'word/document.xml'))
        print('\n'.join(n.text or '' for n in root.iter() if n.tag.endswith('}t'))[:limit])
    elif s == '.xlsx':
        chunks = []
        with zipfile.ZipFile(p) as zf:
            if 'xl/sharedStrings.xml' in zf.namelist():
                root = ET.fromstring(member(zf, 'xl/sharedStrings.xml'))
                chunks.extend(n.text or '' for n in root.iter() if n.tag.endswith('}t'))
        print('\n'.join(chunks)[:limit])
    elif s == '.pdf':
        data = p.read_bytes()[:2000000]
        text = re.sub(rb"[^A-Za-z0-9.,;:!?@#%&()\[\]{}_\-+=/\\'\"\s]+", b' ', data)
        print(text.decode('utf-8', errors='replace')[:limit])
except Exception:
    pass
"""


def extract_upload_text(path: Path) -> tuple[str, str]:
    if path.suffix.lower() not in UPLOAD_TEXT_EXTENSIONS | {".docx", ".xlsx", ".pdf"}:
        return "", ""

    bwrap = shutil.which("bwrap")
    py = shutil.which("python3") or sys.executable
    if bwrap and py:
        cmd = [bwrap]
        for bind_path in ("/usr", "/usr/local", "/bin", "/lib", "/lib64"):
            if Path(bind_path).exists():
                cmd += ["--ro-bind", bind_path, bind_path]
        ld_cache = Path("/etc/ld.so.cache")
        if ld_cache.exists():
            cmd += ["--ro-bind", str(ld_cache), str(ld_cache)]
        cmd += [
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--ro-bind", str(path), "/upload-file",
            "--unshare-net",
            "--unshare-pid",
            "--unshare-ipc",
            "--die-with-parent",
            "--",
            py,
            "-c",
            _BWRAP_EXTRACTOR,
            "/upload-file",
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=8, check=False)
            text = (result.stdout or "").strip()
            if text:
                return text[:MAX_EXTRACTED_TEXT_CHARS], "bubblewrap"
        except Exception:
            pass

    if os.environ.get("CASEFORGE_CHAT_ALLOW_DIRECT_UPLOAD_PARSE", "").strip() == "1":
        return extract_text_direct(path).strip()[:MAX_EXTRACTED_TEXT_CHARS], "direct"
    return "", "sandbox-unavailable"


def cleanup_old_uploads(max_age_days: int = 7) -> None:
    try:
        cutoff = dt.datetime.utcnow() - dt.timedelta(days=max_age_days)
        for user_dir in UPLOAD_DIR.iterdir():
            if not user_dir.is_dir():
                continue
            for batch_dir in user_dir.iterdir():
                if not batch_dir.is_dir():
                    continue
                try:
                    mtime = dt.datetime.utcfromtimestamp(batch_dir.stat().st_mtime)
                    if mtime < cutoff:
                        import shutil as _shutil
                        _shutil.rmtree(batch_dir, ignore_errors=True)
                except Exception:
                    pass
    except Exception:
        pass


def append_upload_context(prompt: str, paths: list[Path], excerpts: list[str], notices: list[str]) -> str:
    if not paths and not excerpts and not notices:
        return prompt
    lines = ["", "", "Attached files saved on the VM:"]
    lines.extend(f"- {path}" for path in paths[:120])
    if len(paths) > 120:
        lines.append(f"- ... {len(paths) - 120} more extracted file(s)")
    if notices:
        lines += ["", "Upload handling notes:"]
        lines.extend(f"- {notice}" for notice in notices)
    if excerpts:
        lines += ["", "Sandboxed text extracted from uploaded files:"]
        for excerpt in excerpts[:12]:
            lines += ["", excerpt]
        if len(excerpts) > 12:
            lines.append(f"\n... {len(excerpts) - 12} more text excerpt(s) omitted.")
    lines.append("")
    lines.append("Use extracted text first. Only inspect raw uploaded file paths if more detail is necessary.")
    return prompt.rstrip() + "\n".join(lines)
