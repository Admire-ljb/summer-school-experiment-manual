#!/usr/bin/env python3
"""Print Multi-ranger readings for 30 seconds without arming the aircraft."""

import threading
import time

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.utils import uri_helper
from cflib.utils.multiranger import Multiranger


URI = uri_helper.uri_from_env(default="")
READ_TIME_S = 30.0


def wait_for_multiranger(scf):
    attached = threading.Event()

    def callback(name, value):
        if int(value):
            attached.set()

    scf.cf.param.add_update_callback(
        group="deck", name="bcMultiranger", cb=callback
    )
    time.sleep(1.0)
    return attached.wait(timeout=4.0)


def main():
    if not URI:
        raise RuntimeError("CFLIB_URI is empty; configure the group URI first.")
    cflib.crtp.init_drivers()
    with SyncCrazyflie(URI, cf=Crazyflie(rw_cache="./cache")) as scf:
        if not wait_for_multiranger(scf):
            raise RuntimeError("Multi-ranger deck was not detected.")
        with Multiranger(scf) as multiranger:
            deadline = time.monotonic() + READ_TIME_S
            try:
                while time.monotonic() < deadline:
                    print(
                        "front=%s back=%s left=%s right=%s up=%s down=%s"
                        % (
                            multiranger.front,
                            multiranger.back,
                            multiranger.left,
                            multiranger.right,
                            multiranger.up,
                            multiranger.down,
                        )
                    )
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print("Reading stopped by the operator.")


if __name__ == "__main__":
    main()
