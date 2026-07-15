# -*- coding: utf-8 -*-
"""Autonomous Multi-ranger exploration and 2-D point-cloud mapping.

The Crazyflie explores an unknown indoor enclosure instead of following a
predefined route. It combines conservative reactive navigation with a small
visited-cell map. Narrow panel seams are rejected in two ways:

1. Side openings must remain visible while the aircraft travels across a
   configurable minimum opening width.
2. The forward corridor is checked from two headings before the aircraft is
   allowed to continue through it.

This is a supervised classroom example, not a certified collision-avoidance
system. Keep one operator ready to close the window or press Escape.
"""

import logging
import math
import statistics
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional, Tuple

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


logging.basicConfig(level=logging.ERROR)

# Flight envelope. Tune only after a low-speed supervised test.
FLIGHT_HEIGHT_M = 0.40
FORWARD_SPEED_MPS = 0.12
TURN_RATE_DPS = 45.0
MAX_FLIGHT_TIME_S = 120.0
MAX_RADIUS_FROM_START_M = 1.80
CONTROL_PERIOD_S = 0.10
LOG_TIMEOUT_S = 0.70
STUCK_TIMEOUT_S = 4.0
STUCK_DISTANCE_M = 0.10

# Range processing and collision margins.
LOG_PERIOD_MS = 100
MIN_RANGE_M = 0.08
SENSOR_OUT_OF_RANGE_M = 4.0
FILTER_WINDOW = 5
FILTER_MIN_SAMPLES = 3
FRONT_EMERGENCY_DISTANCE_M = 0.18
SIDE_EMERGENCY_DISTANCE_M = 0.10
SIDE_RECOVERY_CLEARANCE_M = 0.16
SIDE_RECOVERY_STEP_M = 0.04
SIDE_RECOVERY_SPEED_MPS = 0.08
FORWARD_STOP_DISTANCE_M = 0.32
TURN_CLEARANCE_M = 0.30

# Keep the aircraft near the centre of a 0.40-0.50 m channel.
CORRIDOR_WALL_MAX_M = 0.45
CORRIDOR_CENTERING_GAIN = 0.65
MAX_LATERAL_SPEED_MPS = 0.035

# A side opening is accepted only after it has a useful measured width.
SIDE_OPEN_DISTANCE_M = 0.60
SIDE_OPEN_MIN_WIDTH_M = 0.24
SIDE_OPEN_MIN_SAMPLES = 5

# A two-angle probe rejects a narrow seam directly in front of the sensor.
PROBE_ANGLE_DEG = 12.0
PROBE_CLEAR_DISTANCE_M = 0.52
PROBE_INTERVAL_M = 0.25
PROBE_SAMPLE_COUNT = 3
FILTER_SETTLE_S = 0.45
MAX_CONSECUTIVE_PROBE_FAILURES = 3

# Exploration and display resolution.
VISITED_CELL_M = 0.25
TARGET_LOOKAHEAD_M = 0.55
MAP_MAX_RANGE_M = 2.00
MAP_VOXEL_M = 0.025

DIRECTIONS = ("front", "back", "left", "right")
DIRECTION_ANGLE_DEG = {
    "front": 0.0,
    "left": 90.0,
    "right": -90.0,
    "back": 180.0,
}
SENSOR_GEOMETRY = {
    "front": ((0.03, 0.00), (1.0, 0.0)),
    "back": ((-0.03, 0.00), (-1.0, 0.0)),
    "left": ((0.00, 0.03), (0.0, 1.0)),
    "right": ((0.00, -0.03), (0.0, -1.0)),
}


class GapResistantRangeFilter:
    """Median filter plus travelled-width confirmation for openings."""

    def __init__(self) -> None:
        self._history: Deque[Optional[float]] = deque(maxlen=FILTER_WINDOW)
        self.raw_m: Optional[float] = None
        self.filtered_m: Optional[float] = None
        self.open_samples = 0
        self.open_travel_m = 0.0
        self.confirmed_open = False

    @staticmethod
    def decode_mm(raw_mm: object) -> Optional[float]:
        try:
            value = float(raw_mm)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or value <= 0.0:
            return None
        distance_m = value / 1000.0
        if distance_m < MIN_RANGE_M:
            return None
        if distance_m >= SENSOR_OUT_OF_RANGE_M:
            return SENSOR_OUT_OF_RANGE_M
        return distance_m

    def reset(self) -> None:
        self._history.clear()
        self.raw_m = None
        self.filtered_m = None
        self.open_samples = 0
        self.open_travel_m = 0.0
        self.confirmed_open = False

    def update(self, raw_mm: object, travelled_m: float) -> None:
        self.raw_m = self.decode_mm(raw_mm)
        self._history.append(self.raw_m)
        valid = [value for value in self._history if value is not None]
        self.filtered_m = (
            statistics.median(valid)
            if len(valid) >= FILTER_MIN_SAMPLES
            else None
        )

        if self.filtered_m is not None and self.filtered_m >= SIDE_OPEN_DISTANCE_M:
            self.open_samples += 1
            self.open_travel_m += max(0.0, min(travelled_m, 0.10))
            self.confirmed_open = (
                self.open_samples >= SIDE_OPEN_MIN_SAMPLES
                and self.open_travel_m >= SIDE_OPEN_MIN_WIDTH_M
            )
        else:
            self.open_samples = 0
            self.open_travel_m = 0.0
            self.confirmed_open = False


@dataclass(frozen=True)
class SensorSnapshot:
    sample_id: int
    monotonic_time: float
    x: float
    y: float
    yaw_deg: float
    raw_m: Dict[str, Optional[float]]
    filtered_m: Dict[str, Optional[float]]
    confirmed_open: Dict[str, bool]


class MappingDemo:
    def __init__(self, scf: SyncCrazyflie) -> None:
        self._scf = scf
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._data_ready = threading.Event()
        self._flight_finished = threading.Event()
        self._flight_thread: Optional[threading.Thread] = None

        self._filters = {name: GapResistantRangeFilter() for name in DIRECTIONS}
        self._sample_id = 0
        self._ready_samples = 0
        self._last_log_time = 0.0
        self._current_pos = [0.0, 0.0, 0.0]
        self._last_travel_pos: Optional[Tuple[float, float]] = None
        self._origin: Optional[Tuple[float, float]] = None
        self._is_mapping = False

        self._visited_counts: Dict[Tuple[int, int], int] = defaultdict(int)
        self._last_visit_cell: Optional[Tuple[int, int]] = None
        self._point_cells: Dict[Tuple[int, int], Tuple[float, float, float]] = {}
        self._turn_bias = "left"
        self._last_probe_pos: Optional[Tuple[float, float]] = None

        self.canvas = scene.SceneCanvas(
            keys="interactive",
            show=True,
            title="Crazyflie Multi-ranger Autonomous Exploration",
        )
        self.canvas.events.close.connect(self._on_canvas_close)
        self.canvas.events.key_press.connect(self._on_key_press)
        self.view = self.canvas.central_widget.add_view()
        self.view.bgcolor = "#ffffff"
        self.view.camera = TurntableCamera(
            fov=10.0,
            distance=5.0,
            up="+z",
            center=(0.0, 0.0, 0.0),
        )
        scene.visuals.XYZAxis(parent=self.view.scene)

        self.scatter = visuals.Markers()
        self.view.add(self.scatter)
        self.ship = visuals.Box(
            width=0.10,
            height=0.10,
            depth=0.03,
            color=(0.9, 0.15, 0.10, 1.0),
            edge_color="black",
        )
        self.view.add(self.ship)

        self._display_timer = vispy_app.Timer(
            "auto", connect=self._update_display, start=True
        )
        self._start_logging()

    def _start_logging(self) -> None:
        self._log_config = LogConfig(name="Mapping", period_in_ms=LOG_PERIOD_MS)
        for name in DIRECTIONS:
            self._log_config.add_variable("range.%s" % name, "uint16_t")
        self._log_config.add_variable("stateEstimate.x", "float")
        self._log_config.add_variable("stateEstimate.y", "float")
        self._log_config.add_variable("stateEstimate.yaw", "float")
        self._scf.cf.log.add_config(self._log_config)
        self._log_config.data_received_cb.add_callback(self._data_received)
        if hasattr(self._log_config, "error_cb"):
            self._log_config.error_cb.add_callback(self._log_error)
        self._log_config.start()

    def start_flight(self) -> None:
        self._flight_thread = threading.Thread(
            target=self._flight_worker,
            name="multiranger-exploration",
            daemon=False,
        )
        self._flight_thread.start()

    def request_stop(self) -> None:
        self._stop_event.set()

    def wait_for_flight(self) -> None:
        if self._flight_thread is not None:
            self._flight_thread.join()

    def stop_logging(self) -> None:
        try:
            self._log_config.stop()
        except Exception:
            pass

    def _log_error(self, log_config: LogConfig, message: str) -> None:
        print("Logging error: %s" % message)
        self._stop_event.set()

    def _on_canvas_close(self, event: object) -> None:
        self.request_stop()

    def _on_key_press(self, event: object) -> None:
        key = getattr(getattr(event, "key", None), "name", "")
        if key == "Escape":
            print("Escape pressed: stopping exploration and landing.")
            self.request_stop()

    def _data_received(
        self,
        timestamp: int,
        data: Dict[str, float],
        log_config: LogConfig,
    ) -> None:
        now = time.monotonic()
        x = float(data["stateEstimate.x"])
        y = float(data["stateEstimate.y"])
        yaw_deg = float(data["stateEstimate.yaw"])
        if not all(math.isfinite(value) for value in (x, y, yaw_deg)):
            return

        with self._lock:
            travelled_m = 0.0
            if self._last_travel_pos is not None:
                travelled_m = math.hypot(
                    x - self._last_travel_pos[0], y - self._last_travel_pos[1]
                )
                if travelled_m > 0.15:
                    travelled_m = 0.0
            self._last_travel_pos = (x, y)

            for name in DIRECTIONS:
                self._filters[name].update(data.get("range.%s" % name), travelled_m)

            self._sample_id += 1
            self._ready_samples += 1
            self._last_log_time = now
            self._current_pos = [x, y, yaw_deg]
            if self._ready_samples >= FILTER_WINDOW:
                self._data_ready.set()

            if self._is_mapping:
                self._mark_visited_locked(x, y)
                self._add_map_points_locked(x, y, yaw_deg)

    def _mark_visited_locked(self, x: float, y: float) -> None:
        cell = (
            int(round(x / VISITED_CELL_M)),
            int(round(y / VISITED_CELL_M)),
        )
        if cell != self._last_visit_cell:
            self._visited_counts[cell] += 1
            self._last_visit_cell = cell

    def _add_map_points_locked(self, x: float, y: float, yaw_deg: float) -> None:
        yaw_rad = math.radians(yaw_deg)
        cos_yaw = math.cos(yaw_rad)
        sin_yaw = math.sin(yaw_rad)

        for name, (offset, direction) in SENSOR_GEOMETRY.items():
            distance_m = self._filters[name].filtered_m
            if distance_m is None or not (MIN_RANGE_M < distance_m < MAP_MAX_RANGE_M):
                continue
            body_x = offset[0] + distance_m * direction[0]
            body_y = offset[1] + distance_m * direction[1]
            world_x = x + cos_yaw * body_x - sin_yaw * body_y
            world_y = y + sin_yaw * body_x + cos_yaw * body_y
            voxel = (
                int(round(world_x / MAP_VOXEL_M)),
                int(round(world_y / MAP_VOXEL_M)),
            )
            self._point_cells.setdefault(voxel, (world_x, world_y, 0.0))

    def _snapshot(self) -> SensorSnapshot:
        with self._lock:
            return SensorSnapshot(
                sample_id=self._sample_id,
                monotonic_time=self._last_log_time,
                x=self._current_pos[0],
                y=self._current_pos[1],
                yaw_deg=self._current_pos[2],
                raw_m={name: self._filters[name].raw_m for name in DIRECTIONS},
                filtered_m={
                    name: self._filters[name].filtered_m for name in DIRECTIONS
                },
                confirmed_open={
                    name: self._filters[name].confirmed_open for name in DIRECTIONS
                },
            )

    def _reset_filters(self) -> None:
        with self._lock:
            for range_filter in self._filters.values():
                range_filter.reset()

    def _flight_worker(self) -> None:
        try:
            if not self._data_ready.wait(timeout=6.0):
                print("No stable Multi-ranger/position log data; takeoff cancelled.")
                return
            initial = self._snapshot()
            if any(initial.filtered_m[name] is None for name in DIRECTIONS):
                print("One or more horizontal range sensors are unavailable; takeoff cancelled.")
                return

            self._request_arming(True)
            time.sleep(1.0)
            print("Taking off. Close the window or press Escape to land.")
            with MotionCommander(self._scf, default_height=FLIGHT_HEIGHT_M) as mc:
                time.sleep(1.0)
                start = self._snapshot()
                self._origin = (start.x, start.y)
                with self._lock:
                    self._is_mapping = True
                    self._mark_visited_locked(start.x, start.y)
                self._explore(mc)
                mc.stop()
                print("Exploration complete; landing in place.")
        except Exception as error:
            print("Flight error: %s" % error)
            print("MotionCommander will leave its context and request a landing.")
        finally:
            with self._lock:
                self._is_mapping = False
            try:
                self._request_arming(False)
            except Exception:
                pass
            self._flight_finished.set()
            print("Mapping stopped. The map window remains available for inspection.")

    def _request_arming(self, armed: bool) -> None:
        for service_name in ("platform", "supervisor"):
            service = getattr(self._scf.cf, service_name, None)
            request = getattr(service, "send_arming_request", None)
            if request is not None:
                request(armed)
                return

    def _explore(self, mc: MotionCommander) -> None:
        start_time = time.monotonic()
        progress_anchor = self._snapshot()
        progress_time = time.monotonic()
        moving_forward = False
        probe_failures = 0

        while not self._stop_event.is_set():
            now = time.monotonic()
            snapshot = self._snapshot()

            if now - start_time >= MAX_FLIGHT_TIME_S:
                print("Maximum flight time reached.")
                break
            if now - snapshot.monotonic_time > LOG_TIMEOUT_S:
                print("Sensor log is stale; stopping and landing.")
                break
            if self._outside_flight_envelope(snapshot):
                print("Maximum distance from the start reached; landing in place.")
                break

            front_raw_m = snapshot.raw_m["front"]
            if (
                front_raw_m is not None
                and front_raw_m < FRONT_EMERGENCY_DISTANCE_M
            ):
                if moving_forward:
                    mc.stop()
                    moving_forward = False
                direction = self._select_turn(snapshot)
                if direction is None:
                    print("Front emergency clearance unavailable; landing in place.")
                    break
                print("Front emergency response: turn %s." % direction)
                self._execute_turn(mc, direction)
                progress_anchor = self._snapshot()
                progress_time = time.monotonic()
                continue

            if self._side_emergency(snapshot):
                if moving_forward:
                    mc.stop()
                    moving_forward = False
                if not self._recover_side_clearance(mc, snapshot):
                    print("Side clearance cannot be recovered; landing in place.")
                    break
                progress_anchor = self._snapshot()
                progress_time = time.monotonic()
                continue

            if moving_forward:
                progress = math.hypot(
                    snapshot.x - progress_anchor.x,
                    snapshot.y - progress_anchor.y,
                )
                if progress >= STUCK_DISTANCE_M:
                    progress_anchor = snapshot
                    progress_time = now
                elif now - progress_time >= STUCK_TIMEOUT_S:
                    mc.stop()
                    moving_forward = False
                    direction = self._select_turn(snapshot)
                    if direction is None:
                        print("No progress and no safe turn; landing in place.")
                        break
                    print("No forward progress; turn %s." % direction)
                    self._execute_turn(mc, direction)
                    progress_anchor = self._snapshot()
                    progress_time = time.monotonic()
                    continue

            side_branch = self._select_side_branch(snapshot)
            if side_branch is not None:
                if moving_forward:
                    mc.stop()
                    moving_forward = False
                print("Selecting an unvisited %s branch." % side_branch)
                self._execute_turn(mc, side_branch)
                progress_anchor = self._snapshot()
                progress_time = time.monotonic()
                continue

            front_m = snapshot.filtered_m["front"]
            if front_m is None or front_m < FORWARD_STOP_DISTANCE_M:
                if moving_forward:
                    mc.stop()
                    moving_forward = False
                direction = self._select_turn(snapshot)
                if direction is None:
                    print("No confirmed route is clear; landing in place.")
                    break
                print("Front blocked; turn %s." % direction)
                self._execute_turn(mc, direction)
                progress_anchor = self._snapshot()
                progress_time = time.monotonic()
                continue

            if self._probe_due(snapshot):
                if moving_forward:
                    mc.stop()
                    moving_forward = False
                if self._probe_forward_corridor(mc):
                    probe_failures = 0
                    after_probe = self._snapshot()
                    self._last_probe_pos = (after_probe.x, after_probe.y)
                    progress_anchor = after_probe
                    progress_time = time.monotonic()
                    continue

                probe_failures += 1
                print("Forward width probe rejected the apparent opening.")
                if probe_failures >= MAX_CONSECUTIVE_PROBE_FAILURES:
                    print("Repeated width-probe failures; landing in place.")
                    break
                snapshot = self._snapshot()
                direction = self._select_turn(snapshot)
                if direction is None:
                    break
                self._execute_turn(mc, direction)
                progress_anchor = self._snapshot()
                progress_time = time.monotonic()
                continue

            lateral_speed_mps = self._corridor_centering_speed(snapshot)
            starting_motion = not moving_forward
            mc.start_linear_motion(
                FORWARD_SPEED_MPS,
                lateral_speed_mps,
                0.0,
            )
            if starting_motion:
                moving_forward = True
                progress_anchor = snapshot
                progress_time = now
            time.sleep(CONTROL_PERIOD_S)

        if moving_forward:
            mc.stop()

    def _outside_flight_envelope(self, snapshot: SensorSnapshot) -> bool:
        if self._origin is None:
            return False
        return (
            math.hypot(snapshot.x - self._origin[0], snapshot.y - self._origin[1])
            > MAX_RADIUS_FROM_START_M
        )

    @staticmethod
    def _side_emergency(snapshot: SensorSnapshot) -> bool:
        return any(
            snapshot.raw_m[direction] is not None
            and snapshot.raw_m[direction] < SIDE_EMERGENCY_DISTANCE_M
            for direction in ("left", "right")
        )

    def _recover_side_clearance(
        self, mc: MotionCommander, snapshot: SensorSnapshot
    ) -> bool:
        left_m = snapshot.raw_m["left"]
        right_m = snapshot.raw_m["right"]
        if left_m is not None and left_m < SIDE_EMERGENCY_DISTANCE_M:
            if right_m is None or right_m < SIDE_RECOVERY_CLEARANCE_M:
                return False
            print("Too close on the left; shifting right.")
            mc.right(SIDE_RECOVERY_STEP_M, velocity=SIDE_RECOVERY_SPEED_MPS)
        elif right_m is not None and right_m < SIDE_EMERGENCY_DISTANCE_M:
            if left_m is None or left_m < SIDE_RECOVERY_CLEARANCE_M:
                return False
            print("Too close on the right; shifting left.")
            mc.left(SIDE_RECOVERY_STEP_M, velocity=SIDE_RECOVERY_SPEED_MPS)
        else:
            return True
        self._reset_filters()
        time.sleep(FILTER_SETTLE_S)
        return True

    @staticmethod
    def _corridor_centering_speed(snapshot: SensorSnapshot) -> float:
        left_m = snapshot.filtered_m["left"]
        right_m = snapshot.filtered_m["right"]
        if left_m is None or right_m is None:
            return 0.0
        if not (
            SIDE_EMERGENCY_DISTANCE_M <= left_m <= CORRIDOR_WALL_MAX_M
            and SIDE_EMERGENCY_DISTANCE_M <= right_m <= CORRIDOR_WALL_MAX_M
        ):
            return 0.0
        correction = CORRIDOR_CENTERING_GAIN * (left_m - right_m)
        return max(-MAX_LATERAL_SPEED_MPS, min(MAX_LATERAL_SPEED_MPS, correction))

    def _probe_due(self, snapshot: SensorSnapshot) -> bool:
        if self._last_probe_pos is None:
            return True
        return (
            math.hypot(
                snapshot.x - self._last_probe_pos[0],
                snapshot.y - self._last_probe_pos[1],
            )
            >= PROBE_INTERVAL_M
        )

    def _probe_forward_corridor(self, mc: MotionCommander) -> bool:
        mc.turn_left(PROBE_ANGLE_DEG, rate=TURN_RATE_DPS)
        self._reset_filters()
        left_probe = self._sample_front_raw()

        mc.turn_right(2.0 * PROBE_ANGLE_DEG, rate=TURN_RATE_DPS)
        self._reset_filters()
        right_probe = self._sample_front_raw()

        mc.turn_left(PROBE_ANGLE_DEG, rate=TURN_RATE_DPS)
        self._reset_filters()
        time.sleep(FILTER_SETTLE_S)

        return (
            left_probe is not None
            and right_probe is not None
            and left_probe >= PROBE_CLEAR_DISTANCE_M
            and right_probe >= PROBE_CLEAR_DISTANCE_M
        )

    def _sample_front_raw(self) -> Optional[float]:
        samples: List[float] = []
        initial = self._snapshot()
        last_sample_id = initial.sample_id
        deadline = time.monotonic() + 0.90
        while time.monotonic() < deadline and len(samples) < PROBE_SAMPLE_COUNT:
            snapshot = self._snapshot()
            if snapshot.sample_id != last_sample_id:
                last_sample_id = snapshot.sample_id
                value = snapshot.raw_m["front"]
                if value is not None:
                    samples.append(value)
            time.sleep(0.02)
        if len(samples) < PROBE_SAMPLE_COUNT:
            return None
        return statistics.median(samples)

    def _select_side_branch(self, snapshot: SensorSnapshot) -> Optional[str]:
        candidates = [
            direction
            for direction in ("left", "right")
            if snapshot.confirmed_open[direction]
            and snapshot.filtered_m[direction] is not None
            and snapshot.filtered_m[direction] >= SIDE_OPEN_DISTANCE_M
        ]
        if not candidates:
            return None

        front_score = self._direction_visit_score(snapshot, "front")
        candidates.sort(
            key=lambda direction: (
                self._direction_visit_score(snapshot, direction),
                0 if direction == self._turn_bias else 1,
            )
        )
        best = candidates[0]
        if self._direction_visit_score(snapshot, best) <= front_score:
            return best
        return None

    def _select_turn(self, snapshot: SensorSnapshot) -> Optional[str]:
        side_candidates = [
            direction
            for direction in ("left", "right")
            if snapshot.confirmed_open[direction]
            and snapshot.filtered_m[direction] is not None
            and snapshot.filtered_m[direction] >= TURN_CLEARANCE_M
        ]
        if side_candidates:
            side_candidates.sort(
                key=lambda direction: (
                    self._direction_visit_score(snapshot, direction),
                    0 if direction == self._turn_bias else 1,
                )
            )
            return side_candidates[0]

        back_m = snapshot.filtered_m["back"]
        if back_m is not None and back_m >= TURN_CLEARANCE_M:
            return "back"
        return None

    def _direction_visit_score(
        self, snapshot: SensorSnapshot, direction: str
    ) -> int:
        angle_rad = math.radians(
            snapshot.yaw_deg + DIRECTION_ANGLE_DEG[direction]
        )
        target_x = snapshot.x + TARGET_LOOKAHEAD_M * math.cos(angle_rad)
        target_y = snapshot.y + TARGET_LOOKAHEAD_M * math.sin(angle_rad)
        cell = (
            int(round(target_x / VISITED_CELL_M)),
            int(round(target_y / VISITED_CELL_M)),
        )
        with self._lock:
            return self._visited_counts.get(cell, 0)

    def _execute_turn(self, mc: MotionCommander, direction: str) -> None:
        mc.stop()
        if direction == "left":
            mc.turn_left(90.0, rate=TURN_RATE_DPS)
            self._turn_bias = "right"
        elif direction == "right":
            mc.turn_right(90.0, rate=TURN_RATE_DPS)
            self._turn_bias = "left"
        elif direction == "back":
            mc.turn_left(180.0, rate=TURN_RATE_DPS)
        else:
            raise ValueError("Unsupported turn direction: %s" % direction)
        self._last_probe_pos = None
        self._reset_filters()
        time.sleep(FILTER_SETTLE_S)

    def _update_display(self, event: object) -> None:
        with self._lock:
            x, y, _yaw = self._current_pos
            points = list(self._point_cells.values())
        self.ship.transform = scene.transforms.STTransform(translate=(x, y, 0.05))
        if points:
            self.scatter.set_data(
                np.asarray(points, dtype=np.float32),
                edge_color=None,
                face_color=(0.05, 0.35, 0.90, 0.72),
                size=5,
            )


def wait_for_flow_deck(scf: SyncCrazyflie) -> bool:
    attached = threading.Event()

    def flow_callback(name: str, value: str) -> None:
        if int(value):
            attached.set()

    scf.cf.param.add_update_callback(
        group="deck", name="bcFlow2", cb=flow_callback
    )
    time.sleep(1.0)
    return attached.wait(timeout=5.0)


def get_group_uri() -> str:
    uri = uri_helper.uri_from_env(default="")
    if not uri:
        raise RuntimeError(
            "CFLIB_URI is empty. Complete Experiment 3 and open a new terminal."
        )
    return uri


def main() -> None:
    uri = get_group_uri()
    print("Using URI: %s" % uri)
    cflib.crtp.init_drivers()
    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache="./cache")) as scf:
        if not wait_for_flow_deck(scf):
            raise RuntimeError("Flow deck was not detected; takeoff cancelled.")
        demo = MappingDemo(scf)
        demo.start_flight()
        try:
            vispy_app.run()
        finally:
            demo.request_stop()
            demo.wait_for_flight()
            demo.stop_logging()


if __name__ == "__main__":
    main()
