"""
Quintic Polynomial Trajectory Interpolator

Boundary conditions: zero start/end velocity and acceleration.
Input:  start_pos (deg), target_pos (deg), T (seconds)
Output: get(t) -> (position_deg, velocity_dps)

Polynomial:
    s(t) = a0 + a3*t^3 + a4*t^4 + a5*t^5

Constraints:
    s(0) = start,  s(T) = target
    s'(0) = 0,     s'(T) = 0
    s''(0) = 0,    s''(T) = 0

Solution:
    a0 = start
    a3 =  10 * h / T^3
    a4 = -15 * h / T^4
    a5 =   6 * h / T^5
    where h = target - start
"""

from typing import Tuple


class QuinticTrajectory:
    """5th-order polynomial trajectory with zero-vel/accel boundaries."""

    def __init__(self, start_pos: float, target_pos: float, duration: float) -> None:
        self.p0 = start_pos
        self.p1 = target_pos
        self.T = duration
        h = target_pos - start_pos
        T2 = duration * duration
        T3 = T2 * duration
        self.a3 = 10.0 * h / T3
        self.a4 = -15.0 * h / (T3 * duration)
        self.a5 = 6.0 * h / (T3 * T2)

    def get(self, t: float) -> Tuple[float, float]:
        """Return (position_deg, velocity_dps) at time *t*.

        Values are clamped to the boundary when t is outside [0, T].
        Velocity unit is degrees-per-second (°/s).
        """
        if t <= 0.0:
            return (self.p0, 0.0)
        if t >= self.T:
            return (self.p1, 0.0)

        t2 = t * t
        t3 = t2 * t
        t4 = t3 * t
        t5 = t4 * t

        pos = self.p0 + self.a3 * t3 + self.a4 * t4 + self.a5 * t5
        vel = 3.0 * self.a3 * t2 + 4.0 * self.a4 * t3 + 5.0 * self.a5 * t4

        return (pos, vel)
