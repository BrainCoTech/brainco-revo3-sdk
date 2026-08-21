#include "revo3_ethercat.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cctype>
#include <cstring>
#include <ecrt.h>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <sstream>
#include <string>
#include <vector>

namespace {

using Clock = std::chrono::steady_clock;
constexpr double kPi = 3.14159265358979323846;
constexpr std::uint64_t kNanosecondsPerSecond = 1'000'000'000ULL;
constexpr double kMicrosecondsPerMillisecond = 1000.0;
constexpr unsigned int kDefaultFrequencyHz = 1000;
constexpr unsigned int kDefaultOpTimeoutMs = 9000;
constexpr int kDefaultRealtimePriority = 49;
constexpr std::size_t kSdoStringCapacity = 64;

struct Args {
  std::string scenario = "motor";
  std::string read_strategy = "full-state";
  std::string control_strategy = "none";
  double duration_seconds = 10.0;
  double sine_hz = 0.5;
  int motor_id = 3;
  int amplitude = 100;
  std::uint16_t kp = 100;
  std::uint16_t kd = 20;
  std::uint16_t slave_position = 0;
  unsigned int frequency_hz = kDefaultFrequencyHz;
  unsigned int op_timeout_ms = kDefaultOpTimeoutMs;
  std::uint16_t dc_assign_activate = revo3::ethercat::kDefaultDcAssignActivate;
  std::int32_t sync0_shift_ns = 0;
  std::uint32_t sync1_cycle_ns = 0;
  std::int32_t sync1_shift_ns = 0;
  unsigned int op_warmup_ms = 0;
  bool dc_enabled = false;
  bool realtime_enabled = false;
  bool touch_pdo_enabled = true;
  int realtime_priority = kDefaultRealtimePriority;
  bool detect_only = false;
};

struct Stats {
  std::uint64_t loops = 0;
  std::uint64_t motor_reads = 0;
  std::uint64_t touch_reads = 0;
  std::uint64_t control_writes = 0;
  std::uint64_t errors = 0;
  double latency_sum_us = 0.0;
  double latency_min_us = 0.0;
  double latency_max_us = 0.0;
  std::vector<double> latencies_us;
  std::uint64_t sample = 0;

  void record(double latency_us, bool keep_samples) {
    ++loops;
    latency_sum_us += latency_us;
    latency_min_us = latency_min_us == 0.0
                         ? latency_us
                         : std::min(latency_min_us, latency_us);
    latency_max_us = std::max(latency_max_us, latency_us);
    if (keep_samples) {
      latencies_us.push_back(latency_us);
    }
  }

  double average_ms() const {
    return loops == 0 ? 0.0
                      : latency_sum_us / loops / kMicrosecondsPerMillisecond;
  }
};

void usage(const char *program) {
  std::cerr
      << "Usage: " << program << " [options]\n"
      << "  --scenario motor|motor-touch|control-only|closed-loop\n"
      << "  --read none|single-status|multi-status|all-positions|split-state|"
         "full-state|touch-summary|touch-matrix|full-state-touch-summary|"
         "full-state-touch-matrix\n"
      << "  --control none|single-position|all-positions|single-mit\n"
      << "  --duration seconds --motor 0..20 --amplitude raw-units\n"
      << "  --sine-hz hz --kp value --kd value\n"
      << "  --slave-position position --frequency hz --op-timeout ms\n"
      << "  --dc --dc-assign value --sync0-shift-ns ns\n"
      << "  --sync1-cycle-ns ns --sync1-shift-ns ns --op-warmup-ms ms\n"
      << "  --no-touch-pdo --realtime [priority] --detect-only\n";
}

bool next_value(int argc, char **argv, int *index, const char **value) {
  if (*index + 1 >= argc) {
    std::cerr << "Missing value for " << argv[*index] << '\n';
    return false;
  }
  *value = argv[++*index];
  return true;
}

template <typename T>
bool parse_unsigned(const char *text, T *result) {
  try {
    const unsigned long long value = std::stoull(text, nullptr, 0);
    if (value > std::numeric_limits<T>::max()) {
      return false;
    }
    *result = static_cast<T>(value);
    return true;
  } catch (const std::exception &) {
    return false;
  }
}

template <typename T>
bool parse_signed(const char *text, T *result) {
  try {
    const long long value = std::stoll(text, nullptr, 0);
    if (value < std::numeric_limits<T>::min() ||
        value > std::numeric_limits<T>::max()) {
      return false;
    }
    *result = static_cast<T>(value);
    return true;
  } catch (const std::exception &) {
    return false;
  }
}

bool is_read_strategy(const std::string &value) {
  static const std::array<const char *, 10> values = {
      "none",          "single-status", "multi-status",
      "all-positions", "split-state",   "full-state",
      "touch-summary", "touch-matrix",  "full-state-touch-summary",
      "full-state-touch-matrix"};
  return std::find(values.begin(), values.end(), value) != values.end();
}

bool parse_args(int argc, char **argv, Args *args) {
  for (int i = 1; i < argc; ++i) {
    const char *value = nullptr;
    const std::string option = argv[i];
    if (option == "--help" || option == "-h") {
      usage(argv[0]);
      return false;
    }
    if (option == "--detect-only") {
      args->detect_only = true;
      continue;
    }
    if (option == "--dc") {
      args->dc_enabled = true;
      continue;
    }
    if (option == "--no-touch-pdo") {
      args->touch_pdo_enabled = false;
      continue;
    }
    if (option == "--realtime") {
      args->realtime_enabled = true;
      if (i + 1 < argc && std::string(argv[i + 1]).find("--") != 0) {
        if (!parse_unsigned(argv[++i], &args->realtime_priority)) {
          return false;
        }
      }
      continue;
    }
    if (!next_value(argc, argv, &i, &value)) {
      return false;
    }
    try {
      if (option == "--scenario") {
        args->scenario = value;
      } else if (option == "--read") {
        args->read_strategy = value;
      } else if (option == "--control") {
        args->control_strategy = value;
      } else if (option == "--duration") {
        args->duration_seconds = std::stod(value);
      } else if (option == "--sine-hz") {
        args->sine_hz = std::stod(value);
      } else if (option == "--motor") {
        args->motor_id = std::stoi(value);
      } else if (option == "--amplitude") {
        args->amplitude = std::stoi(value);
      } else if (option == "--kp") {
        if (!parse_unsigned(value, &args->kp)) return false;
      } else if (option == "--kd") {
        if (!parse_unsigned(value, &args->kd)) return false;
      } else if (option == "--slave-position") {
        if (!parse_unsigned(value, &args->slave_position)) return false;
      } else if (option == "--frequency") {
        if (!parse_unsigned(value, &args->frequency_hz)) return false;
      } else if (option == "--op-timeout") {
        if (!parse_unsigned(value, &args->op_timeout_ms)) return false;
      } else if (option == "--dc-assign") {
        if (!parse_unsigned(value, &args->dc_assign_activate)) return false;
      } else if (option == "--sync0-shift-ns") {
        if (!parse_signed(value, &args->sync0_shift_ns)) return false;
      } else if (option == "--sync1-cycle-ns") {
        if (!parse_unsigned(value, &args->sync1_cycle_ns)) return false;
      } else if (option == "--sync1-shift-ns") {
        if (!parse_signed(value, &args->sync1_shift_ns)) return false;
      } else if (option == "--op-warmup-ms") {
        if (!parse_unsigned(value, &args->op_warmup_ms)) return false;
      } else {
        std::cerr << "Unknown argument: " << option << '\n';
        return false;
      }
    } catch (const std::exception &) {
      std::cerr << "Invalid value for " << option << ": " << value << '\n';
      return false;
    }
  }

  if (args->scenario == "closed-loop" && args->control_strategy == "none") {
    args->control_strategy = "single-position";
  }
  const bool scenario_valid =
      args->scenario == "motor" || args->scenario == "motor-touch" ||
      args->scenario == "control-only" || args->scenario == "closed-loop";
  const bool control_valid =
      args->control_strategy == "none" ||
      args->control_strategy == "single-position" ||
      args->control_strategy == "all-positions" ||
      args->control_strategy == "single-mit";
  if (!scenario_valid || !is_read_strategy(args->read_strategy) ||
      !control_valid || args->motor_id < 0 ||
      args->motor_id >= static_cast<int>(revo3::ethercat::kMotorCount) ||
      args->duration_seconds <= 0.0 || !std::isfinite(args->duration_seconds) ||
      args->sine_hz < 0.0 || !std::isfinite(args->sine_hz) ||
      args->amplitude < 0 || args->frequency_hz == 0) {
    std::cerr << "Invalid benchmark configuration\n";
    return false;
  }
  return true;
}

bool read_sdo_u16(revo3::ethercat::Master *master, std::uint16_t index,
                  std::uint16_t *value, std::uint8_t subindex = 0) {
  std::array<std::uint8_t, 2> data{};
  std::size_t size = 0;
  if (!master->read_sdo(index, subindex, data.data(), data.size(), &size) ||
      size != data.size()) {
    return false;
  }
  *value = EC_READ_U16(data.data());
  return true;
}

std::string read_sdo_string(revo3::ethercat::Master *master,
                            std::uint16_t index) {
  std::array<char, kSdoStringCapacity> data{};
  std::size_t size = 0;
  if (!master->read_sdo(index, 0, data.data(), data.size() - 1, &size)) {
    return "Unknown";
  }
  data[std::min(size, data.size() - 1)] = '\0';
  std::string value;
  value.reserve(size);
  for (std::size_t i = 0; i < size && i < data.size(); ++i) {
    const auto ch = static_cast<unsigned char>(data[i]);
    if (ch == '\0') {
      break;
    }
    if (std::isprint(ch)) {
      value.push_back(static_cast<char>(ch));
    }
  }
  return value.empty() ? "Unknown" : value;
}

std::vector<std::string> read_motor_sdo_strings(
    revo3::ethercat::Master *master) {
  std::vector<std::string> values;
  values.reserve(revo3::ethercat::kMotorCount);
  for (std::size_t motor = 0; motor < revo3::ethercat::kMotorCount; ++motor) {
    values.push_back(read_sdo_string(
        master,
        static_cast<std::uint16_t>(
            revo3::ethercat::kMotorSnObjectIndexBase + motor)));
  }
  return values;
}

std::vector<std::string> read_motor_versions(revo3::ethercat::Master *master) {
  std::vector<std::string> values;
  values.reserve(revo3::ethercat::kMotorCount);
  for (std::size_t motor = 0; motor < revo3::ethercat::kMotorCount; ++motor) {
    std::uint16_t raw = 0;
    if (!read_sdo_u16(master, revo3::ethercat::kMotorVersionObjectIndex, &raw,
                      static_cast<std::uint8_t>(motor + 1))) {
      values.push_back("N/A");
      continue;
    }
    values.push_back(std::to_string(raw >> 8) + "." +
                     std::to_string(raw & 0xFF));
  }
  return values;
}

std::string join_csv(const std::vector<std::string> &values) {
  std::ostringstream stream;
  for (std::size_t i = 0; i < values.size(); ++i) {
    if (i != 0) {
      stream << ", ";
    }
    stream << values[i];
  }
  return stream.str();
}

void apply_control(revo3::ethercat::Master *master, const Args &args,
                   const revo3::ethercat::MotorCommand &base_command,
                   double elapsed_seconds) {
  if (args.control_strategy == "none") {
    return;
  }
  // The sine wave calculations are done in raw units (degrees * 100).
  // E.g., amplitude=100 represents a movement amplitude of 1.0 degree.
  const double phase = 2.0 * kPi * args.sine_hz * elapsed_seconds;
  const int delta = static_cast<int>(std::lround(args.amplitude * std::sin(phase)));
  const auto update_joint = [&](std::size_t motor) {
    const int target = std::clamp(
        static_cast<int>(base_command.position_raw[motor]) + delta, 0,
        static_cast<int>(std::numeric_limits<std::uint16_t>::max()));
    master->command().position_raw[motor] = static_cast<std::uint16_t>(target);
    // Raw gains Kp and Kd are scaled by 100 (e.g. 100 represents Kp=1.0).
    master->command().kp_raw[motor] = args.kp;
    master->command().kd_raw[motor] = args.kd;
  };
  if (args.control_strategy == "all-positions") {
    for (std::size_t motor = 0; motor < revo3::ethercat::kMotorCount;
         ++motor) {
      update_joint(motor);
    }
  } else {
    update_joint(static_cast<std::size_t>(args.motor_id));
  }
}

void consume_feedback(const revo3::ethercat::Master &master, const Args &args,
                      Stats *stats) {
  const auto motor = static_cast<std::size_t>(args.motor_id);
  const auto &feedback = master.feedback();
  const auto &touch = master.touch_packet();
  const bool motor_touch_scenario = args.scenario == "motor-touch";

  if (args.read_strategy == "single-status") {
    stats->sample = feedback.status_raw[motor];
    ++stats->motor_reads;
  } else if (args.read_strategy == "multi-status") {
    stats->sample = feedback.status_raw[motor] + feedback.error_raw[motor];
    ++stats->motor_reads;
  } else if (args.read_strategy == "all-positions") {
    stats->sample = feedback.position_raw[motor];
    ++stats->motor_reads;
  } else if (args.read_strategy == "split-state" ||
             args.read_strategy == "full-state" ||
             args.read_strategy.find("full-state-touch") == 0) {
    stats->sample = feedback.position_raw[motor] + feedback.velocity_raw[motor] +
                    feedback.current_raw[motor] + feedback.error_raw[motor];
    ++stats->motor_reads;
  }

  if (motor_touch_scenario ||
      args.read_strategy.find("touch") != std::string::npos) {
    stats->sample += touch.index + touch.length;
    if (touch.length > 0) {
      stats->sample += touch.data[0];
    }
    ++stats->touch_reads;
  }
}

double percentile(std::vector<double> samples, double fraction) {
  if (samples.empty()) {
    return 0.0;
  }
  std::sort(samples.begin(), samples.end());
  const std::size_t index = static_cast<std::size_t>(
      std::ceil(fraction * static_cast<double>(samples.size())) - 1.0);
  return samples[std::min(index, samples.size() - 1)] /
         kMicrosecondsPerMillisecond;
}

void print_interval(double elapsed, double window, const Stats &stats) {
  std::cout << std::fixed << std::setprecision(1) << '[' << std::setw(5)
            << elapsed << "s] loop=" << stats.loops / window
            << "Hz motor=" << stats.motor_reads / window
            << "Hz touch=" << stats.touch_reads / window
            << "Hz control_cmd=" << stats.control_writes / window
            << "Hz latency(avg/min/max)=" << std::setprecision(2)
            << stats.average_ms() << '/'
            << stats.latency_min_us / kMicrosecondsPerMillisecond << '/'
            << stats.latency_max_us / kMicrosecondsPerMillisecond
            << "ms errors=" << stats.errors
            << " sample=" << stats.sample << '\n';
}

} // namespace

int main(int argc, char **argv) {
  Args args;
  if (!parse_args(argc, argv, &args)) {
    return 2;
  }

  auto pdo_layout = revo3::ethercat::default_pdo_layout();
  pdo_layout.has_touch_pdo = args.touch_pdo_enabled;
  revo3::ethercat::Master master(args.slave_position, 0, pdo_layout);
  if (args.dc_enabled) {
    revo3::ethercat::DcConfig dc;
    dc.enabled = true;
    dc.assign_activate = args.dc_assign_activate;
    dc.sync0_cycle_ns =
        static_cast<std::uint32_t>(kNanosecondsPerSecond / args.frequency_hz);
    dc.sync0_shift_ns = args.sync0_shift_ns;
    dc.sync1_cycle_ns = args.sync1_cycle_ns;
    dc.sync1_shift_ns = args.sync1_shift_ns;
    master.configure_dc(dc);
  }
  std::string error;
  if (args.realtime_enabled &&
      !revo3::ethercat::enable_realtime(args.realtime_priority, &error)) {
    std::cerr << error << '\n';
    return 1;
  }
  if (!master.initialize_sdo(&error)) {
    std::cerr << error << '\n';
    return 1;
  }
  const std::string serial =
      read_sdo_string(&master, revo3::ethercat::kSerialNumberObjectIndex);
  const std::string firmware =
      read_sdo_string(&master, revo3::ethercat::kFirmwareVersionObjectIndex);
  const std::string hardware =
      read_sdo_string(&master, revo3::ethercat::kHardwareVersionObjectIndex);
  const std::vector<std::string> motor_sns = read_motor_sdo_strings(&master);
  const std::vector<std::string> motor_versions = read_motor_versions(&master);
  std::uint16_t hand_type = 0;
  read_sdo_u16(&master, revo3::ethercat::kHandTypeObjectIndex, &hand_type);

  std::cout << "DEVICE_INFO: sn=" << serial << ", fw=" << firmware
            << ", hw=" << hardware << ", type=" << hand_type << '\n';
  std::cout << "DETECTED_SLAVE_ID=" << args.slave_position << '\n';
  std::cout << "DEVICE_MOTORS_SN: " << join_csv(motor_sns) << '\n';
  std::cout << "DEVICE_MOTORS_FW: " << join_csv(motor_versions) << '\n';
  if (args.detect_only) {
    return serial == "Unknown" ? 1 : 0;
  }
  if (!master.initialize(&error) || !master.activate(&error)) {
    std::cerr << error << '\n';
    return 1;
  }
  const std::uint64_t period_ns =
      kNanosecondsPerSecond / static_cast<std::uint64_t>(args.frequency_hz);
  if (args.op_warmup_ms > 0) {
    const std::uint64_t warmup_end_ns =
        revo3::ethercat::monotonic_time_ns() +
        static_cast<std::uint64_t>(args.op_warmup_ms) * 1'000'000ULL;
    std::uint64_t next_wakeup_ns = revo3::ethercat::monotonic_time_ns();
    while (revo3::ethercat::monotonic_time_ns() < warmup_end_ns) {
      next_wakeup_ns += period_ns;
      revo3::ethercat::sleep_until_monotonic_ns(next_wakeup_ns);
      master.cycle(next_wakeup_ns);
    }
  }
  if (!master.wait_for_operational(args.op_timeout_ms, period_ns, &error)) {
    std::cerr << error << '\n';
    return 1;
  }

  std::cout << "=== Revo3 EtherCAT Feedback Benchmark ===\n"
            << "scenario=" << args.scenario << '\n'
            << "read_strategy=" << args.read_strategy << '\n'
            << "control_strategy=" << args.control_strategy << '\n'
            << "duration=" << args.duration_seconds
            << "s, motor_id=" << args.motor_id << '\n'
            << "frequency_hz=" << args.frequency_hz << '\n'
            << "dc=" << (args.dc_enabled ? "on" : "off")
            << ", realtime=" << (args.realtime_enabled ? "on" : "off")
            << ", touch_pdo=" << (args.touch_pdo_enabled ? "on" : "off")
            << '\n'
            << "dc_assign=0x" << std::hex << args.dc_assign_activate
            << std::dec << ", sync0_shift_ns=" << args.sync0_shift_ns
            << ", sync1_cycle_ns=" << args.sync1_cycle_ns
            << ", sync1_shift_ns=" << args.sync1_shift_ns
            << ", op_warmup_ms=" << args.op_warmup_ms << '\n'
            << "Note: EtherCAT always exchanges the complete fixed PDO image; "
               "strategies select application-side consumption and updates.\n";

  const revo3::ethercat::MotorCommand base_command = master.command();
  const auto start = Clock::now();
  std::uint64_t next_wakeup_ns = revo3::ethercat::monotonic_time_ns();
  auto last_print = start;
  Stats total;
  Stats interval;

  while (std::chrono::duration<double>(Clock::now() - start).count() <
         args.duration_seconds) {
    next_wakeup_ns += period_ns;
    revo3::ethercat::sleep_until_monotonic_ns(next_wakeup_ns);
    const auto loop_start = Clock::now();
    const double elapsed =
        std::chrono::duration<double>(loop_start - start).count();
    apply_control(&master, args, base_command, elapsed);
    if (args.control_strategy != "none") {
      ++total.control_writes;
      ++interval.control_writes;
    }
    if (!master.cycle(next_wakeup_ns)) {
      ++total.errors;
      ++interval.errors;
    }
    consume_feedback(master, args, &total);
    consume_feedback(master, args, &interval);

    const double latency_us =
        std::chrono::duration<double, std::micro>(Clock::now() - loop_start)
            .count();
    total.record(latency_us, true);
    interval.record(latency_us, false);

    const double window =
        std::chrono::duration<double>(Clock::now() - last_print).count();
    if (window >= 1.0) {
      print_interval(
          std::chrono::duration<double>(Clock::now() - start).count(), window,
          interval);
      interval = Stats{};
      last_print = Clock::now();
    }
  }

  const double duration =
      std::chrono::duration<double>(Clock::now() - start).count();
  std::cout << "=== Summary ===\n"
            << std::fixed << std::setprecision(2) << "duration=" << duration
            << "s loops=" << total.loops << " errors=" << total.errors << '\n'
            << std::setprecision(1) << "loop_hz=" << total.loops / duration
            << '\n'
            << "motor_read_hz=" << total.motor_reads / duration << '\n'
            << "touch_read_hz=" << total.touch_reads / duration << '\n'
            << "control_cmd_hz=" << total.control_writes / duration << '\n'
            << std::setprecision(2) << "latency_ms avg=" << total.average_ms()
            << ", min="
            << total.latency_min_us / kMicrosecondsPerMillisecond
            << ", max="
            << total.latency_max_us / kMicrosecondsPerMillisecond << '\n'
            << "latency_percentiles_ms p50="
            << percentile(total.latencies_us, 0.50) << ", p90="
            << percentile(total.latencies_us, 0.90) << ", p99="
            << percentile(total.latencies_us, 0.99) << '\n';

  master.command() = base_command;
  for (std::size_t joint = 0; joint < revo3::ethercat::kMotorCount; ++joint) {
    master.command().kp_raw[joint] = 0;
    master.command().kd_raw[joint] = 0;
  }
  master.cycle();
  return total.errors == 0 ? 0 : 1;
}
