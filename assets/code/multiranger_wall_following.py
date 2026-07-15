#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run gap-resistant Multi-ranger wall following in a narrow classroom arena."""

import argparse
import logging
import math
import threading
import time

from wall_following import GapResistantRangeFilter
from wall_following import WallFollowing

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.positioning.motion_commander import MotionCommander
from cflib.utils import uri_helper
from cflib.utils.multiranger import Multiranger


logging.basicConfig(level=logging.ERROR)

# Immediate landing thresholds. Normal steering uses the filtered values below.
FRONT_EMERGENCY_DISTANCE_M = 0.14
SIDE_EMERGENCY_DISTANCE_M = 0.09
UP_STOP_DISTANCE_M = 0.15
DEFAULT_MAX_FLIGHT_TIME_S = 90.0
STATUS_PERIOD_S = 0.50
LOG_STALE_TIMEOUT_S = 0.60


def parse_args():
    parser = argparse.ArgumentParser(
        description="Follow the selected wall using Flow and Multi-ranger decks."
    )
    parser.add_argument(
        "--wall-side",
        choices=("left", "right"),
        default="left",
        help="side on which the wall is kept (default: left)",
    )
    parser.add_argument(
        "--max-time",
        type=float,
        default=DEFAULT_MAX_FLIGHT_TIME_S,
        help="maximum flight time in seconds (default: 90)",
    )
    return parser.parse_args()


def require_group_uri():
    uri = uri_helper.uri_from_env(default="")
    if not uri:
        raise RuntimeError(
            "CFLIB_URI is empty. Complete Experiment 3 and open a new terminal."
        )
    return uri


def request_arming(scf, armed):
    """Support both newer ``platform`` and older ``supervisor`` services."""
    for service_name in ("platform", "supervisor"):
        service = getattr(scf.cf, service_name, None)
        request = getattr(service, "send_arming_request", None)
        if request is not None:
            request(armed)
            return
    raise RuntimeError("This cflib version has no arming service.")


def wait_for_decks(scf):
    attached = {
        "bcFlow2": threading.Event(),
        "bcMultiranger": threading.Event(),
    }

    def callback(name, value):
        deck_name = name.rsplit(".", 1)[-1]
        if deck_name in attached and int(value):
            attached[deck_name].set()

    for deck_name in attached:
        scf.cf.param.add_update_callback(
            group="deck",
            name=deck_name,
            cb=callback,
        )
    time.sleep(1.0)
    return all(event.wait(timeout=4.0) for event in attached.values())


def valid_range(value):
    if value is None:
        return None
    try:
        distance = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(distance) or distance <= 0.03:
        return None
    return distance


def emergency_reason(multiranger):
    front = valid_range(multiranger.front)
    left = valid_range(multiranger.left)
    right = valid_range(multiranger.right)
    up = valid_range(multiranger.up)
    if up is not None and up < UP_STOP_DISTANCE_M:
        return "upper sensor stop gesture"
    if front is not None and front < FRONT_EMERGENCY_DISTANCE_M:
        return "front clearance below %.2f m" % FRONT_EMERGENCY_DISTANCE_M
    if left is not None and left < SIDE_EMERGENCY_DISTANCE_M:
        return "left clearance below %.2f m" % SIDE_EMERGENCY_DISTANCE_M
    if right is not None and right < SIDE_EMERGENCY_DISTANCE_M:
        return "right clearance below %.2f m" % SIDE_EMERGENCY_DISTANCE_M
    return None


def run_wall_following(scf, wall_side_name, max_time):
    if max_time <= 0.0:
        raise ValueError("--max-time must be greater than zero")

    wall_side = (
        WallFollowing.WallSide.LEFT
        if wall_side_name == "left"
        else WallFollowing.WallSide.RIGHT
    )
    controller = WallFollowing(wall_side=wall_side)

    # A short front hold rejects one-frame dropouts. The longer side hold is
    # what prevents panel seams from being treated as real outer corners.
    front_filter = GapResistantRangeFilter(
        window_size=3,
        minimum_samples=2,
        gap_threshold=0.80,
        gap_confirm_seconds=0.25,
    )
    side_filter = GapResistantRangeFilter(
        window_size=5,
        minimum_samples=3,
        gap_threshold=controller.side_lost_distance,
        gap_confirm_seconds=0.80,
    )

    yaw_log = LogConfig(name="WallFollowingYaw", period_in_ms=100)
    yaw_log.add_variable("stabilizer.yaw", "float")
    yaw_lock = threading.Lock()
    yaw_ready = threading.Event()
    yaw_sample = [0.0, 0.0]

    def yaw_callback(timestamp, data, log_config):
        with yaw_lock:
            yaw_sample[0] = math.radians(float(data["stabilizer.yaw"]))
            yaw_sample[1] = time.monotonic()
        yaw_ready.set()

    yaw_log.data_received_cb.add_callback(yaw_callback)
    scf.cf.log.add_config(yaw_log)
    yaw_log.start()

    try:
        if not yaw_ready.wait(timeout=2.0):
            raise RuntimeError("No yaw log data; takeoff cancelled.")
        with Multiranger(scf) as multiranger:
            armed = False
            try:
                request_arming(scf, True)
                armed = True
                time.sleep(1.0)
                started = time.monotonic()
                last_status = 0.0
                with MotionCommander(scf, default_height=0.35) as commander:
                    time.sleep(1.0)
                    while time.monotonic() - started < max_time:
                        reason = emergency_reason(multiranger)
                        if reason is not None:
                            commander.stop()
                            print("Stopping: %s." % reason)
                            break

                        now = time.monotonic()
                        with yaw_lock:
                            yaw_rad, yaw_time = yaw_sample
                        if now - yaw_time > LOG_STALE_TIMEOUT_S:
                            commander.stop()
                            print("Yaw log is stale; landing.")
                            break
                        raw_front = valid_range(multiranger.front)
                        raw_side = valid_range(
                            multiranger.left
                            if wall_side is WallFollowing.WallSide.LEFT
                            else multiranger.right
                        )
                        front = front_filter.update(raw_front, now=now)
                        side = side_filter.update(raw_side, now=now)

                        velocity_x, velocity_y, yaw_rate, state = controller.update(
                            front,
                            side,
                            yaw_rad,
                            now=now,
                        )
                        if state is WallFollowing.State.HOVER:
                            commander.stop()
                            print("Controller could not reacquire the wall; landing.")
                            break

                        commander.start_linear_motion(
                            velocity_x,
                            velocity_y,
                            0.0,
                            rate_yaw=math.degrees(yaw_rate),
                        )
                        if now - last_status >= STATUS_PERIOD_S:
                            print(
                                "state=%s front=%.2f side=%.2f vx=%.2f vy=%.2f"
                                % (state.name, front, side, velocity_x, velocity_y)
                            )
                            last_status = now
                        time.sleep(0.1)
                    else:
                        commander.stop()
                        print("Maximum flight time reached; landing.")
            finally:
                if armed:
                    request_arming(scf, False)
    finally:
        yaw_log.stop()


def main():
    args = parse_args()
    uri = require_group_uri()
    print("Using URI: %s" % uri)
    print("Following the %s wall." % args.wall_side)

    cflib.crtp.init_drivers()
    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache="./cache")) as scf:
        if not wait_for_decks(scf):
            raise RuntimeError(
                "Flow deck or Multi-ranger deck was not detected; takeoff cancelled."
            )
        try:
            run_wall_following(scf, args.wall_side, args.max_time)
        except KeyboardInterrupt:
            print("Ctrl-C received; landing.")


if __name__ == "__main__":
    main()
