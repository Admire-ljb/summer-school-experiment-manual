#!/usr/bin/env python3
"""Low-speed reactive Multi-ranger demonstration with a flight-time limit."""

import math
import threading
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.positioning.motion_commander import MotionCommander
from cflib.utils import uri_helper
from cflib.utils.multiranger import Multiranger


URI = uri_helper.uri_from_env(default="")
MIN_DISTANCE_M = 0.18
VELOCITY_MPS = 0.20
MAX_FLIGHT_TIME_S = 60.0


def is_close(value):
    return value is not None and math.isfinite(value) and value < MIN_DISTANCE_M


def request_arming(scf, armed):
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
            group="deck", name=deck_name, cb=callback
        )
    time.sleep(1.0)
    return all(event.wait(timeout=4.0) for event in attached.values())


def main():
    if not URI:
        raise RuntimeError("CFLIB_URI is empty; configure the group URI first.")
    cflib.crtp.init_drivers()
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache="./cache")) as scf:
        if not wait_for_decks(scf):
            raise RuntimeError(
                "Flow deck or Multi-ranger deck was not detected; takeoff cancelled."
            )
        armed = False
        try:
            request_arming(scf, True)
            armed = True
            time.sleep(1.0)
            with MotionCommander(scf, default_height=0.35) as commander:
                with Multiranger(scf) as multiranger:
                    deadline = time.monotonic() + MAX_FLIGHT_TIME_S
                    while time.monotonic() < deadline:
                        if is_close(multiranger.up):
                            commander.stop()
                            break
                        velocity_x = 0.0
                        velocity_y = 0.0
                        if is_close(multiranger.front):
                            velocity_x -= VELOCITY_MPS
                        if is_close(multiranger.back):
                            velocity_x += VELOCITY_MPS
                        if is_close(multiranger.left):
                            velocity_y -= VELOCITY_MPS
                        if is_close(multiranger.right):
                            velocity_y += VELOCITY_MPS
                        commander.start_linear_motion(velocity_x, velocity_y, 0.0)
                        time.sleep(0.1)
                    commander.stop()
        finally:
            if armed:
                request_arming(scf, False)


if __name__ == "__main__":
    main()
