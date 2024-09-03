"""
.. codeauthor:: Tsuyoshi Hombashi <tsuyoshi.hombashi@gmail.com>
"""

import abc

import subprocrunner
import typepy
from humanreadable import ParameterError

from .._common import run_command_helper
from .._const import TcSubCommand, TrafficDirection
from .._iptables import IptablesMangleMarkEntry
from .._logger import logger
from .._network import get_anywhere_network
from .._shaping_rule_finder import TcShapingRuleFinder


class ShaperInterface(metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def algorithm_name(self):  # pragma: no cover
        ...

    @abc.abstractmethod
    def set_shaping(self):  # pragma: no cover
        ...


class AbstractShaper(ShaperInterface):
    @property
    def _tc_device(self):
        return f"{self._tc_obj.get_tc_device():s}"

    @property
    def _dev(self):
        return f"dev {self._tc_device:s}"

    @property
    def _existing_parent(self):
        if self.__existing_parent:
            return self.__existing_parent

        self.__existing_parent = self._shaping_rule_finder.find_parent()

        return self.__existing_parent

    @property
    def _shaping_rule_finder(self):
        if self.__shaping_rule_finder:
            return self.__shaping_rule_finder

        self.__shaping_rule_finder = TcShapingRuleFinder(logger=logger, tc=self._tc_obj)

        return self.__shaping_rule_finder

    def __init__(self, tc_obj):
        self._tc_obj = tc_obj

        self.__shaping_rule_finder = None
        self.__existing_parent = None

    def _set_netem(self):
        base_command = self._tc_obj.get_tc_command(TcSubCommand.QDISC)
        parent = self._get_tc_parent(
            f"{self._tc_obj.qdisc_major_id_str:s}:{self._get_qdisc_minor_id():d}"
        )
        handle = self._get_tc_handle(
            f"{self._get_netem_qdisc_major_id(self._tc_obj.qdisc_major_id):x}:"
        )

        command_item_list = [
            base_command,
            f"dev {self._tc_obj.get_tc_device():s}",
            f"parent {parent:s}",
            f"handle {handle:s}",
            self._tc_obj.netem_param.make_netem_command_parts(),
        ]

        return run_command_helper(
            " ".join(command_item_list),
            ignore_error_msg_regexp=self._tc_obj.REGEXP_FILE_EXISTS,
            notice_msg=self._tc_obj.EXISTS_MSG_TEMPLATE.format(
                "failed to '{command:s}': netem qdisc already exists "
                "(dev={dev:s}, parent={parent:s}, handle={handle:s})".format(
                    command=base_command,
                    dev=self._tc_obj.get_tc_device(),
                    parent=parent,
                    handle=handle,
                )
            ),
        )

    def _get_filter_prio(self, is_exclude_filter: bool) -> int:
        offset = 4
        if is_exclude_filter:
            offset = 0

        if self._tc_obj.protocol == "ip":
            return 1 + offset

        if self._tc_obj.protocol == "ipv6":
            return 2 + offset

        return 3 + offset

    def _add_filter(self):
        if self._tc_obj.is_change_shaping_rule:
            return 0

        command_item_list = [
            self._tc_obj.get_tc_command(TcSubCommand.FILTER),
            self._dev,
            f"protocol {self._tc_obj.protocol:s}",
            f"parent {self._tc_obj.qdisc_major_id_str:s}:",
            f"prio {self._get_filter_prio(is_exclude_filter=False):d}",
        ]

        if self._is_use_iptables():
            command_item_list.append(f"handle {self._get_unique_mangle_mark_id():d} fw")
        else:
            if typepy.is_null_string(self._tc_obj.dst_network):
                dst_network = get_anywhere_network(self._tc_obj.ip_version)
            else:
                dst_network = self._tc_obj.dst_network

            command_item_list.extend(
                [
                    "u32",
                    "match {:s} {:s} {:s}".format(self._tc_obj.protocol_match, "dst", dst_network),
                ]
            )

            if typepy.is_not_null_string(self._tc_obj.src_network):
                command_item_list.append(
                    "match {:s} {:s} {:s}".format(
                        self._tc_obj.protocol_match, "src", self._tc_obj.src_network
                    )
                )

            if self._tc_obj.src_port:
                command_item_list.append(
                    "match {:s} sport {:d} 0xffff".format(
                        self._tc_obj.protocol_match, self._tc_obj.src_port
                    )
                )

            if self._tc_obj.dst_port:
                command_item_list.append(
                    "match {:s} dport {:d} 0xffff".format(
                        self._tc_obj.protocol_match, self._tc_obj.dst_port
                    )
                )

        command_item_list.append(
            f"flowid {self._tc_obj.qdisc_major_id_str:s}:{self._get_qdisc_minor_id():d}"
        )

        return subprocrunner.SubprocessRunner(" ".join(command_item_list)).run()

    def _add_exclude_filter(self):
        pass

    def _is_use_iptables(self):
        return all(
            [
                self._tc_obj.is_enable_iptables,
                self._tc_obj.direction == TrafficDirection.OUTGOING,
            ]
        )

    @abc.abstractmethod
    def _get_qdisc_minor_id(self):  # pragma: no cover
        ...

    @abc.abstractmethod
    def _get_netem_qdisc_major_id(self, base_id):  # pragma: no cover
        ...

    def _get_network_direction_str(self):
        if self._tc_obj.direction == TrafficDirection.OUTGOING:
            return "dst"

        if self._tc_obj.direction == TrafficDirection.INCOMING:
            return "src"

        raise ParameterError(
            "unknown direction",
            expected=TrafficDirection.LIST,
            value=self._tc_obj.direction,
        )

    def _get_tc_handle(self, default_handle):
        handle = None
        if self._tc_obj.is_change_shaping_rule:
            handle = self._shaping_rule_finder.find_qdisc_handle(self._get_tc_parent(None))

        if not handle:
            handle = default_handle

        return handle

    def _get_tc_parent(self, default_parent):
        parent = None
        if self._tc_obj.is_change_shaping_rule:
            parent = self._existing_parent

        if not parent:
            parent = default_parent

        return parent

    def _get_unique_mangle_mark_id(self):
        mark_id = self._tc_obj.iptables_ctrl.get_unique_mark_id()

        self.__add_mangle_mark(mark_id)

        return mark_id

    @abc.abstractmethod
    def _make_qdisc(self):  # pragma: no cover
        ...

    @abc.abstractmethod
    def _add_rate(self):  # pragma: no cover
        ...

    def __add_mangle_mark(self, mark_id):
        dst_network = None
        src_network = None

        if self._tc_obj.direction == TrafficDirection.OUTGOING:
            dst_network = self._tc_obj.dst_network
            if typepy.is_null_string(self._tc_obj.src_network):
                chain = "OUTPUT"
            else:
                src_network = self._tc_obj.src_network
                chain = "PREROUTING"
        elif self._tc_obj.direction == TrafficDirection.INCOMING:
            src_network = self._tc_obj.dst_network
            chain = "INPUT"

        self._tc_obj.iptables_ctrl.add(
            IptablesMangleMarkEntry(
                ip_version=self._tc_obj.ip_version,
                mark_id=mark_id,
                source=src_network,
                destination=dst_network,
                chain=chain,
            )
        )
