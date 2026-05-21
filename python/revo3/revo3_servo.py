"""
Stark Revo3 - High-Frequency Real-Time Servo Control Example

This example demonstrates how to command a Revo3 hand inside a high-frequency (100Hz)
real-time control loop with an active first-order low-pass filter (LPF) to eliminate
mechanical jitter and command spikes.

Usage:
    python revo3_servo.py
    python revo3_servo.py --port /dev/ttyUSB0
"""

import asyncio
import sys
import argparse
import time
import math
from revo3_utils import *


async def main(port_name=None):
    """Main function: Initialize Revo3 and execute real-time servo loop"""
    (client, slave_id) = await open_modbus_revo3(port_name=port_name)

    # 1. Configure Servo Filtering
    # Mode options: 0 (None), 1 (First-order LPF), 2 (Second-order Critically Damped)
    # Let's enable Second-order Critically Damped filter for ultra-smooth position and velocity tracking.
    await client.revo3_set_servo_filter_mode(2)  # 2: SecondOrderCriticallyDamped
    await client.revo3_set_servo_damping_omega(25.0)  # Natural frequency (omega_n) in rad/s. Higher = faster response.

    current_mode = await client.revo3_get_servo_filter_mode()
    current_omega = await client.revo3_get_servo_damping_omega()
    current_alpha = await client.revo3_get_servo_lpf_alpha()
    logger.info(f"Servo Filter configured: Mode={current_mode} (2=SecondOrder), Omega={current_omega} rad/s (Fall-back LPF Alpha={current_alpha})")

    # 2. Clear initial errors if any
    logger.info("Clearing motor errors...")
    await client.revo3_clear_motor_errors(slave_id)
    await asyncio.sleep(0.2)

    # 3. Define target parameters
    frequency = 0.5  # Hz
    dt = 0.01        # 100Hz (10ms control cycle)
    loop_duration_secs = 8
    total_steps = int(loop_duration_secs / dt)

    logger.info(f"Starting 100Hz real-time servo control loop for {loop_duration_secs} seconds...")
    t = 0.0

    for step in range(total_steps):
        start_time = time.perf_counter()

        # Generate sinusoidal positions (oscillating between 0 and 40 degrees)
        # and matching derivatives (velocities) in RPM
        angle = 20.0 + 20.0 * math.sin(2.0 * math.pi * frequency * t)

        # speed_deg_sec = 20.0 * 2pi * f * cos(2pi * f * t)
        # Since 1 RPM = 6 deg/sec, divide by 6.0 to get target velocity in RPM
        speed_deg_sec = 20.0 * 2.0 * math.pi * frequency * math.cos(2.0 * math.pi * frequency * t)
        speed_rpm = speed_deg_sec / 6.0

        target_positions = [angle] * REVO3_MOTOR_COUNT
        target_velocities = [speed_rpm] * REVO3_MOTOR_COUNT

        # Single-write, non-retry, non-blocking asynchronous servo command.
        # Extremely fast and guarantees no accumulation of command queues.
        try:
            await client.revo3_servo_hand(slave_id, target_positions, target_velocities)
        except Exception as e:
            logger.warning(f"Servo loop write failed at step {step}: {e}")

        # Dynamic latency monitor
        elapsed = time.perf_counter() - start_time
        if step % 100 == 0:
            logger.info(
                f"[Step {step:>4}] Time={t:.2f}s | Target Angle={angle:.1f}° | "
                f"Target Speed={speed_rpm:.1f} RPM | Latency={elapsed * 1000.0:.2f}ms"
            )

        # Precise interval timing
        sleep_dur = max(0.0, dt - elapsed)
        await asyncio.sleep(sleep_dur)
        t += dt

    logger.info("Servo loop complete. Resetting hand gently to zero positions...")
    zero_positions = [0.0] * REVO3_MOTOR_COUNT
    zero_velocities = [0.0] * REVO3_MOTOR_COUNT
    # Best Practice: To prevent high-frequency jitter at target/rest positions
    # due to derivative measurement noise, set Kd = 0.0 during static holding.
    try:
        await client.revo3_servo_hand_with_gains(
            slave_id, zero_positions, zero_velocities, 1.0, 0.0
        )
    except Exception as e:
        logger.warning(f"Failed to reset hand: {e}")
    await asyncio.sleep(0.5)

    # Cleanup
    libstark.modbus_close(client)
    logger.info("Done. Closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Revo3 Servo Control Example")
    parser.add_argument("--port", "-p", type=str, default=None, help="Serial port name")
    args = parser.parse_args()

    try:
        asyncio.run(main(port_name=args.port))
    except KeyboardInterrupt:
        logger.info("User interrupted")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)
