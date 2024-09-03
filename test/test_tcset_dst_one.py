"""
.. codeauthor:: Tsuyoshi Hombashi <tsuyoshi.hombashi@gmail.com>
"""

import itertools

import pingparsing
import pytest
import typepy

from tcconfig._const import Tc
from tcconfig._netem_param import convert_rate_to_f
from tcconfig.traffic_control import delete_all_rules

from .common import ASSERT_MARGIN, DEADLINE_TIME, runner_helper


@pytest.fixture
def device_option(request):
    return request.config.getoption("--device")


@pytest.fixture
def dst_host_option(request):
    return request.config.getoption("--dst-host")


@pytest.fixture
def transmitter():
    transmitter = pingparsing.PingTransmitter()
    transmitter.ping_option = "-i 0.2 -q"
    transmitter.deadline = DEADLINE_TIME

    return transmitter


@pytest.fixture
def pingparser():
    return pingparsing.PingParsing()


class Test_tcset_one_network:
    """
    Tests in this class are not executable on CI services.
    Execute the following command at the local environment to running tests:

        pytest --device=<test device> --dst-host=<IP address>

    These tests expected to execute in the following environment:
       - Linux w/ iputils-ping package
       - English locale (for parsing ping output)
    """

    @pytest.mark.parametrize(
        ["shaping_algo", "delay"],
        [[params[0], params[1]] for params in itertools.product(["htb"], [100])],
    )
    def test_dst_net_uniform_latency(
        self,
        device_option,
        dst_host_option,
        transmitter,
        pingparser,
        shaping_algo,
        delay,
    ):
        if device_option is None:
            pytest.skip("device option is null")
        if typepy.is_null_string(dst_host_option):
            pytest.skip("destination host is null")

        for tc_target in [device_option]:
            delete_all_rules(tc_target)
            transmitter.destination = dst_host_option

            # w/o latency tc ---
            ping_result = transmitter.ping()
            assert ping_result.returncode == 0
            without_tc_rtt_avg = pingparser.parse(ping_result).rtt_avg

            # w/ latency tc ---
            runner_helper(
                " ".join(
                    [
                        Tc.Command.TCSET,
                        tc_target,
                        f"--delay {delay}ms",
                        f"--shaping-algo {shaping_algo:s}",
                    ]
                )
            )

            ping_result = transmitter.ping()
            assert ping_result.returncode == 0
            with_tc_rtt_avg = pingparser.parse(ping_result).rtt_avg

            # assertion ---
            rtt_diff = with_tc_rtt_avg - without_tc_rtt_avg
            assert rtt_diff > (delay * ASSERT_MARGIN)

            # finalize ---
            delete_all_rules(device_option)

    @pytest.mark.parametrize(["delay", "delay_distro"], [[100, 50]])
    def test_dst_net_latency_distro(
        self,
        device_option,
        dst_host_option,
        transmitter,
        pingparser,
        delay,
        delay_distro,
    ):
        if typepy.is_null_string(dst_host_option):
            pytest.skip("destination host is null")

        for tc_target in [device_option]:
            delete_all_rules(tc_target)
            transmitter.destination = dst_host_option

            # w/o latency tc ---
            ping_result = transmitter.ping()
            assert ping_result.returncode == 0
            ping_stats = pingparser.parse(ping_result)
            without_tc_rtt_avg = ping_stats.rtt_avg
            without_tc_rtt_mdev = ping_stats.rtt_mdev

            # w/ latency tc ---
            runner_helper(
                " ".join(
                    [
                        Tc.Command.TCSET,
                        tc_target,
                        "--delay",
                        f"{delay:d}ms",
                        "--delay-distro",
                        f"{delay_distro:d}ms",
                    ]
                )
            )

            ping_result = transmitter.ping()
            assert ping_result.returncode == 0
            ping_stats = pingparser.parse(ping_result)
            with_tc_rtt_avg = ping_stats.rtt_avg
            with_tc_rtt_mdev = ping_stats.rtt_mdev

            # assertion ---
            rtt_diff = with_tc_rtt_avg - without_tc_rtt_avg
            assert rtt_diff > (delay * ASSERT_MARGIN)

            rtt_diff = with_tc_rtt_mdev - without_tc_rtt_mdev
            assert rtt_diff > (delay_distro * ASSERT_MARGIN)

            # finalize ---
            delete_all_rules(tc_target)

    @pytest.mark.parametrize(["delay_distribution"], [["normal"], ["pareto"], ["paretonormal"]])
    def test_latency_distribution(
        self, device_option, dst_host_option, transmitter, delay_distribution
    ):
        if typepy.is_null_string(dst_host_option):
            pytest.skip("destination host is null")

        for tc_target in [device_option]:
            delete_all_rules(tc_target)
            transmitter.destination = dst_host_option

            # w/ latency tc ---
            runner_helper(
                " ".join(
                    [
                        Tc.Command.TCSET,
                        tc_target,
                        "--delay",
                        "2ms",
                        "--delay-distro",
                        "5ms",
                        "--delay-distribution",
                        delay_distribution,
                    ]
                )
            )

            # finalize ---
            delete_all_rules(tc_target)

    @pytest.mark.parametrize(["option", "value"], [["--loss", 10], ["--corrupt", 10]])
    def test_dst_net_packet_loss(
        self, device_option, dst_host_option, transmitter, pingparser, option, value
    ):
        if typepy.is_null_string(dst_host_option):
            pytest.skip("destination host is null")

        for tc_target in [device_option]:
            delete_all_rules(tc_target)
            transmitter.destination = dst_host_option

            # w/o traffic shaping ---
            ping_result = transmitter.ping()
            assert ping_result.returncode == 0
            without_tc_loss_rate = pingparser.parse(ping_result).packet_loss_rate

            # w/ traffic shaping ---
            runner_helper(" ".join([Tc.Command.TCSET, tc_target, f"{option:s} {value:f}"]))

            ping_result = transmitter.ping()
            assert ping_result.returncode == 0
            with_tc_loss_rate = pingparser.parse(ping_result).packet_loss_rate

            # check packet loss rate ---
            loss_diff = with_tc_loss_rate - without_tc_loss_rate
            assert loss_diff > (value * ASSERT_MARGIN)

            # finalize ---
            delete_all_rules(tc_target)

    @pytest.mark.parametrize(["option", "value"], [["--duplicate", 50], ["--duplicate", "10%"]])
    def test_dst_net_packet_duplicate(
        self, device_option, dst_host_option, transmitter, pingparser, option, value
    ):
        if typepy.is_null_string(dst_host_option):
            pytest.skip("destination host is null")

        for tc_target in [device_option]:
            delete_all_rules(tc_target)
            transmitter.destination = dst_host_option

            # w/o packet duplicate tc ---
            ping_result = transmitter.ping()
            assert ping_result.returncode == 0
            without_tc_duplicate_rate = pingparser.parse(ping_result).packet_duplicate_rate

            # w/ packet duplicate tc ---
            runner_helper(" ".join([Tc.Command.TCSET, tc_target, f"{option:s} {value}"]))

            ping_result = transmitter.ping()
            assert ping_result.returncode == 0
            with_tc_duplicate_rate = pingparser.parse(ping_result).packet_duplicate_rate

            # assertion ---
            duplicate_rate_diff = with_tc_duplicate_rate - without_tc_duplicate_rate
            assert duplicate_rate_diff > (convert_rate_to_f(value) * ASSERT_MARGIN)

            # finalize ---
            delete_all_rules(tc_target)

    def test_dst_net_exclude_dst_network(
        self, device_option, dst_host_option, transmitter, pingparser
    ):
        if device_option is None:
            pytest.skip("device option is null")
        if typepy.is_null_string(dst_host_option):
            pytest.skip("destination host is null")

        delay = 100

        for tc_target in [device_option]:
            delete_all_rules(tc_target)
            transmitter.destination = dst_host_option

            # w/ latency tc ---
            runner_helper([Tc.Command.TCSET, tc_target, "--delay", f"{delay:d}ms"])

            ping_result = transmitter.ping()
            assert ping_result.returncode == 0
            with_tc_rtt_avg = pingparser.parse(ping_result).rtt_avg

            # exclude certain network ---
            runner_helper(
                " ".join(
                    [
                        Tc.Command.TCSET,
                        tc_target,
                        "--exclude-dst-network {:s}/24".format(
                            ".".join(dst_host_option.split(".")[:3] + ["0"])
                        ),
                        f"--delay {delay:d}ms",
                        "--overwrite",
                    ]
                )
            )
            without_tc_rtt_avg = pingparser.parse(transmitter.ping()).rtt_avg

            # assertion ---
            rtt_diff = with_tc_rtt_avg - without_tc_rtt_avg
            assert rtt_diff > (delay * ASSERT_MARGIN)

            # finalize ---
            delete_all_rules(tc_target)
