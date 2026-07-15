#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Keyboard-controlled Multi-ranger mapping with guarded motion and landing."""

import math
import threading
import time

import numpy as np
from vispy import app as vispy_app
from vispy import scene
from vispy.scene import visuals
from vispy.scene.cameras import TurntableCamera

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.positioning.motion_commander import MotionCommander
from cflib.utils import uri_helper


LOG_PERIOD_MS = 100
FLIGHT_HEIGHT_M = 0.35
TRANSLATION_SPEED_MPS = 0.08
YAW_RATE_DPS = 30.0
MAX_FLIGHT_TIME_S = 90.0
LOG_STALE_TIMEOUT_S = 0.70
MOTION_CLEARANCE_M = 0.18
SIDE_EMERGENCY_DISTANCE_M = 0.10
UP_STOP_DISTANCE_M = 0.15
MAP_MAX_RANGE_M = 2.0
MAP_VOXEL_M = 0.025

DIRECTIONS = ("front", "back", "left", "right")
DIRECTION_ANGLE_DEG = {
    "front": 0.0,
    "left": 90.0,
    "right": -90.0,
    "back": 180.0,
}


def request_arming(scf, armed):
    for service_name in ("platform", "supervisor"):
        service = getattr(scf.cf, service_name, None)
        request = getattr(service, "send_arming_request", None)
        if request is not None:
            request(armed)
            return
    raise RuntimeError("This cflib version has no arming service.")


def require_group_uri():
    uri = uri_helper.uri_from_env(default="")
    if not uri:
        raise RuntimeError("CFLIB_URI is empty; configure the group URI first.")
    return uri


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


class ManualMappingDemo:
    def __init__(self, scf):
        self._scf = scf
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._data_ready = threading.Event()
        self._flight_thread = None
        self._last_log_time = 0.0
        self._position = [0.0, 0.0, 0.0]
        self._ranges = {name: None for name in DIRECTIONS}
        self._up_range = None
        self._command = [0.0, 0.0, 0.0]
        self._point_cells = {}

        self.canvas = scene.SceneCanvas(
            keys="interactive",
            show=True,
            title="Crazyflie Manual Multi-ranger Mapping",
        )
        self.canvas.events.close.connect(self._on_close)
        self.canvas.events.key_press.connect(self._on_key_press)
        self.canvas.events.key_release.connect(self._on_key_release)
        self.view = self.canvas.central_widget.add_view()
        self.view.bgcolor = "#ffffff"
        self.view.camera = TurntableCamera(
            fov=10.0, distance=5.0, up="+z", center=(0.0, 0.0, 0.0)
        )
        scene.visuals.XYZAxis(parent=self.view.scene)
        self.scatter = visuals.Markers()
        self.view.add(self.scatter)
        self.aircraft = visuals.Box(
            width=0.10,
            height=0.10,
            depth=0.03,
            color=(0.90, 0.15, 0.10, 1.0),
            edge_color="black",
        )
        self.view.add(self.aircraft)
        self._display_timer = vispy_app.Timer(
            "auto", connect=self._update_display, start=True
        )

        self._log = LogConfig(name="ManualMapping", period_in_ms=LOG_PERIOD_MS)
        for direction in DIRECTIONS:
            self._log.add_variable("range.%s" % direction, "uint16_t")
        self._log.add_variable("range.up", "uint16_t")
        self._log.add_variable("stateEstimate.x", "float")
        self._log.add_variable("stateEstimate.y", "float")
        self._log.add_variable("stateEstimate.yaw", "float")
        self._scf.cf.log.add_config(self._log)
        self._log.data_received_cb.add_callback(self._data_received)
        self._log.start()

    @staticmethod
    def _decode_range(raw_mm):
        if raw_mm is None:
            return None
        distance = float(raw_mm) / 1000.0
        if not math.isfinite(distance) or distance <= 0.03 or distance >= 4.0:
            return None
        return distance

    def _data_received(self, timestamp, data, log_config):
        x = float(data["stateEstimate.x"])
        y = float(data["stateEstimate.y"])
        yaw_deg = float(data["stateEstimate.yaw"])
        if not all(math.isfinite(value) for value in (x, y, yaw_deg)):
            return
        ranges = {
            name: self._decode_range(data.get("range.%s" % name))
            for name in DIRECTIONS
        }
        with self._lock:
            self._last_log_time = time.monotonic()
            self._position = [x, y, yaw_deg]
            self._ranges = ranges
            self._up_range = self._decode_range(data.get("range.up"))
            self._add_points_locked(x, y, yaw_deg, ranges)
        self._data_ready.set()

    def _add_points_locked(self, x, y, yaw_deg, ranges):
        for direction, distance in ranges.items():
            if distance is None or distance >= MAP_MAX_RANGE_M:
                continue
            angle = math.radians(yaw_deg + DIRECTION_ANGLE_DEG[direction])
            point_x = x + distance * math.cos(angle)
            point_y = y + distance * math.sin(angle)
            cell = (
                int(round(point_x / MAP_VOXEL_M)),
                int(round(point_y / MAP_VOXEL_M)),
            )
            self._point_cells.setdefault(cell, (point_x, point_y, 0.0))

    def _on_close(self, event):
        self._stop.set()

    @staticmethod
    def _key_name(event):
        return getattr(getattr(event, "key", None), "name", "")

    def _on_key_press(self, event):
        key = self._key_name(event)
        with self._lock:
            if key == "Up":
                self._command[0] = TRANSLATION_SPEED_MPS
            elif key == "Down":
                self._command[0] = -TRANSLATION_SPEED_MPS
            elif key == "Left":
                self._command[1] = TRANSLATION_SPEED_MPS
            elif key == "Right":
                self._command[1] = -TRANSLATION_SPEED_MPS
            elif key == "A":
                self._command[2] = YAW_RATE_DPS
            elif key == "D":
                self._command[2] = -YAW_RATE_DPS
            elif key == "Escape":
                self._stop.set()

    def _on_key_release(self, event):
        key = self._key_name(event)
        with self._lock:
            if key in ("Up", "Down"):
                self._command[0] = 0.0
            elif key in ("Left", "Right"):
                self._command[1] = 0.0
            elif key in ("A", "D"):
                self._command[2] = 0.0

    def start(self):
        self._flight_thread = threading.Thread(
            target=self._flight_worker,
            name="manual-mapping-flight",
            daemon=False,
        )
        self._flight_thread.start()

    def stop(self):
        self._stop.set()

    def wait(self):
        if self._flight_thread is not None:
            self._flight_thread.join()

    def close_log(self):
        self._log.stop()

    def _guarded_command(self, command, ranges):
        velocity_x, velocity_y, yaw_rate = command
        if velocity_x > 0.0 and self._too_close(ranges["front"]):
            velocity_x = 0.0
        if velocity_x < 0.0 and self._too_close(ranges["back"]):
            velocity_x = 0.0
        if velocity_y > 0.0 and self._too_close(ranges["left"]):
            velocity_y = 0.0
        if velocity_y < 0.0 and self._too_close(ranges["right"]):
            velocity_y = 0.0
        return velocity_x, velocity_y, yaw_rate

    @staticmethod
    def _too_close(distance):
        return distance is not None and distance < MOTION_CLEARANCE_M

    def _flight_worker(self):
        armed = False
        try:
            if not self._data_ready.wait(timeout=5.0):
                print("No range/position log data; takeoff cancelled.")
                return
            request_arming(self._scf, True)
            armed = True
            time.sleep(1.0)
            started = time.monotonic()
            print("Arrow keys move, A/D yaw, Escape or window close lands.")
            with MotionCommander(
                self._scf, default_height=FLIGHT_HEIGHT_M
            ) as commander:
                while not self._stop.is_set():
                    now = time.monotonic()
                    if now - started >= MAX_FLIGHT_TIME_S:
                        print("Maximum flight time reached; landing.")
                        break
                    with self._lock:
                        log_age = now - self._last_log_time
                        command = list(self._command)
                        ranges = dict(self._ranges)
                        up_range = self._up_range
                    if log_age > LOG_STALE_TIMEOUT_S:
                        print("Sensor log is stale; landing.")
                        break
                    if up_range is not None and up_range < UP_STOP_DISTANCE_M:
                        print("Upper-sensor stop gesture detected; landing.")
                        break
                    if any(
                        distance is not None
                        and distance < SIDE_EMERGENCY_DISTANCE_M
                        for distance in (ranges["left"], ranges["right"])
                    ):
                        print("Side emergency clearance reached; landing.")
                        break
                    velocity_x, velocity_y, yaw_rate = self._guarded_command(
                        command, ranges
                    )
                    commander.start_linear_motion(
                        velocity_x,
                        velocity_y,
                        0.0,
                        rate_yaw=yaw_rate,
                    )
                    time.sleep(0.1)
                commander.stop()
        except Exception as error:
            print("Manual mapping stopped: %s" % error)
        finally:
            if armed:
                request_arming(self._scf, False)

    def _update_display(self, event):
        with self._lock:
            x, y, _yaw = self._position
            points = list(self._point_cells.values())
        self.aircraft.transform = scene.transforms.STTransform(
            translate=(x, y, 0.05)
        )
        if points:
            self.scatter.set_data(
                np.asarray(points, dtype=np.float32),
                edge_color=None,
                face_color=(0.05, 0.35, 0.90, 0.72),
                size=5,
            )


def main():
    uri = require_group_uri()
    print("Using URI: %s" % uri)
    cflib.crtp.init_drivers()
    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache="./cache")) as scf:
        if not wait_for_decks(scf):
            raise RuntimeError(
                "Flow deck or Multi-ranger deck was not detected; takeoff cancelled."
            )
        demo = ManualMappingDemo(scf)
        demo.start()
        try:
            vispy_app.run()
        finally:
            demo.stop()
            demo.wait()
            demo.close_log()


if __name__ == "__main__":
    main()
