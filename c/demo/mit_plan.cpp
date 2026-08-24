#include <revo3/revo3.hpp>

#include "../common/revo3_mit_plan.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include <csignal>

namespace {

volatile std::sig_atomic_t g_running = 1;

void signal_handler(int) {
  g_running = 0;
}

constexpr std::size_t kJointCount = 21;
constexpr std::array<std::size_t, 6> kTargetJoints = {1, 5, 9, 13, 16, 20};
constexpr int kSegmentDurationMs = 800;
constexpr double kSegmentDurationSeconds = kSegmentDurationMs / 1000.0;
constexpr double kQuinticPeakRateFactor = 1.875;

void print_usage(const char *program) {
  std::printf(
      "Usage: %s [PORT] [--port PORT] [--slave-id ID] --run\n",
      program);
}

struct ProgramOptions {
  bool run = false;
  bool help = false;
  revo3::DiscoveryOptions discovery;
};

ProgramOptions parse_options(int argc, char **argv) {
  ProgramOptions options;
  for (int index = 1; index < argc; ++index) {
    if (std::strcmp(argv[index], "--run") == 0) {
      options.run = true;
    } else if (std::strcmp(argv[index], "--help") == 0 ||
               std::strcmp(argv[index], "-h") == 0) {
      options.help = true;
    } else if (std::strcmp(argv[index], "--port") == 0 && index + 1 < argc) {
      options.discovery.port = argv[++index];
    } else if (std::strcmp(argv[index], "--slave-id") == 0 &&
               index + 1 < argc) {
      const auto value = std::stoul(argv[++index], nullptr, 0);
      if (value > 247) {
        throw std::invalid_argument("slave ID must be in the range 0..247");
      }
      options.discovery.slave_id = static_cast<std::uint8_t>(value);
    } else if (argv[index][0] == '-') {
      throw std::invalid_argument(std::string("unknown or incomplete option: ") +
                                  argv[index]);
    } else if (options.discovery.port.empty()) {
      options.discovery.port = argv[index];
    } else {
      throw std::invalid_argument(std::string("unexpected positional argument: ") +
                                  argv[index]);
    }
  }
  return options;
}

std::size_t run_plan(revo3::Hand &hand, revo3::ServoSession &session,
                     const std::vector<float> &start,
                     const std::vector<float> &target,
                     std::chrono::milliseconds segment_duration) {
  using clock = std::chrono::steady_clock;
  constexpr auto period = std::chrono::milliseconds(10);
  const double segment_duration_seconds =
      std::chrono::duration<double>(segment_duration).count();
  const revo3::examples::RepeatingMitPlan plan(
      0.0, 1.0, segment_duration_seconds, 1);
  const auto started_at = clock::now();
  std::size_t cycle = 0;

  while (g_running) {
    const double elapsed =
        std::chrono::duration<double>(clock::now() - started_at).count();
    const auto sample = plan.sample(elapsed);

    auto positions = start;
    std::vector<float> velocities(kJointCount, 0.0f);
    std::vector<float> kp(kJointCount, 3.0f);
    std::vector<float> kd(kJointCount, 0.3f);
    std::vector<float> feedforward_current_ma(kJointCount, 0.0f);
    for (const auto joint : kTargetJoints) {
      const double distance = target[joint] - start[joint];
      positions[joint] =
          static_cast<float>(start[joint] + distance * sample.position);
      velocities[joint] = static_cast<float>(
          distance * sample.velocity_per_second / 6.0);
    }
    session.send_mit(positions, velocities, kp, kd, feedforward_current_ma);
    ++cycle;

    if (cycle % 100 == 0 || sample.finished) {
      const auto state = hand.state().snapshot();
      std::printf("cycle=%zu", cycle);
      for (const auto joint : kTargetJoints) {
        std::printf(" J%zu=%.2f degree", joint,
                    state.motors.positions_deg[joint]);
      }
      std::printf("\n");
    }
    if (sample.finished) {
      return cycle;
    }
    std::this_thread::sleep_until(started_at + cycle * period);
  }
  return cycle;
}

}  // namespace

int main(int argc, char **argv) {
  std::signal(SIGINT, signal_handler);
  try {
    const auto options = parse_options(argc, argv);
    if (options.help) {
      print_usage(argv[0]);
      return 0;
    }
    if (!options.run) {
      std::fprintf(stderr,
                   "Pass --run after checking the work area and independent "
                   "stop path\n");
      return 2;
    }

    std::printf("=== Revo3 C++ Manager MIT Plan Demo ===\n");
    revo3::Manager manager;
    auto hand = manager.connect_auto(options.discovery);
    const auto layout = hand.joint_layout();
    if (!layout || layout->joint_count != kJointCount) {
      throw std::runtime_error("This example requires a 21-joint Revo3 hand");
    }

    const auto state = hand.state().snapshot();
    const auto config = hand.config().snapshot();
    std::vector<float> initial(state.motors.positions_deg,
                               state.motors.positions_deg + kJointCount);
    auto target = initial;
    for (const auto joint : kTargetJoints) {
      const float minimum = config.joint_min_position_deg[joint];
      const float maximum = config.joint_max_position_deg[joint];
      if (!std::isfinite(minimum) || !std::isfinite(maximum) ||
          minimum >= maximum) {
        throw std::runtime_error("Invalid configured position limits for J" +
                                 std::to_string(joint));
      }
      if (initial[joint] < minimum || initial[joint] > maximum) {
        throw std::runtime_error(
            "Initial feedback is outside the configured position range for J" +
            std::to_string(joint));
      }
      target[joint] = minimum + 0.5f * (maximum - minimum);
      const double distance = target[joint] - initial[joint];
      const double minimum_speed = config.joint_min_speed_rpm[joint];
      const double maximum_speed = config.joint_max_speed_rpm[joint];
      const double allowed_speed =
          distance >= 0.0 || minimum_speed >= 0.0
              ? maximum_speed
              : std::abs(minimum_speed);
      const double peak_speed = kQuinticPeakRateFactor * std::abs(distance) /
                                kSegmentDurationSeconds / 6.0;
      if (!std::isfinite(allowed_speed) || allowed_speed <= 0.0) {
        throw std::runtime_error("Invalid configured speed limit for J" +
                                 std::to_string(joint));
      }
      if (peak_speed > allowed_speed) {
        const double minimum_duration =
            kQuinticPeakRateFactor * std::abs(distance) / allowed_speed / 6.0;
        throw std::runtime_error(
            "Configured speed limit for J" + std::to_string(joint) +
            " requires duration >= " + std::to_string(minimum_duration) +
            "s");
      }
      std::printf("J%zu: initial=%.2f degree, target=%.2f degree, "
                  "peak_velocity=%.2f/%.2f rpm\n",
                  joint, initial[joint], target[joint], peak_speed,
                  allowed_speed);
    }

    std::printf("Connected! Executing 5-finger MIT trajectory to the 50%% configured range point (800ms outbound + 800ms return)...\n");
    auto session = hand.motion().open_servo(std::chrono::milliseconds(100));
    const std::vector<float> zeros(kJointCount, 0.0f);
    const auto clear_gains = [&]() {
      session.send_mit(initial, zeros, zeros, zeros, zeros);
    };
    const auto started_at = std::chrono::steady_clock::now();
    std::size_t command_count = 0;
    double motion_elapsed = 0.0;
    try {
      command_count =
          run_plan(hand, session, initial, target,
                   std::chrono::milliseconds(kSegmentDurationMs));
      motion_elapsed = std::chrono::duration<double>(
                           std::chrono::steady_clock::now() - started_at)
                           .count();
      clear_gains();
    } catch (...) {
      try {
        clear_gains();
      } catch (const std::exception &cleanup_error) {
        std::fprintf(stderr, "Failed to clear MIT gains: %s\n",
                     cleanup_error.what());
      }
      session.close();
      throw;
    }
    session.close();
    hand.close();
    manager.close();
    std::printf("MIT rate: %.1f Hz actual, 100 Hz requested\n",
                command_count / motion_elapsed);
    if (!g_running) {
      std::fprintf(stderr, "MIT plan interrupted after clearing gains.\n");
      return 130;
    }
    std::printf("MIT plan executed successfully.\n");
    return 0;
  } catch (const std::invalid_argument &error) {
    std::fprintf(stderr, "Invalid argument: %s\n", error.what());
    print_usage(argv[0]);
    return 2;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Error: %s\n", error.what());
    return 1;
  }
}
