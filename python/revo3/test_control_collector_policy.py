import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from revo3.control_collector_policy import (
    OBSERVED_JOINTS,
    CollectorRates,
    observed_joint_summary,
)


class Status:
    def __init__(self):
        self.positions = [0.0] * 21
        self.velocities = [0.0] * 21
        self.currents = [0.0] * 21
        self.statuses = [0] * 21


class ControlCollectorPolicyTest(unittest.TestCase):
    def test_control_rate_is_lower_than_idle_rate(self):
        rates = CollectorRates(idle_hz=60, control_hz=10)

        self.assertEqual(rates.idle_hz, 60)
        self.assertEqual(rates.control_hz, 10)

    def test_rejects_control_rate_above_idle_rate(self):
        with self.assertRaises(ValueError):
            CollectorRates(idle_hz=10, control_hz=60)

    def test_observed_summary_covers_representative_joints(self):
        status = Status()
        status.positions[0] = 1.0
        status.positions[13] = 13.0
        status.positions[16] = 16.0

        summary = observed_joint_summary(status)

        self.assertEqual(OBSERVED_JOINTS, ((0, "Pinky"), (13, "Index"), (16, "Thumb")))
        self.assertIn("J0(Pinky)=1.00deg", summary)
        self.assertIn("J13(Index)=13.00deg", summary)
        self.assertIn("J16(Thumb)=16.00deg", summary)


if __name__ == "__main__":
    unittest.main()
