"""
.. codeauthor:: Tsuyoshi Hombashi <tsuyoshi.hombashi@gmail.com>
"""

import datetime
import os
import sys

import typepy

from ._const import Tc
from ._logger import logger


def write_tc_script(tcconfig_command, command_history, filename_suffix=None):
    filename_item_list = [tcconfig_command]
    if typepy.is_not_null_string(filename_suffix):
        filename_item_list.append(filename_suffix)

    script_line_list = ["#!/bin/sh", ""]

    org_tcconfig_cmd = _get_original_tcconfig_command(tcconfig_command)

    if tcconfig_command != Tc.Command.TCSHOW:
        script_line_list.extend(
            [
                "# command sequence in this script attempt to simulate the following "
                "tcconfig command:",
                "#",
                f"#   {org_tcconfig_cmd:s}",
            ]
        )

    script_line_list.extend(
        [
            "#",
            f"# the script execution result may different from '{org_tcconfig_cmd}'",
            "#",
            "# created by {:s} on {:s}.".format(
                tcconfig_command,
                datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"),
            ),
            "",
            command_history,
        ]
    )

    filename = "_".join(filename_item_list) + ".sh"
    with open(filename, "w", encoding="utf8") as fp:
        fp.write("\n".join(script_line_list) + "\n")

    os.chmod(filename, 0o755)
    logger.info(f"written a tc script to '{filename:s}'")


def _get_original_tcconfig_command(tcconfig_command):
    return " ".join(
        [tcconfig_command]
        + [command_item for command_item in sys.argv[1:] if command_item != "--tc-script"]
    )
