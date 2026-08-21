#include "revo3_ethercat.hpp"
#include "../../../common/revo3_mit_plan.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

namespace {

constexpr std::uint64_t kNanosecondsPerSecond = 1'000'000'000ULL;
constexpr unsigned int kDefaultFrequencyHz = 1000;
constexpr unsigned int kDefaultPlanAllFrequencyHz = 100;
constexpr unsigned int kDefaultOpTimeoutMs = 9000;
constexpr int kDefaultRealtimePriority = 49;
constexpr std::uint16_t kDefaultPlanAllTargetPosition = 8000;
constexpr std::uint16_t kDefaultPlanAllKp = 300;
constexpr std::uint16_t kDefaultPlanAllKd = 30;
constexpr double kDefaultPlanAllDurationSeconds = 0.8;
constexpr std::size_t kDefaultPlanAllRepeatCount = 1;

struct ObservedJoint {
  std::uint16_t index;
  const char *name;
};

constexpr std::array<ObservedJoint, 3> kObservedJoints = {
    ObservedJoint{0, "Pinky"},
    ObservedJoint{13, "Index"},
    ObservedJoint{16, "Thumb"},
};

struct PlanGroup {
  const char *name;
  std::vector<std::uint16_t> joints;
};

volatile std::sig_atomic_t running = 1;

void stop(int) { running = 0; }

std::uint16_t parse_u16(const char *text) {
  const unsigned long value = std::stoul(text, nullptr, 0);
  if (value > std::numeric_limits<std::uint16_t>::max()) {
    throw std::out_of_range("value exceeds uint16 range");
  }
  return static_cast<std::uint16_t>(value);
}

void usage(const char *program) {
  std::cerr << "Usage: " << program
            << " [slave-position] [--command joint position kp kd]\n"
            << "       [--mit-plan joint position kp kd duration repeat]\n"
            << "       [--mit-plan-all [position kp kd duration repeat]]\n"
            << "       [--frequency hz] [--dc] [--no-touch-pdo] [--op-timeout ms]\n"
            << "       [--realtime [priority]]\n";
}

} // namespace

int main(int argc, char **argv) {
  std::uint16_t slave_position = 0;
  bool command_requested = false;
  bool plan_requested = false;
  bool plan_all_requested = false;
  bool dc_enabled = false;
  bool realtime_enabled = false;
  bool touch_pdo_enabled = true;
  bool frequency_requested = false;
  unsigned int frequency_hz = kDefaultFrequencyHz;
  unsigned int op_timeout_ms = kDefaultOpTimeoutMs;
  int realtime_priority = kDefaultRealtimePriority;
  std::uint16_t joint = 0;
  std::uint16_t target_position = 0;
  std::uint16_t kp = 0;
  std::uint16_t kd = 0;
  double plan_duration_seconds = 2.0;
  std::size_t plan_repeat_count = 1;

  try {
    int arg = 1;
    if (arg < argc && std::string(argv[arg]).find("--") != 0) {
      slave_position = parse_u16(argv[arg++]);
    }
    while (arg < argc) {
      const std::string option = argv[arg++];
      if (option == "--command") {
        if (arg + 3 >= argc) {
          usage(argv[0]);
          return 2;
        }
        joint = parse_u16(argv[arg++]);
        target_position = parse_u16(argv[arg++]);
        kp = parse_u16(argv[arg++]);
        kd = parse_u16(argv[arg++]);
        command_requested = true;
      } else if (option == "--mit-plan") {
        if (arg + 5 >= argc) {
          usage(argv[0]);
          return 2;
        }
        joint = parse_u16(argv[arg++]);
        target_position = parse_u16(argv[arg++]);
        kp = parse_u16(argv[arg++]);
        kd = parse_u16(argv[arg++]);
        plan_duration_seconds = std::stod(argv[arg++]);
        plan_repeat_count = std::stoul(argv[arg++], nullptr, 0);
        plan_requested = true;
      } else if (option == "--mit-plan-all") {
        target_position = kDefaultPlanAllTargetPosition;
        kp = kDefaultPlanAllKp;
        kd = kDefaultPlanAllKd;
        plan_duration_seconds = kDefaultPlanAllDurationSeconds;
        plan_repeat_count = kDefaultPlanAllRepeatCount;
        if (arg < argc && std::string(argv[arg]).find("--") != 0) {
          if (arg + 4 >= argc) {
            usage(argv[0]);
            return 2;
          }
          target_position = parse_u16(argv[arg++]);
          kp = parse_u16(argv[arg++]);
          kd = parse_u16(argv[arg++]);
          plan_duration_seconds = std::stod(argv[arg++]);
          plan_repeat_count = std::stoul(argv[arg++], nullptr, 0);
        }
        plan_all_requested = true;
      } else if (option == "--frequency") {
        if (arg >= argc) {
          usage(argv[0]);
          return 2;
        }
        frequency_hz = parse_u16(argv[arg++]);
        frequency_requested = true;
      } else if (option == "--op-timeout") {
        if (arg >= argc) {
          usage(argv[0]);
          return 2;
        }
        op_timeout_ms = parse_u16(argv[arg++]);
      } else if (option == "--dc") {
        dc_enabled = true;
      } else if (option == "--no-touch-pdo") {
        touch_pdo_enabled = false;
      } else if (option == "--realtime") {
        realtime_enabled = true;
        if (arg < argc && std::string(argv[arg]).find("--") != 0) {
          realtime_priority = parse_u16(argv[arg++]);
        }
      } else {
        usage(argv[0]);
        return 2;
      }
    }
  } catch (const std::exception &error) {
    std::cerr << "Invalid argument: " << error.what() << '\n';
    usage(argv[0]);
    return 2;
  }
  if (joint >= revo3::ethercat::kMotorCount) {
    std::cerr << "Joint must be in the range 0..20\n";
    return 2;
  }
  if (frequency_hz == 0) {
    std::cerr << "Frequency must be greater than zero\n";
    return 2;
  }
  if (plan_all_requested && !frequency_requested) {
    frequency_hz = kDefaultPlanAllFrequencyHz;
  }
  const int motion_mode_count = (command_requested ? 1 : 0) +
                                (plan_requested ? 1 : 0) +
                                (plan_all_requested ? 1 : 0);
  if (motion_mode_count > 1) {
    std::cerr << "--command, --mit-plan, and --mit-plan-all are mutually exclusive\n";
    return 2;
  }
  if ((plan_requested || plan_all_requested) &&
      (plan_duration_seconds <= 0.0 || !std::isfinite(plan_duration_seconds) ||
       plan_repeat_count == 0)) {
    std::cerr << "MIT plan duration and repeat count must be positive\n";
    return 2;
  }

  auto pdo_layout = revo3::ethercat::default_pdo_layout();
  pdo_layout.has_touch_pdo = touch_pdo_enabled;
  revo3::ethercat::Master master(slave_position, 0, pdo_layout);
  if (dc_enabled) {
    revo3::ethercat::DcConfig dc;
    dc.enabled = true;
    dc.sync0_cycle_ns =
        static_cast<std::uint32_t>(kNanosecondsPerSecond / frequency_hz);
    master.configure_dc(dc);
  }
  std::string error;
  if (realtime_enabled &&
      !revo3::ethercat::enable_realtime(realtime_priority, &error)) {
    std::cerr << error << '\n';
    return 1;
  }
  if (!master.initialize(&error) || !master.activate(&error)) {
    std::cerr << error << '\n';
    return 1;
  }
  const std::uint64_t period_ns = kNanosecondsPerSecond / frequency_hz;
  if (!master.wait_for_operational(op_timeout_ms, period_ns, &error)) {
    std::cerr << error << '\n';
    return 1;
  }

  std::signal(SIGINT, stop);
  std::signal(SIGTERM, stop);
  std::cout << "Revo3 EtherCAT PDO loop started for slave " << slave_position
            << ". Press Ctrl+C to stop.\n";
  if (command_requested) {
    std::cout << "Command will be applied after initial feedback: joint=" << joint
              << " position=" << target_position << " Kp=" << kp
              << " Kd=" << kd << '\n';
  }

  std::vector<PlanGroup> plan_groups;
  if (plan_requested) {
    plan_groups.push_back({"Joint", {joint}});
  } else if (plan_all_requested) {
    plan_groups.push_back({"Full Hand", {1, 5, 9, 13, 16, 20}});
    plan_groups.push_back({"Pinky", {1}});
    plan_groups.push_back({"Ring", {5}});
    plan_groups.push_back({"Middle", {9}});
    plan_groups.push_back({"Index", {13}});
    plan_groups.push_back({"Thumb Rot", {16}});
    plan_groups.push_back({"Thumb Flex", {20}});
    joint = plan_groups.front().joints.front();
  }

  std::vector<std::uint16_t> active_joints;
  std::vector<revo3::examples::RepeatingMitPlan> plans;
  std::size_t active_group_index = 0;
  const auto plan_start = std::chrono::steady_clock::now();
  auto group_start = plan_start;
  auto plan_finished_at = std::chrono::steady_clock::time_point{};
  revo3::examples::MitPlanSample plan_sample{};
  if (plan_requested) {
    const std::uint16_t initial_position = master.command().position_raw[joint];
    active_joints = {joint};
    plans.emplace_back(initial_position, target_position, plan_duration_seconds,
                       plan_repeat_count);
    std::cout << "MIT plan: joint=" << joint << " position="
              << initial_position << " -> " << target_position
              << " duration=" << plan_duration_seconds
              << "s/segment repeats=" << plan_repeat_count << " Kp=" << kp
              << " Kd=" << kd << '\n';
  } else if (plan_all_requested) {
    active_joints = plan_groups.front().joints;
    for (const auto active_joint : active_joints) {
      plans.emplace_back(master.command().position_raw[active_joint], target_position,
                         plan_duration_seconds, plan_repeat_count);
    }
    std::cout << "MIT plan all: target=" << target_position
              << " duration=" << plan_duration_seconds
              << "s/segment repeats=" << plan_repeat_count << " Kp=" << kp
              << " Kd=" << kd << '\n';
    std::cout << "MIT plan group: " << plan_groups[active_group_index].name
              << '\n';
  }

  std::uint64_t next_wakeup_ns = revo3::ethercat::monotonic_time_ns();
  std::uint64_t cycles = 0;
  bool command_applied = false;
  while (running) {
    next_wakeup_ns += period_ns;
    revo3::ethercat::sleep_until_monotonic_ns(next_wakeup_ns);
    if (command_requested && master.outputs_initialized() && !command_applied) {
      // EtherCAT PDO raw command scaling:
      // - Target Position: value * 100 in degrees (e.g., 15000 represents 150.0 deg)
      // - Stiffness Kp: value * 100 (e.g., 200 represents Kp=2.0)
      // - Damping Kd: value * 100 (e.g., 25 represents Kd=0.25)
      master.command().position_raw[joint] = target_position;
      master.command().kp_raw[joint] = kp;
      master.command().kd_raw[joint] = kd;
      command_applied = true;
    }
    if (!plans.empty()) {
      const double elapsed = std::chrono::duration<double>(
                                 std::chrono::steady_clock::now() - group_start)
                                 .count();
      bool group_finished = true;
      for (std::size_t i = 0; i < active_joints.size(); ++i) {
        plan_sample = plans[i].sample(elapsed);
        const auto active_joint = active_joints[i];
        master.command().position_raw[active_joint] =
            static_cast<std::uint16_t>(std::clamp(
                std::lround(plan_sample.position), 0L,
                static_cast<long>(std::numeric_limits<std::uint16_t>::max())));
        // Position is centidegrees and velocity is centi-RPM, so divide the
        // trajectory derivative by 6 to convert centidegrees/s to centi-RPM.
        master.command().velocity_raw[active_joint] =
            revo3::ethercat::velocity_rpm_to_raw(
                static_cast<float>(plan_sample.velocity_per_second / 600.0));
        master.command().kp_raw[active_joint] = kp;
        master.command().kd_raw[active_joint] = kd;
        group_finished = group_finished && plan_sample.finished;
      }
      if (group_finished) {
        for (const auto active_joint : active_joints) {
          master.command().velocity_raw[active_joint] = 0;
          master.command().kp_raw[active_joint] = 0;
          master.command().kd_raw[active_joint] = 0;
        }
        if (plan_all_requested) {
          active_group_index = (active_group_index + 1) % plan_groups.size();
          active_joints = plan_groups[active_group_index].joints;
          plans.clear();
          for (const auto active_joint : active_joints) {
            plans.emplace_back(master.feedback().position_raw[active_joint],
                               target_position, plan_duration_seconds,
                               plan_repeat_count);
          }
          joint = active_joints.front();
          group_start = std::chrono::steady_clock::now();
          std::cout << "MIT plan group: "
                    << plan_groups[active_group_index].name << '\n';
        } else if (plan_finished_at ==
                   std::chrono::steady_clock::time_point{}) {
          plan_finished_at = std::chrono::steady_clock::now();
        }
      }
    }
    if (!master.cycle(next_wakeup_ns)) {
      std::cerr << "EtherCAT cycle failed\n";
      break;
    }
    if (++cycles % frequency_hz == 0) {
      const auto &feedback = master.feedback();
      const auto &touch = master.touch_packet();
      // Raw feedback scaling:
      // - pos: actual angle in degrees * 100 (e.g., 9000 for 90.0 deg)
      // - vel: actual velocity in RPM * 100 (e.g., 5000 for 50.0 RPM)
      // - cur: current in mA (no scaling, direct mA)
      // - err: 32-bit motor fault code bitmask (0 = normal)
      std::cout << "J" << joint << " target_raw="
                << master.command().position_raw[joint]
                << " pos_deg="
                << revo3::ethercat::position_raw_to_deg(
                       feedback.position_raw[joint])
                << " vel_rpm="
                << revo3::ethercat::velocity_raw_to_rpm(
                       feedback.velocity_raw[joint])
                << " cur_ma="
                << revo3::ethercat::current_raw_to_ma(
                       feedback.current_raw[joint])
                << " error_raw=0x"
                << std::hex << feedback.error_raw[joint] << std::dec
                << " phase="
                << (!plans.empty()
                        ? (plan_sample.returning ? "return" : "outbound")
                        : "hold")
                << " repeat=" << (!plans.empty() ? plan_sample.cycle_index : 0)
                << " group="
                << (!plan_groups.empty() ? plan_groups[active_group_index].name
                                         : "-")
                << " observed_deg_rpm_ma_error=";
      for (std::size_t i = 0; i < kObservedJoints.size(); ++i) {
        const auto observed = kObservedJoints[i];
        std::cout << (i == 0 ? "" : " ") << "J" << observed.index << "("
                  << observed.name << ")="
                  << revo3::ethercat::position_raw_to_deg(
                         feedback.position_raw[observed.index])
                  << "/"
                  << revo3::ethercat::velocity_raw_to_rpm(
                         feedback.velocity_raw[observed.index])
                  << "/"
                  << revo3::ethercat::current_raw_to_ma(
                         feedback.current_raw[observed.index])
                  << "/0x" << std::hex
                  << feedback.error_raw[observed.index] << std::dec;
      }
      std::cout
                << " touch_packet="
                << touch.index << " touch_length=" << touch.length << '\n';
    }
    if (plan_finished_at != std::chrono::steady_clock::time_point{} &&
        std::chrono::steady_clock::now() - plan_finished_at >=
            std::chrono::milliseconds(100)) {
      std::cout << "MIT plan completed; clearing joint gains.\n";
      break;
    }
  }
  if (command_requested || plan_requested || plan_all_requested) {
    if (active_joints.empty()) {
      active_joints = {joint};
    }
    for (const auto active_joint : active_joints) {
      master.command().velocity_raw[active_joint] = 0;
      master.command().kp_raw[active_joint] = 0;
      master.command().kd_raw[active_joint] = 0;
    }
    master.cycle(revo3::ethercat::monotonic_time_ns());
  }
  master.shutdown();
  return 0;
}
