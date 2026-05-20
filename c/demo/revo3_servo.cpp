#include "../common/revo3_common.h"
#include <cmath>
#include <chrono>
#include <cstdio>
#include <vector>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

int main(int argc, char **argv) {
  Revo3Context ctx;
  if (!revo3_init_from_args(ctx, argc, argv)) {
    return 1;
  }

  // 1. Configure Servo Filtering
  // Mode options: 0 (None), 1 (First-order LPF), 2 (Second-order Critically Damped)
  // Let's enable Second-order Critically Damped filter for ultra-smooth position and velocity tracking.
  revo3_set_servo_filter_mode(ctx.handle, 2); // 2: SecondOrderCriticallyDamped
  revo3_set_servo_damping_omega(ctx.handle, 25.0f); // Natural frequency (omega_n) in rad/s. Higher = faster response.

  uint8_t current_mode = revo3_get_servo_filter_mode(ctx.handle);
  float current_omega = revo3_get_servo_damping_omega(ctx.handle);
  float current_alpha = revo3_get_servo_lpf_alpha(ctx.handle);
  std::printf("[INFO] Servo Filter configured: Mode=%d (2=SecondOrder), Omega=%.2f rad/s, (Fall-back LPF Alpha=%.2f)\n",
              current_mode, current_omega, current_alpha);

  // 2. Clear initial errors if any
  std::printf("[INFO] Clearing motor errors...\n");
  revo3_clear_motor_errors(ctx.handle, ctx.slave_id);
  revo3_sleep_ms(200);

  // 3. Define target parameters
  float frequency = 0.5f; // Hz
  float dt = 0.01f;       // 100Hz (10ms control cycle)
  float loop_duration_secs = 8.0f;
  int total_steps = static_cast<int>(loop_duration_secs / dt);

  std::printf("[INFO] Starting 100Hz real-time servo control loop for %.1f seconds...\n", loop_duration_secs);
  float t = 0.0f;

  std::vector<float> target_positions(21);
  std::vector<float> target_velocities(21);

  for (int step = 0; step < total_steps; ++step) {
    auto start_time = std::chrono::high_resolution_clock::now();

    // Generate sinusoidal positions (oscillating between 0 and 40 degrees)
    // and matching derivatives (velocities) in RPM
    float angle = 20.0f + 20.0f * std::sin(2.0f * M_PI * frequency * t);

    // speed_deg_sec = 20.0f * 2pi * f * cos(2pi * f * t)
    // Since 1 RPM = 6 deg/sec, divide by 6.0 to get target velocity in RPM
    float speed_deg_sec = 20.0f * 2.0f * M_PI * frequency * std::cos(2.0f * M_PI * frequency * t);
    float speed_rpm = speed_deg_sec / 6.0f;

    for (int i = 0; i < 21; ++i) {
      target_positions[i] = angle;
      target_velocities[i] = speed_rpm;
    }

    // Single-write, non-retry, non-blocking asynchronous servo command.
    // Extremely fast and guarantees no accumulation of command queues.
    revo3_servo_hand(ctx.handle, ctx.slave_id, target_positions.data(), target_velocities.data());

    // Dynamic latency monitor
    auto elapsed = std::chrono::high_resolution_clock::now() - start_time;
    double elapsed_ms = std::chrono::duration<double, std::milli>(elapsed).count();

    if (step % 100 == 0) {
      std::printf("[Step %4d] Time=%.2fs | Target Angle=%.1f° | Target Speed=%.1f RPM | Latency=%.2fms\n",
                  step, t, angle, speed_rpm, elapsed_ms);
    }

    // Precise interval timing
    double sleep_ms = (dt * 1000.0) - elapsed_ms;
    if (sleep_ms > 0) {
      revo3_sleep_ms(static_cast<int>(sleep_ms));
    }
    t += dt;
  }

  std::printf("[INFO] Servo loop complete. Resetting hand gently to zero positions...\n");
  std::vector<float> zero_positions(21, 0.0f);
  std::vector<float> zero_velocities(21, 0.0f);
  // Best Practice: To prevent high-frequency jitter at target/rest positions
  // due to derivative measurement noise, set Kd = 0.0 during static holding.
  revo3_servo_hand_with_gains(ctx.handle, ctx.slave_id, zero_positions.data(), zero_velocities.data(), 3.0f, 0.0f);
  revo3_sleep_ms(500);

  revo3_close(ctx);
  std::printf("[INFO] Done!\n");
  return 0;
}
