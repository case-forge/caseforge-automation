from __future__ import annotations

import socket
import threading
import urllib.error
import urllib.request

import pytest


def test_a_real_hostname_is_refused():
    with pytest.raises(socket.gaierror, match="gh#305"):
        socket.getaddrinfo("graph.microsoft.com", 443)


def test_the_refusal_reaches_urllib_the_way_a_dns_failure_would():
    with pytest.raises(urllib.error.URLError) as info:
        urllib.request.urlopen("http://caseforge:8000/ping/key/x", timeout=1)
    assert isinstance(info.value.reason, socket.gaierror)
    assert "gh#305" in str(info.value.reason)


def test_a_background_thread_is_refused_too():
    caught: list[BaseException] = []

    def lookup() -> None:
        try:
            socket.getaddrinfo("sign.example.net", 443)
        except BaseException as exc:
            caught.append(exc)

    thread = threading.Thread(target=lookup)
    thread.start()
    thread.join(timeout=5)
    assert len(caught) == 1 and isinstance(caught[0], socket.gaierror)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", None])
def test_loopback_and_literals_still_resolve(host):
    assert socket.getaddrinfo(host, 80, type=socket.SOCK_STREAM)
