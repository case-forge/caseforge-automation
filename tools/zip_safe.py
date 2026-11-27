
from __future__ import annotations

import zipfile

MAX_MEMBER_BYTES = 20 * 1024 * 1024


class MemberTooLarge(ValueError):
    pass


def read_member(archive: zipfile.ZipFile, name: str | zipfile.ZipInfo, limit: int = MAX_MEMBER_BYTES) -> bytes:
    info = name if isinstance(name, zipfile.ZipInfo) else archive.getinfo(name)
    if info.file_size > limit:
        raise MemberTooLarge(f"{info.filename}: {info.file_size} bytes exceeds the {limit} byte limit")
    with archive.open(info) as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise MemberTooLarge(f"{info.filename}: inflated past the {limit} byte limit")
    return data


def check_members(archive: zipfile.ZipFile, limit: int = MAX_MEMBER_BYTES) -> None:
    for info in archive.infolist():
        if info.file_size > limit:
            raise MemberTooLarge(f"{info.filename}: {info.file_size} bytes exceeds the {limit} byte limit")
