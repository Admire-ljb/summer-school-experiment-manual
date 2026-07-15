#!/usr/bin/env python3
"""Bounded Flow-deck position exercise with stale-log and time limits."""

import threading
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.positioning.motion_commander import MotionCommander
from cflib.utils import uri_helper


URI = uri_helper.uri_from_env(default="")
DEFAULT_HEIGHT_M = 0.35
BOX_LIMIT_M = 0.35
MAX_VELOCITY_MPS = 0.15
MAX_FLIGHT_TIME_S = 45.0
LOG_STALE_TIMEOUT_S = 0.60

flow_deck_attached = threading.Event()
position_lock = threading.Lock()
position_estimate = [0.0, 0.0]
last_position_update = 0.0


def request_arming(scf, armed):
    for service_name in ("platform", "supervisor"):
        service = getattr(scf.cf, service_name, None)
        request = getattr(service, "send_arming_request", None)
        if request is not None:
            request(armed)
            return
    raise RuntimeError("This cflib version has no arming service.")


def flow_deck_callback(name, value):
    if int(value):
        flow_deck_attached.set()


def position_callback(timestamp, data, log_config):
    global last_position_update
    with position_lock:
        position_estimate[0] = float(data["stateEstimate.x"])
        position_estimate[1] = float(data["stateEstimate.y"])
        last_position_update = time.monotonic()


def move_box_limit(scf):
    body_x = MAX_VELOCITY_MPS
    body_y = MAX_VELOCITY_MPS * 0.5
    deadline = time.monotonic() + MAX_FLIGHT_TIME_S

    with MotionCommander(scf, default_height=DEFAULT_HEIGHT_M) as commander:
        while time.monotonic() < deadline:
            with position_lock:
                x, y = position_estimate
                update_age = time.monotonic() - last_position_update
            if update_age > LOG_STALE_TIMEOUT_S:
                commander.stop()
                raise RuntimeError("Position log is stale; landing.")
            if x >= BOX_LIMIT_M:
                body_x = -MAX_VELOCITY_MPS
            elif x <= -BOX_LIMIT_M:
                body_x = MAX_VELOCITY_MPS
            if y >= BOX_LIMIT_M:
                body_y = -MAX_VELOCITY_MPS
            elif y <= -BOX_LIMIT_M:
                body_y = MAX_VELOCITY_MPS
            commander.start_linear_motion(body_x, body_y, 0.0)
            time.sleep(0.1)
        commander.stop()


def main():
    if not URI:
        raise RuntimeError("CFLIB_URI is empty; configure the group URI first.")
    cflib.crtp.init_drivers()
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache="./cache")) as scf:
        scf.cf.param.add_update_callback(
            group="deck", name="bcFlow2", cb=flow_deck_callback
        )
        time.sleep(1.0)
        if not flow_deck_attached.wait(timeout=5.0):
            raise RuntimeError("Flow deck was not detected; takeoff cancelled.")

        position_log = LogConfig(name="Position", period_in_ms=100)
        position_log.add_variable("stateEstimate.x", "float")
        position_log.add_variable("stateEstimate.y", "float")
        scf.cf.log.add_config(position_log)
        position_log.data_received_cb.add_callback(position_callback)
        log_started = False
        armed = False
        try:
            position_log.start()
            log_started = True
            if not wait_for_first_position(timeout=2.0):
                raise RuntimeError("No position log data; takeoff cancelled.")
            request_arming(scf, True)
            armed = True
            time.sleep(1.0)
            move_box_limit(scf)
        finally:
            if log_started:
                position_log.stop()
            if armed:
                request_arming(scf, False)


def wait_for_first_position(timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with position_lock:
            if last_position_update > 0.0:
                return True
        time.sleep(0.05)
    return False


if __name__ == "__main__":
    main()
