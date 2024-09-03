"""
.. codeauthor:: Tsuyoshi Hombashi <tsuyoshi.hombashi@gmail.com>
"""

import humanreadable as hr
import typepy
from pyroute2 import IPRoute

from ._const import Network
from ._error import NetworkInterfaceNotFoundError


def get_anywhere_network(ip_version):
    ip_version_n = typepy.Integer(ip_version).try_convert()

    if ip_version_n == 4:
        return Network.Ipv4.ANYWHERE

    if ip_version_n == 6:
        return Network.Ipv6.ANYWHERE

    raise ValueError(f"unknown ip version: {ip_version}")


def _get_iproute2_upper_limite_rate():
    """
    :return: Upper bandwidth rate limit of iproute2 [Kbps].
    :rtype: int
    """

    # upper bandwidth rate limit of iproute2 was 34,359,738,360
    # bits per second older than 3.14.0
    # http://git.kernel.org/cgit/linux/kernel/git/shemminger/iproute2.git/commit/?id=8334bb325d5178483a3063c5f06858b46d993dc7

    return hr.BitsPerSecond("32Gbps")


def _read_iface_speed(tc_device):
    with open(f"/sys/class/net/{tc_device:s}/speed") as f:
        return int(f.read().strip())


def get_upper_limit_rate(tc_device):
    if typepy.is_null_string(tc_device):
        return _get_iproute2_upper_limite_rate()

    try:
        speed_value = _read_iface_speed(tc_device)
    except OSError:
        return _get_iproute2_upper_limite_rate()

    if speed_value < 0:
        # default to the iproute2 upper limit when the speed value is -1 in
        # paravirtualized network interfaces
        return _get_iproute2_upper_limite_rate()

    return min(
        hr.BitsPerSecond(f"{speed_value}Mbps"),
        _get_iproute2_upper_limite_rate(),
    )


def is_anywhere_network(network, ip_version):
    try:
        network = network.strip()
    except AttributeError as e:
        raise ValueError(e)

    if ip_version == 4:
        return network == get_anywhere_network(ip_version)

    if ip_version == 6:
        return network in (get_anywhere_network(ip_version), "0:0:0:0:0:0:0:0/0")

    raise ValueError(f"invalid ip version: {ip_version}")


def sanitize_network(network, ip_version):
    """
    :return: Network string
    :rtype: str
    :raises ValueError: if the network string is invalid.
    """

    import ipaddress

    if typepy.is_null_string(network) or network.casefold() == "anywhere":
        return get_anywhere_network(ip_version)

    try:
        if ip_version == 4:
            ipaddress.IPv4Address(network)
            return network + "/32"

        if ip_version == 6:
            return ipaddress.IPv6Address(network).compressed
    except ipaddress.AddressValueError:
        pass

    # validate network str ---

    if ip_version == 4:
        return ipaddress.IPv4Network(str(network)).compressed

    if ip_version == 6:
        return ipaddress.IPv6Network(str(network)).compressed

    raise ValueError(f"unexpected ip version: {ip_version}")


def verify_network_interface(device, tc_command_output):
    from ._common import is_execute_tc_command

    if not is_execute_tc_command(tc_command_output):
        return

    with IPRoute() as ipr:
        avail_interfaces = [link.get_attr("IFLA_IFNAME") for link in ipr.get_links()]

    if device not in avail_interfaces:
        raise NetworkInterfaceNotFoundError(target=device)
