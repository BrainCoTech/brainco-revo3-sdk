"""Shared helpers for control plus DataCollector examples."""

from dataclasses import dataclass


OBSERVED_JOINTS = ((0, "Pinky"), (13, "Index"), (16, "Thumb"))


@dataclass(frozen=True)
class CollectorRates:
    idle_hz: int = 60
    control_hz: int = 10

    def __post_init__(self) -> None:
        if self.idle_hz <= 0:
            raise ValueError("idle_hz must be positive")
        if self.control_hz < 0:
            raise ValueError("control_hz must be non-negative")
        if self.control_hz > self.idle_hz:
            raise ValueError("control_hz must not exceed idle_hz")


def observed_joint_summary(status) -> str:
    return " ".join(
        (
            f"J{joint}({name})={status.positions[joint]:.2f}deg/"
            f"{status.velocities[joint]:.2f}rpm/"
            f"{status.currents[joint]:.2f}mA/"
            f"0x{status.statuses[joint]:04X}"
        )
        for joint, name in OBSERVED_JOINTS
    )
