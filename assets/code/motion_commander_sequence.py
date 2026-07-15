#!/usr/bin/env python3
"""Finite MotionCommander sequence with Flow-deck and URI checks."""

import threading
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
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


def main():
    if not URI:
        raise RuntimeError("CFLIB_URI is empty; configure the group URI first.")
    cflib.crtp.init_drivers(enable_debug_driver=False)
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache="./cache")) as scf:
        scf.cf.param.add_update_callback(
            group="deck", name="bcFlow2", cb=flow_deck_callback
        )
        time.sleep(1.0)
        if not flow_deck_attached.wait(timeout=5.0):
            raise RuntimeError("Flow deck was not detected; takeoff cancelled.")

        armed = False
        try:
            request_arming(scf, True)
            armed = True
            time.sleep(1.0)
            with MotionCommander(scf, default_height=0.30) as commander:
                time.sleep(1.0)
                commander.forward(0.50, velocity=0.20)
                time.sleep(1.0)
                commander.up(0.20, velocity=0.15)
                time.sleep(1.0)
                commander.circle_right(0.50, velocity=0.20, angle_degrees=270)
                commander.down(0.20, velocity=0.15)
                time.sleep(1.0)
                commander.left(0.20, velocity=0.20)
                time.sleep(1.0)
                commander.forward(0.50, velocity=0.20)
        finally:
            if armed:
                request_arming(scf, False)


if __name__ == "__main__":
    main()
