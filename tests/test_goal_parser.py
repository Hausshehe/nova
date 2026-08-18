import unittest

from navigation.goal_parser import parse_open_path


class GoalParserTests(unittest.TestCase):
    def test_multi_step_open_goal(self):
        goal = "Open Settings and open Apps, then open YouTube"
        self.assertEqual(parse_open_path(goal), ["Settings", "Apps", "YouTube"])

    def test_single_open_goal(self):
        self.assertEqual(parse_open_path("open Chrome"), ["Chrome"])


if __name__ == "__main__":
    unittest.main()
