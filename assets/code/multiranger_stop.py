#!/usr/bin/env python3
"""Fly forward slowly and land before the front obstacle."""

import threading
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.positioning.motion_commander import MotionCommander
from cflib.utils import uri_helper
from cflib.utils.multiranger import Multiranger


URI = uri_helper.uri_from_env(default="")
FRONT_STOP_DISTANCE_M = 0.28
UP_STOP_DISTANCE_M = 0.15
FORWARD_SPEED_MPS = 0.10
MAX_FLIGHT_TIME_S = 20.0


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
                        front = multiranger.front
                        up = multiranger.up
                        should_stop = (
                            up is not None and up < UP_STOP_DISTANCE_M
                        ) or (
                            front is not None and front < FRONT_STOP_DISTANCE_M
                        )
                        if should_stop:
                            commander.stop()
                            break
                        commander.start_forward(FORWARD_SPEED_MPS)
                        time.sleep(0.1)
                    commander.stop()
        finally:
            if armed:
                request_arming(scf, False)


if __name__ == "__main__":
    main()
