import math
import unittest

from assets.code.wall_following import GapResistantRangeFilter
from assets.code.wall_following import WallFollowing


class GapResistantRangeFilterTests(unittest.TestCase):
    def test_short_panel_gap_is_held(self):
        range_filter = GapResistantRangeFilter(gap_confirm_seconds=0.8)
        for index in range(5):
            value = range_filter.update(0.18, now=index * 0.1)
        self.assertAlmostEqual(value, 0.18)

        for now in (0.5, 0.7, 1.0, 1.2):
            value = range_filter.update(None, now=now)
            self.assertLess(value, 0.30)

    def test_sustained_opening_is_confirmed(self):
        range_filter = GapResistantRangeFilter(gap_confirm_seconds=0.8)
        for index in range(5):
            range_filter.update(0.18, now=index * 0.1)
        range_filter.update(None, now=0.5)
        value = range_filter.update(None, now=1.31)
        self.assertGreater(value, 1.0)


class WallFollowingTests(unittest.TestCase):
    def test_left_wall_correction_moves_left_when_wall_is_far(self):
        controller = WallFollowing(wall_side=WallFollowing.WallSide.LEFT)
        controller.state = WallFollowing.State.FOLLOW_WALL
        velocity_x, velocity_y, yaw_rate, _ = controller.update(
            1.0, 0.25, 0.0, now=0.0
        )
        self.assertGreater(velocity_x, 0.0)
        self.assertGreater(velocity_y, 0.0)
        self.assertEqual(yaw_rate, 0.0)

    def test_right_wall_correction_moves_right_when_wall_is_far(self):
        controller = WallFollowing(wall_side=WallFollowing.WallSide.RIGHT)
        controller.state = WallFollowing.State.FOLLOW_WALL
        _, velocity_y, _, _ = controller.update(1.0, 0.25, 0.0, now=0.0)
        self.assertLess(velocity_y, 0.0)

    def test_inner_corner_turns_away_from_left_wall(self):
        controller = WallFollowing(wall_side=WallFollowing.WallSide.LEFT)
        controller.state = WallFollowing.State.FOLLOW_WALL
        _, _, yaw_rate, state = controller.update(0.20, 0.18, 0.0, now=0.0)
        self.assertEqual(state, WallFollowing.State.TURN_INNER_CORNER)
        self.assertLess(yaw_rate, 0.0)

        _, _, _, state = controller.update(
            1.0,
            0.18,
            -math.radians(85.0),
            now=2.0,
        )
        self.assertEqual(state, WallFollowing.State.FOLLOW_WALL)

    def test_outer_corner_timeout_falls_back_to_hover(self):
        controller = WallFollowing(wall_side=WallFollowing.WallSide.LEFT)
        controller.state = WallFollowing.State.FOLLOW_WALL
        controller.update(1.0, 1.0, 0.0, now=0.0)
        _, _, _, state = controller.update(1.0, 1.0, 0.0, now=4.1)
        self.assertEqual(state, WallFollowing.State.HOVER)


if __name__ == "__main__":
    unittest.main()
