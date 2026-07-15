#!/usr/bin/env python3
"""Fly a finite 1 m square with PositionHlCommander."""

import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.positioning.position_hl_commander import PositionHlCommander
from cflib.utils import uri_helper


URI = uri_helper.uri_from_env(default="")


def request_arming(scf, armed):
    for service_name in ("platform", "supervisor"):
        service = getattr(scf.cf, service_name, None)
        request = getattr(service, "send_arming_request", None)
        if request is not None:
            request(armed)
            return
    raise RuntimeError("This cflib version has no arming service.")


def main():
    if not URI:
        raise RuntimeError("CFLIB_URI is empty; configure the group URI first.")
    cflib.crtp.init_drivers()
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache="./cache")) as scf:
        armed = False
        try:
            request_arming(scf, True)
            armed = True
            time.sleep(1.0)
            with PositionHlCommander(
                scf,
                x=0.0,
                y=0.0,
                z=0.0,
                default_velocity=0.20,
                default_height=0.35,
                controller=PositionHlCommander.CONTROLLER_PID,
            ) as commander:
                commander.go_to(1.0, 0.0, 0.35)
                commander.go_to(1.0, 1.0, 0.35)
                commander.go_to(0.0, 1.0, 0.35)
                commander.go_to(0.0, 0.0, 0.35)
        finally:
            if armed:
                request_arming(scf, False)


if __name__ == "__main__":
    main()
