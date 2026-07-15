# -*- coding: utf-8 -*-
"""Gap-resistant wall-following controller for the classroom arena.

The controller is intentionally independent of cflib so its state transitions
can be checked without connecting a Crazyflie. Distances are in metres,
headings and yaw rates are in radians, and body-frame velocities are in m/s.

The state-machine structure is based on the Bitcraze wall-following demo:
https://github.com/bitcraze/crazyflie-demos/tree/main/demos/scripts/cflib/multiranger/multiranger_wall_following
"""

import math
import statistics
import time
from collections import deque
from enum import Enum


class GapResistantRangeFilter:
    """Median filter that requires a sustained far reading to declare a gap."""

    def __init__(
        self,
        window_size=5,
        minimum_samples=3,
        far_distance=4.0,
        gap_threshold=0.45,
        gap_confirm_seconds=0.80,
    ):
        self._history = deque(maxlen=window_size)
        self._minimum_samples = minimum_samples
        self._far_distance = far_distance
        self._gap_threshold = gap_threshold
        self._gap_confirm_seconds = gap_confirm_seconds
        self._last_near = None
        self._gap_started = None

    @staticmethod
    def _valid_distance(value):
        if value is None:
            return None
        try:
            distance = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(distance) or distance <= 0.03:
            return None
        return distance

    def update(self, value, now=None):
        """Return a filtered distance; ``None``/out-of-range means open space."""
        if now is None:
            now = time.monotonic()

        distance = self._valid_distance(value)
        looks_far = distance is None or distance >= self._gap_threshold

        if looks_far and self._last_near is not None:
            if self._gap_started is None:
                self._gap_started = now
            if now - self._gap_started < self._gap_confirm_seconds:
                distance = self._last_near
            else:
                distance = self._far_distance
                self._last_near = None
                self._history.clear()
        elif looks_far:
            distance = self._far_distance
        else:
            self._gap_started = None
            self._last_near = distance

        self._history.append(distance)
        if len(self._history) < self._minimum_samples:
            return distance
        return statistics.median(self._history)


class WallFollowing:
    """Small wall-following state machine for straight panel corridors."""

    class State(Enum):
        SEARCH_FORWARD = 1
        FOLLOW_WALL = 2
        TURN_INNER_CORNER = 3
        ROUND_OUTER_CORNER = 4
        HOVER = 5

    class WallSide(Enum):
        LEFT = 1.0
        RIGHT = -1.0

    def __init__(
        self,
        wall_side=WallSide.LEFT,
        reference_distance=0.18,
        front_stop_distance=0.24,
        side_lost_distance=0.42,
        max_forward_speed=0.08,
        max_lateral_speed=0.035,
        lateral_gain=0.60,
        max_turn_rate=math.radians(45.0),
        corner_angle=math.radians(82.0),
        outer_forward_seconds=0.80,
        outer_corner_timeout=4.0,
    ):
        self.wall_side = wall_side
        self.reference_distance = reference_distance
        self.front_stop_distance = front_stop_distance
        self.side_lost_distance = side_lost_distance
        self.max_forward_speed = max_forward_speed
        self.max_lateral_speed = max_lateral_speed
        self.lateral_gain = lateral_gain
        self.max_turn_rate = max_turn_rate
        self.corner_angle = corner_angle
        self.outer_forward_seconds = outer_forward_seconds
        self.outer_corner_timeout = outer_corner_timeout

        self.state = self.State.SEARCH_FORWARD
        self._state_started = 0.0
        self._turn_start_heading = 0.0

    @staticmethod
    def _wrap_to_pi(angle):
        return (angle + math.pi) % (2.0 * math.pi) - math.pi

    def _enter(self, state, heading, now):
        self.state = state
        self._state_started = now
        self._turn_start_heading = heading

    def _follow_command(self, front_range, side_range):
        clearance = max(0.0, front_range - self.front_stop_distance)
        speed_scale = max(0.35, min(1.0, clearance / 0.25))
        velocity_x = self.max_forward_speed * speed_scale

        side_error = side_range - self.reference_distance
        velocity_y = self.wall_side.value * self.lateral_gain * side_error
        velocity_y = max(
            -self.max_lateral_speed,
            min(self.max_lateral_speed, velocity_y),
        )
        return velocity_x, velocity_y, 0.0

    def update(self, front_range, side_range, heading, now=None):
        """Return ``velocity_x, velocity_y, yaw_rate, state``."""
        if now is None:
            now = time.monotonic()
        if front_range is None or side_range is None:
            self.state = self.State.HOVER
            return 0.0, 0.0, 0.0, self.state

        if self.state == self.State.SEARCH_FORWARD:
            if front_range <= self.front_stop_distance:
                self._enter(self.State.TURN_INNER_CORNER, heading, now)
            elif side_range <= self.side_lost_distance:
                self._enter(self.State.FOLLOW_WALL, heading, now)

        elif self.state == self.State.FOLLOW_WALL:
            if front_range <= self.front_stop_distance:
                self._enter(self.State.TURN_INNER_CORNER, heading, now)
            elif side_range > self.side_lost_distance:
                self._enter(self.State.ROUND_OUTER_CORNER, heading, now)

        elif self.state == self.State.TURN_INNER_CORNER:
            turn_sign = -self.wall_side.value
            progress = turn_sign * self._wrap_to_pi(
                heading - self._turn_start_heading
            )
            if progress >= self.corner_angle:
                self._enter(self.State.FOLLOW_WALL, heading, now)

        elif self.state == self.State.ROUND_OUTER_CORNER:
            elapsed = now - self._state_started
            turn_sign = self.wall_side.value
            progress = turn_sign * self._wrap_to_pi(
                heading - self._turn_start_heading
            )
            wall_reacquired = (
                side_range <= self.side_lost_distance
                and progress >= math.radians(25.0)
            )
            if wall_reacquired:
                self._enter(self.State.FOLLOW_WALL, heading, now)
            elif elapsed >= self.outer_corner_timeout:
                self._enter(self.State.HOVER, heading, now)

        if self.state == self.State.SEARCH_FORWARD:
            return self.max_forward_speed * 0.60, 0.0, 0.0, self.state
        if self.state == self.State.FOLLOW_WALL:
            return (*self._follow_command(front_range, side_range), self.state)
        if self.state == self.State.TURN_INNER_CORNER:
            yaw_rate = -self.wall_side.value * self.max_turn_rate
            return 0.0, 0.0, yaw_rate, self.state
        if self.state == self.State.ROUND_OUTER_CORNER:
            elapsed = now - self._state_started
            if elapsed < self.outer_forward_seconds:
                return self.max_forward_speed * 0.60, 0.0, 0.0, self.state
            yaw_rate = self.wall_side.value * self.max_turn_rate
            return 0.0, 0.0, yaw_rate, self.state
        return 0.0, 0.0, 0.0, self.State.HOVER
