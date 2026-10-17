import pytest

from dryline.cli import main


def test_cli_requires_a_command():
    with pytest.raises(SystemExit):
        main([])


def test_network_is_blocked_in_tests():
    import socket

    from pytest_socket import SocketBlockedError

    with pytest.raises(SocketBlockedError):
        socket.create_connection(("example.com", 80), timeout=1)
