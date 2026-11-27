from __future__ import annotations

import csv
import re
from decimal import Decimal
from typing import Any, Iterable, Mapping

_FORMULA_LEADERS = ("=", "+", "-", "@", "\t", "\r", "\n")
_PLAIN_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


def safe_cell(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float, Decimal)):
        return value
    text = value if isinstance(value, str) else str(value)
    if text[:1] in _FORMULA_LEADERS and not _PLAIN_NUMBER.match(text):
        return "'" + text
    return text


def safe_row(row: Iterable[Any]) -> list[Any]:
    return [safe_cell(cell) for cell in row]


class _SafeWriter:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def writerow(self, row: Iterable[Any]) -> Any:
        return self._inner.writerow(safe_row(row))

    def writerows(self, rows: Iterable[Iterable[Any]]) -> None:
        for row in rows:
            self.writerow(row)


class _SafeDictWriter(_SafeWriter):
    def writeheader(self) -> Any:
        return self._inner.writeheader()

    def writerow(self, row: Mapping[str, Any]) -> Any:
        return self._inner.writerow({key: safe_cell(value) for key, value in row.items()})

    def writerows(self, rows: Iterable[Mapping[str, Any]]) -> None:
        for row in rows:
            self.writerow(row)


def writer(fileobj: Any, **kwargs: Any) -> _SafeWriter:
    return _SafeWriter(csv.writer(fileobj, **kwargs))


def dict_writer(fileobj: Any, fieldnames: Iterable[str], **kwargs: Any) -> _SafeDictWriter:
    return _SafeDictWriter(csv.DictWriter(fileobj, fieldnames=list(fieldnames), **kwargs))
