#include <revo3/revo3.hpp>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <thread>
#include <vector>

#include <csignal>
#include <atomic>

namespace {

// Atomic flag to handle SIGINT (Ctrl+C) signal for graceful shutdown
std::atomic<bool> g_running{true};

void signal_handler(int) {
  g_running = false;
}

constexpr std::size_t kJointCount = 21;
constexpr std::array<std::size_t, 6> kTargetJoints = {1, 5, 9, 13, 16, 20};

double quintic_blend(double ratio) {
  return 10.0 * std::pow(ratio, 3) - 15.0 * std::pow(ratio, 4) +
         6.0 * std::pow(ratio, 5);
}

double quintic_blend_rate(double ratio, double duration_seconds) {
  return (30.0 * std::pow(ratio, 2) - 60.0 * std::pow(ratio, 3) +
          30.0 * std::pow(ratio, 4)) /
         duration_seconds;
}

void run_segment(revo3::ServoSession &session,
                 const std::vector<float> &start,
                 const std::vector<float> &target,
                 std::chrono::milliseconds duration) {
  using clock = std::chrono::steady_clock;
  constexpr auto period = std::chrono::milliseconds(10);
  const double duration_seconds =
      std::chrono::duration<double>(duration).count();
  const auto started_at = clock::now();
  std::size_t cycle = 0;

  while (g_running) {
    const double elapsed = std::min(
        std::chrono::duration<double>(clock::now() - started_at).count(),
        duration_seconds);
    const double ratio = elapsed / duration_seconds;
    const double blend = quintic_blend(ratio);
    const double blend_rate = quintic_blend_rate(ratio, duration_seconds);

    auto positions = start;
    std::vector<float> velocities(kJointCount, 0.0f);
    std::vector<float> kp(kJointCount, 3.0f);
    std::vector<float> kd(kJointCount, 0.3f);
    std::vector<float> feedforward_current_ma(kJointCount, 0.0f);
    for (const auto joint : kTargetJoints) {
      const double distance = target[joint] - start[joint];
      positions[joint] = static_cast<float>(start[joint] + distance * blend);
      velocities[joint] = static_cast<float>(distance * blend_rate / 6.0);
    }
    session.send_mit(positions, velocities, kp, kd, feedforward_current_ma);
    if (elapsed >= duration_seconds) {
      return;
    }
    ++cycle;
    std::this_thread::sleep_until(started_at + cycle * period);
  }
}

}  // namespace

int main(int argc, char **argv) {
  std::signal(SIGINT, signal_handler);
  bool run = false;
  revo3::DiscoveryOptions discovery;
  for (int index = 1; index < argc; ++index) {
    if (std::strcmp(argv[index], "--move") == 0 || std::strcmp(argv[index], "--run") == 0) {
      run = true;
    } else {
      discovery.port = argv[index];
    }
  }
  if (!run) {
    std::fprintf(stderr,
                 "Pass --move after checking the work area and independent "
                 "stop path\n");
    return 2;
  }

  try {
    std::printf("=== Revo3 C++ Manager MIT Plan Demo ===\n");
    revo3::Manager manager;
    auto hand = manager.connect_auto(discovery);
    const auto layout = hand.joint_layout();
    if (!layout || layout->joint_count != kJointCount) {
      throw std::runtime_error("This example requires a 21-joint Revo3 hand");
    }

    const auto state = hand.state().snapshot();
    std::vector<float> initial(state.motors.positions_deg,
                               state.motors.positions_deg + kJointCount);
    auto target = initial;
    for (const auto joint : kTargetJoints) {
      target[joint] += 20.0f;
    }

    std::printf("Connected! Executing 5-finger MIT trajectory segment (800ms flex + 800ms extend)...\n");
    auto session = hand.motion().open_servo(std::chrono::milliseconds(100));
    run_segment(session, initial, target, std::chrono::milliseconds(800));
    run_segment(session, target, initial, std::chrono::milliseconds(800));

    const std::vector<float> zeros(kJointCount, 0.0f);
    session.send_mit(initial, zeros, zeros, zeros, zeros);
    session.close();
    hand.close();
    manager.close();
    std::printf("MIT plan executed successfully.\n");
    return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Error: %s\n", error.what());
    return 1;
  }
}
