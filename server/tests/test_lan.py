"""LAN addresses must be usable on another device; discovery sends no packets."""
from unittest.mock import MagicMock

import pytest

from deadzone import lan
from deadzone.__main__ import main


@pytest.mark.parametrize("address", ["127.0.0.1", "127.0.0.2", "169.254.1.2", "0.0.0.0", "::1", "224.0.0.1", "bad"])
def test_unusable_addresses(address):
    assert not lan.usable_ipv4(address)


def test_routed_interface_beats_hostname_adapters_without_sending(monkeypatch):
    probe = MagicMock()
    probe.__enter__.return_value = probe
    probe.getsockname.return_value = ("10.84.29.47", 50000)
    monkeypatch.setattr(lan.socket, "socket", lambda *args: probe)
    monkeypatch.setattr(lan.socket, "gethostbyname_ex", lambda *args: pytest.fail("route already found"))
    assert lan.lan_ipv4("192.168.1.2") == "10.84.29.47"
    probe.connect.assert_called_once_with(("192.168.1.2", 80))
    probe.send.assert_not_called()
    probe.sendto.assert_not_called()


@pytest.mark.parametrize("addresses,expected", [(["127.0.0.1", "169.254.1.2", "192.168.1.9"], "192.168.1.9"), (["127.0.0.1"], None)])
def test_no_route_falls_back_only_to_usable_addresses(monkeypatch, addresses, expected):
    def unavailable(*args):
        raise OSError()
    monkeypatch.setattr(lan.socket, "socket", unavailable)
    monkeypatch.setattr(lan.socket, "gethostbyname_ex", lambda *args: ("laptop", [], addresses))
    assert lan.lan_ipv4() == expected


def test_default_launcher_binds_lan_and_supports_overrides(monkeypatch):
    import uvicorn
    run = MagicMock()
    monkeypatch.setattr(uvicorn, "run", run)
    main([])
    run.assert_called_once_with("deadzone.app:app", host="0.0.0.0", port=8000, reload=False)
    main(["--host", "127.0.0.1", "--port", "8012", "--reload"])
    assert run.call_args.kwargs == {"host": "127.0.0.1", "port": 8012, "reload": True}
