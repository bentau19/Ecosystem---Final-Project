"""Unit tests for utils.network — get_ip."""

from unittest.mock import patch, MagicMock

from utils.network import get_ip


# ---------------------------------------------------------------------------
# get_ip
# ---------------------------------------------------------------------------


def test_get_ip_returns_string() -> None:
    with patch("utils.network.socket") as mock_socket:
        mock_socket.gethostname.return_value = "my-host"
        mock_socket.gethostbyname.return_value = "192.168.1.100"

        result = get_ip()

    assert isinstance(result, str)


def test_get_ip_returns_resolved_address() -> None:
    with patch("utils.network.socket") as mock_socket:
        mock_socket.gethostname.return_value = "my-host"
        mock_socket.gethostbyname.return_value = "10.0.0.1"

        result = get_ip()

    assert result == "10.0.0.1"


def test_get_ip_calls_gethostname() -> None:
    with patch("utils.network.socket") as mock_socket:
        mock_socket.gethostname.return_value = "my-host"
        mock_socket.gethostbyname.return_value = "192.168.1.100"

        get_ip()

    mock_socket.gethostname.assert_called_once()


def test_get_ip_passes_hostname_to_gethostbyname() -> None:
    with patch("utils.network.socket") as mock_socket:
        mock_socket.gethostname.return_value = "desktop-abc"
        mock_socket.gethostbyname.return_value = "172.16.0.5"

        get_ip()

    mock_socket.gethostbyname.assert_called_once_with("desktop-abc")


def test_get_ip_propagates_different_hostnames() -> None:
    for hostname, ip in [("host-a", "1.2.3.4"), ("host-b", "5.6.7.8")]:
        with patch("utils.network.socket") as mock_socket:
            mock_socket.gethostname.return_value = hostname
            mock_socket.gethostbyname.return_value = ip

            result = get_ip()

        assert result == ip
