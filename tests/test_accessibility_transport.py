import unittest

from tools.test_accessibility_transport import _receiver_result


class AccessibilityTransportTests(unittest.TestCase):
    def test_receiver_result_one_is_success_even_when_am_returncode_is_nonzero(self):
        output = (
            "Broadcasting: Intent { act=com.infoney.nova.SCROLL_WINDOW }\n"
            "Broadcast completed: result=1"
        )
        self.assertEqual(_receiver_result(output), 1)

    def test_receiver_result_zero_is_failure(self):
        self.assertEqual(_receiver_result("Broadcast completed: result=0"), 0)

    def test_missing_receiver_result_is_unknown(self):
        self.assertIsNone(_receiver_result("Broadcasting: Intent { ... }"))


if __name__ == "__main__":
    unittest.main()
