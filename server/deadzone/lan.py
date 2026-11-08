"""Find a usable laptop IPv4 address without sending traffic to a third party."""
import ipaddress
import socket


def usable_ipv4(value):
    try:
        address = ipaddress.ip_address(value)
        return address.version == 4 and not (address.is_loopback or address.is_link_local
            or address.is_unspecified or address.is_multicast or address.is_reserved)
    except ValueError:
        return False


def lan_ipv4(peer=None):
    # UDP connect asks the OS which local interface routes to the peer/default
    # gateway. No send/sendto occurs, so no datagram leaves the machine.
    target = peer if peer and usable_ipv4(peer) else "8.8.8.8"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect((target, 80))
            address = probe.getsockname()[0]
            if usable_ipv4(address):
                return address
    except OSError:
        pass
    try:
        candidates = socket.gethostbyname_ex(socket.gethostname())[2]
        return next((address for address in sorted(candidates) if usable_ipv4(address)), None)
    except OSError:
        return None
