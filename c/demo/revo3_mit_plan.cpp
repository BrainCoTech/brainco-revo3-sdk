#include "../common/revo3_common.h"
#include "../common/revo3_mit_plan.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <exception>
#include <string>
#include <thread>
#include <vector>

namespace {

struct FingerSpec {
  const char *name;
  std::vector<std::uint16_t> joints;
};

const std::array<FingerSpec, 6> kFingerSpecs = {{
    {"Pinky", {1}},
    {"Ring", {5}},
    {"Middle", {9}},
    {"Index", {13}},
    {"Thumb Rot", {16}},
    {"Thumb Flex", {20}},
}};

const std::vector<std::uint16_t> kFullHandJoints = {1, 5, 9, 13, 16, 20};

struct ObservedJoint {
  std::uint16_t index;
  const char *name;
};

constexpr std::array<ObservedJoint, 6> kObservedJoints = {{
    ObservedJoint{1, "Pinky"},
    ObservedJoint{5, "Ring"},
    ObservedJoint{9, "Middle"},
    ObservedJoint{13, "Index"},
    ObservedJoint{16, "ThumbRot"},
    ObservedJoint{20, "ThumbFlex"},
}};

struct Args {
  int joint = -1; // -1 means default full-hand + sequential fingers
  double target_position_deg = 80.0;
  double segment_duration_seconds = 0.8;
  std::size_t repeat_count = 1;
  unsigned int frequency_hz = 100;
  float kp = 3.0f;
  float kd = 0.3f;
};

volatile std::sig_atomic_t running = 1;

void stop(int) { running = 0; }

Args parse_args(int argc, char **argv) {
  Args args;
  for (int i = 1; i < argc; ++i) {
    const std::string option = argv[i];
    if (option == "--joint" && i + 1 < argc) {
      args.joint = std::stoi(argv[++i]);
    } else if (option == "--target" && i + 1 < argc) {
      args.target_position_deg = std::stod(argv[++i]);
    } else if (option == "--duration" && i + 1 < argc) {
      args.segment_duration_seconds = std::stod(argv[++i]);
    } else if (option == "--repeat" && i + 1 < argc) {
      args.repeat_count = std::stoul(argv[++i], nullptr, 0);
    } else if (option == "--frequency" && i + 1 < argc) {
      args.frequency_hz = std::stoul(argv[++i], nullptr, 0);
    } else if (option == "--kp" && i + 1 < argc) {
      args.kp = std::stof(argv[++i]);
    } else if (option == "--kd" && i + 1 < argc) {
      args.kd = std::stof(argv[++i]);
    }
  }
  return args;
}

void clear_mit_gains(const Revo3Context &ctx, const std::vector<std::uint16_t> &joints) {
  for (std::uint16_t joint : joints) {
    revo3_joint_mit_control(ctx.handle, ctx.slave_id, joint, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f);
  }
}

void print_observed_summary(const CRevo3MotorStatusData *status) {
  for (std::size_t i = 0; i < kObservedJoints.size(); ++i) {
    const auto observed = kObservedJoints[i];
    std::printf("%sJ%u(%s)=%.2fdeg/%.2frpm/%.2fmA/0x%04X",
                i == 0 ? "" : " ", observed.index, observed.name,
                status->positions[observed.index],
                status->velocities[observed.index],
                status->currents[observed.index],
                status->statuses[observed.index]);
  }
}

bool run_plan_group(const Revo3Context &ctx, const char *group_name,
                    const std::vector<std::uint16_t> &joints, const Args &args) {
  CRevo3MotorStatusData *initial = revo3_get_motor_status_data(ctx.handle, ctx.slave_id);
  if (initial == nullptr) {
    std::fprintf(stderr, "Failed to read initial motor status for [%s]\n", group_name);
    return false;
  }

  std::vector<double> start_positions;
  std::vector<revo3::examples::RepeatingMitPlan> plans;
  for (std::uint16_t joint : joints) {
    const double start_pos = initial->positions[joint];
    start_positions.push_back(start_pos);
    const double joint_target = (joint == 16) ? std::min(args.target_position_deg, 50.0) : args.target_position_deg;
    plans.emplace_back(start_pos, joint_target, args.segment_duration_seconds, args.repeat_count);
  }
  free_revo3_motor_status_data(initial);

  std::printf("MIT quintic plan [%s] joints:", group_name);
  for (std::uint16_t j : joints) std::printf(" %u", j);
  std::printf(": target %.2f deg, %.2fs/segment, %zu repeats, %u Hz\n",
              args.target_position_deg, args.segment_duration_seconds, args.repeat_count, args.frequency_hz);

  const auto period = std::chrono::nanoseconds(1'000'000'000ULL / static_cast<std::uint64_t>(args.frequency_hz));
  const auto start = std::chrono::steady_clock::now();
  auto next_tick = start;
  std::uint64_t cycle = 0;

  while (running) {
    const double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();

    bool all_finished = true;
    bool returning = false;
    std::size_t repeat_idx = 0;

    for (std::size_t i = 0; i < joints.size(); ++i) {
      const auto sample = plans[i].sample(elapsed);
      if (!sample.finished) all_finished = false;
      returning = sample.returning;
      repeat_idx = sample.cycle_index;

      const float target_velocity_rpm = static_cast<float>(sample.velocity_per_second / 6.0);
      revo3_joint_mit_control(ctx.handle, ctx.slave_id, joints[i], args.kp, args.kd,
                              static_cast<float>(sample.position), target_velocity_rpm, 0.0f);
    }

    CRevo3MotorStatusData *status = revo3_get_motor_status_data(ctx.handle, ctx.slave_id);
    if (status != nullptr) {
      if (cycle % args.frequency_hz == 0 || all_finished) {
        std::printf("cycle=%llu phase=%s repeat=%zu group=[%s] observed=",
                    static_cast<unsigned long long>(cycle),
                    returning ? "return" : "outbound", repeat_idx + 1, group_name);
        print_observed_summary(status);
        std::printf("\n");
      }
      free_revo3_motor_status_data(status);
    }

    if (all_finished) break;

    ++cycle;
    next_tick += period;
    std::this_thread::sleep_until(next_tick);
  }

  clear_mit_gains(ctx, joints);
  if (!running) {
    std::printf("MIT plan interrupted by user during [%s]\n", group_name);
    return false;
  }
  return true;
}

} // namespace

int main(int argc, char **argv) {
  Args args;
  try {
    args = parse_args(argc, argv);
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Invalid MIT plan argument: %s\n", error.what());
    return 2;
  }
  if ((args.joint >= 21) || args.frequency_hz == 0 || args.frequency_hz > 10000 ||
      args.repeat_count == 0 || args.segment_duration_seconds <= 0.0 ||
      !std::isfinite(args.target_position_deg) ||
      !std::isfinite(args.segment_duration_seconds) || !std::isfinite(args.kp) ||
      !std::isfinite(args.kd) || args.kp < 0.0f || args.kp > 10.0f ||
      args.kd < 0.0f || args.kd > 10.0f) {
    std::fprintf(stderr, "Invalid MIT plan configuration\n");
    return 2;
  }

  Revo3Context ctx;
  if (!revo3_init_from_args(ctx, argc, argv)) {
    return 1;
  }

  std::signal(SIGINT, stop);
  std::signal(SIGTERM, stop);

  if (args.joint >= 0) {
    std::printf("Executing single joint J%d MIT plan\n", args.joint);
    run_plan_group(ctx, ("Joint " + std::to_string(args.joint)).c_str(), {static_cast<std::uint16_t>(args.joint)}, args);
  } else {
    std::printf("=== Phase 1: Full Hand Quintic MIT Plan ===\n");
    bool completed = run_plan_group(ctx, "Full Hand", kFullHandJoints, args);
    if (completed) {
      std::printf("=== Phase 2: Sequential Individual Finger MIT Plans ===\n");
      for (const auto &finger : kFingerSpecs) {
        std::this_thread::sleep_for(std::chrono::milliseconds(300));
        if (!run_plan_group(ctx, finger.name, finger.joints, args)) {
          break;
        }
      }
    }
  }

  clear_mit_gains(ctx, kFullHandJoints);
  revo3_close(ctx);
  std::printf("MIT plan finished; all gains were cleared.\n");
  return 0;
}

