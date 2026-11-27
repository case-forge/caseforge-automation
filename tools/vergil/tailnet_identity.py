#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import contextvars
import ipaddress
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Iterator, Mapping

TAILNET_ROLE = "tailnet"
MACHINE_ROLE = "machine"

TAILNET_IDENTITY_HEADER = "X-CaseForge-Tailnet-Identity"
SERVE_LOGIN_HEADER = "Tailscale-User-Login"
FORWARDED_FOR_HEADER = "X-Forwarded-For"

TAILNET_BUDGET_PREFIX = "__tailnet__"
LOCAL_MACHINE_IDENTITY = "__local_machine__"

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "::ffff:127.0.0.1"})
TAILNET_NETWORKS = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))

WHOIS_TTL_SECONDS = 300
WHOIS_TIMEOUT_SECONDS = 2
_FIELD_RE = re.compile(r"[^A-Za-z0-9@._+-]")
_MAX_FIELD = 120

_REQUEST_CALLER: contextvars.ContextVar[dict | None] = contextvars.ContextVar("vergil_machine_caller", default=None)
_LOCK = threading.Lock()
_WHOIS_CACHE: dict[str, tuple[float, dict]] = {}




@contextlib.contextmanager
def request_caller(caller: dict | None) -> Iterator[None]:
    token = _REQUEST_CALLER.set(caller)
    try:
        yield
    finally:
        _REQUEST_CALLER.reset(token)


def current_caller() -> dict | None:
    return _REQUEST_CALLER.get()


def budget_identity_for(caller: Mapping) -> str:
    if caller.get("role") == TAILNET_ROLE:
        who = caller.get("login") or caller.get("node") or caller.get("ip") or "unknown"
        return f"{TAILNET_BUDGET_PREFIX}{who}"
    return LOCAL_MACHINE_IDENTITY




def _clean(value: object) -> str:
    return _FIELD_RE.sub("_", str(value or "").strip())[:_MAX_FIELD]


def tailnet_ip(value: str | None) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("::ffff:"):
        text = text[7:]
    try:
        addr = ipaddress.ip_address(text)
    except ValueError:
        return ""
    return str(addr) if any(addr in net for net in TAILNET_NETWORKS) else ""


def parse_whois(payload: Mapping) -> dict:
    node = payload.get("Node") if isinstance(payload.get("Node"), Mapping) else {}
    profile = payload.get("UserProfile") if isinstance(payload.get("UserProfile"), Mapping) else {}
    tags = [_clean(tag) for tag in (node.get("Tags") or []) if str(tag).strip()]
    name = str(node.get("ComputedName") or node.get("Name") or "").strip().rstrip(".")
    return {
        "login": "" if tags else _clean(profile.get("LoginName")),
        "node": _clean(name.split(".")[0] if name else ""),
        "tags": tags,
    }


def whois(ip: str) -> dict:
    ip = tailnet_ip(ip)
    if not ip:
        return {}
    now = time.monotonic()
    with _LOCK:
        hit = _WHOIS_CACHE.get(ip)
        if hit and now - hit[0] < WHOIS_TTL_SECONDS:
            return dict(hit[1])
    try:
        done = subprocess.run(
            ["tailscale", "whois", "--json", ip],
            capture_output=True, text=True, timeout=WHOIS_TIMEOUT_SECONDS, check=False,
        )
        result = parse_whois(json.loads(done.stdout)) if done.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, ValueError):
        result = {}
    with _LOCK:
        _WHOIS_CACHE[ip] = (now, result)
    return dict(result)




def _hex_endpoint_v4(host: str, port: int) -> str:
    packed = ipaddress.IPv4Address(host).packed
    return f"{packed[::-1].hex().upper()}:{port:04X}"


def _hex_endpoint_v6(host: str, port: int) -> str:
    host = host if ":" in host else f"::ffff:{host}"
    packed = ipaddress.IPv6Address(host).packed
    words = "".join(packed[i:i + 4][::-1].hex().upper() for i in range(0, 16, 4))
    return f"{words}:{port:04X}"


def _socket_inode(proc: Path, peer_host: str, peer_port: int, local_port: int) -> str:
    candidates = []
    if ":" not in peer_host or peer_host.startswith("::ffff:"):
        v4 = peer_host.removeprefix("::ffff:")
        candidates.append((proc / "net" / "tcp", _hex_endpoint_v4(v4, peer_port), _hex_endpoint_v4("127.0.0.1", local_port)))
    candidates.append((proc / "net" / "tcp6", _hex_endpoint_v6(peer_host, peer_port), None))
    for table, local_hex, remote_hex in candidates:
        try:
            lines = table.read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10 or fields[1] != local_hex:
                continue
            if remote_hex is not None and fields[2] != remote_hex:
                continue
            if remote_hex is None and not fields[2].endswith(f":{local_port:04X}"):
                continue
            return fields[9]
    return ""


_PID_CACHE: dict[str, tuple[float, list[Path]]] = {}
PID_CACHE_SECONDS = 30


def _tailscaled_pids(proc: Path) -> list[Path]:
    now = time.monotonic()
    with _LOCK:
        hit = _PID_CACHE.get(str(proc))
        if hit and now - hit[0] < PID_CACHE_SECONDS and all(p.exists() for p in hit[1]):
            return list(hit[1])
    pids = _scan_tailscaled_pids(proc)
    with _LOCK:
        _PID_CACHE[str(proc)] = (now, pids)
    return pids


def _scan_tailscaled_pids(proc: Path) -> list[Path]:
    pids = []
    try:
        entries = list(proc.iterdir())
    except OSError:
        return pids
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            if (entry / "comm").read_text().strip() == "tailscaled":
                pids.append(entry)
        except OSError:
            continue
    return pids


def is_tailscale_serve_connection(peer_host: str, peer_port: int, local_port: int, *, proc: Path = Path("/proc")) -> bool:
    try:
        inode = _socket_inode(proc, peer_host, int(peer_port), int(local_port))
    except (ValueError, TypeError):
        return False
    if not inode or inode == "0":
        return False
    target = f"socket:[{inode}]"
    for pid_dir in _tailscaled_pids(proc):
        try:
            for fd in (pid_dir / "fd").iterdir():
                try:
                    if os.readlink(fd) == target:
                        return True
                except OSError:
                    continue
        except OSError:
            continue
    return False




def _forwarded_identity(raw: str) -> dict | None:
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    ip = tailnet_ip(payload.get("ip"))
    login, node = _clean(payload.get("login")), _clean(payload.get("node"))
    if not (ip or login or node):
        return None
    return {"role": TAILNET_ROLE, "source": "crm", "login": login, "node": node, "ip": ip}


def resolve_caller(
    *,
    peer_host: str | None,
    peer_port: int | None,
    local_port: int | None,
    headers: Mapping[str, str],
    serve_check=is_tailscale_serve_connection,
    whois_lookup=whois,
) -> dict | None:
    host = str(peer_host or "")
    if host not in LOOPBACK_HOSTS:
        return None
    try:
        via_serve = bool(peer_port and local_port and serve_check(host, int(peer_port), int(local_port)))
    except Exception:
        via_serve = False
    if via_serve:
        ip = tailnet_ip(headers.get(FORWARDED_FOR_HEADER))
        found = whois_lookup(ip) if ip else {}
        login = _clean(headers.get(SERVE_LOGIN_HEADER)) or found.get("login", "")
        caller = {"role": TAILNET_ROLE, "source": "serve", "login": login, "node": found.get("node", ""), "ip": ip}
        if found.get("tags"):
            caller["tags"] = found["tags"]
        return caller
    raw = headers.get(TAILNET_IDENTITY_HEADER)
    if raw:
        forwarded = _forwarded_identity(raw)
        if forwarded:
            return forwarded
    return {"role": MACHINE_ROLE, "source": "local"}
