#!/usr/bin/env python3
"""Finite MotionCommander route with 10 Hz position logging."""

import threading
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.positioning.motion_commander import MotionCommander
from cflib.utils import uri_helper


URI = uri_helper.uri_from_env(default="")
flow_deck_attached = threading.Event()


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
    print(
        "x=%.3f y=%.3f"
        % (float(data["stateEstimate.x"]), float(data["stateEstimate.y"]))
    )


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
            request_arming(scf, True)
            armed = True
            time.sleep(1.0)
            with MotionCommander(scf, default_height=0.35) as commander:
                time.sleep(1.0)
                commander.forward(0.50, velocity=0.20)
                time.sleep(1.0)
                commander.turn_left(180)
                time.sleep(1.0)
                commander.forward(0.50, velocity=0.20)
                time.sleep(1.0)
        finally:
            if log_started:
                position_log.stop()
            if armed:
                request_arming(scf, False)


if __name__ == "__main__":
    main()
