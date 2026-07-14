#include "../common/revo3_common.h"

#include <array>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <string>

namespace {

constexpr int kMotorCount = 21;
constexpr double kPi = 3.14159265358979323846;

struct Args {
  std::string scenario = "motor";
  std::string read_strategy = "full-state";
  std::string control_strategy = "none";
  double duration_secs = 10.0;
  int motor_id = 3;
  float amplitude_deg = 3.0f;
  float sine_hz = 0.5f;
  const char *port = nullptr;
  uint32_t baudrate = 5000000;
  uint8_t slave_id = 126;
};

struct Stats {
  uint64_t loops = 0;
  uint64_t motor_reads = 0;
  uint64_t touch_reads = 0;
  uint64_t control_writes = 0;
  uint64_t errors = 0;
  double latency_sum_us = 0.0;
  double latency_min_us = 0.0;
  double latency_max_us = 0.0;
  float last_motor_sample = 0.0f;
  uint16_t last_touch_sample = 0;

  void record_loop(double latency_us) {
    loops += 1;
    latency_sum_us += latency_us;
    latency_min_us = latency_min_us == 0.0 ? latency_us : std::fmin(latency_min_us, latency_us);
    latency_max_us = std::fmax(latency_max_us, latency_us);
  }

  double avg_latency_ms() const {
    return loops == 0 ? 0.0 : latency_sum_us / static_cast<double>(loops) / 1000.0;
  }
};

using Clock = std::chrono::steady_clock;

void print_usage(const char *program) {
  std::printf("Usage:\n");
  std::printf("  %s [options]\n\n", program);
  std::printf("Options:\n");
  std::printf("  --scenario <motor|motor-touch|closed-loop>\n");
  std::printf("  --read <single-status|multi-status|all-positions|split-state|full-state|touch-only>\n");
  std::printf("  --control <none|single-position|all-positions|single-mit>\n");
  std::printf("  --duration <seconds>\n");
  std::printf("  --motor <0..20>\n");
  std::printf("  --amplitude <deg>\n");
  std::printf("  --sine-hz <hz>\n");
  std::printf("  --port <serial-port> --baudrate <baud> --slave-id <id>\n");
}

bool next_arg(int argc, char **argv, int &i, const char **value) {
  if (i + 1 >= argc) {
    std::fprintf(stderr, "[ERROR] Missing value for %s\n", argv[i]);
    return false;
  }
  *value = argv[++i];
  return true;
}

bool is_one_of(const std::string &value, std::initializer_list<const char *> allowed) {
  for (const char *item : allowed) {
    if (value == item) {
      return true;
    }
  }
  return false;
}

bool parse_args(int argc, char **argv, Args &args) {
  for (int i = 1; i < argc; ++i) {
    const char *value = nullptr;
    if (std::strcmp(argv[i], "--help") == 0 || std::strcmp(argv[i], "-h") == 0) {
      print_usage(argv[0]);
      return false;
    } else if (std::strcmp(argv[i], "--scenario") == 0) {
      if (!next_arg(argc, argv, i, &value)) return false;
      args.scenario = value;
    } else if (std::strcmp(argv[i], "--read") == 0) {
      if (!next_arg(argc, argv, i, &value)) return false;
      args.read_strategy = value;
    } else if (std::strcmp(argv[i], "--control") == 0) {
      if (!next_arg(argc, argv, i, &value)) return false;
      args.control_strategy = value;
    } else if (std::strcmp(argv[i], "--duration") == 0) {
      if (!next_arg(argc, argv, i, &value)) return false;
      args.duration_secs = std::strtod(value, nullptr);
    } else if (std::strcmp(argv[i], "--motor") == 0) {
      if (!next_arg(argc, argv, i, &value)) return false;
      args.motor_id = std::atoi(value);
    } else if (std::strcmp(argv[i], "--amplitude") == 0) {
      if (!next_arg(argc, argv, i, &value)) return false;
      args.amplitude_deg = static_cast<float>(std::strtod(value, nullptr));
    } else if (std::strcmp(argv[i], "--sine-hz") == 0) {
      if (!next_arg(argc, argv, i, &value)) return false;
      args.sine_hz = static_cast<float>(std::strtod(value, nullptr));
    } else if (std::strcmp(argv[i], "--port") == 0) {
      if (!next_arg(argc, argv, i, &value)) return false;
      args.port = value;
    } else if (std::strcmp(argv[i], "--baudrate") == 0) {
      if (!next_arg(argc, argv, i, &value)) return false;
      args.baudrate = static_cast<uint32_t>(std::strtoul(value, nullptr, 10));
    } else if (std::strcmp(argv[i], "--slave-id") == 0) {
      if (!next_arg(argc, argv, i, &value)) return false;
      args.slave_id = static_cast<uint8_t>(std::strtoul(value, nullptr, 10));
    } else {
      std::fprintf(stderr, "[ERROR] Unknown argument: %s\n", argv[i]);
      return false;
    }
  }

  if (args.scenario == "closed-loop" && args.control_strategy == "none") {
    args.control_strategy = "single-position";
  }
  if (!is_one_of(args.scenario, {"motor", "motor-touch", "closed-loop"})) {
    std::fprintf(stderr, "[ERROR] Unknown scenario: %s\n", args.scenario.c_str());
    return false;
  }
  if (!is_one_of(args.read_strategy,
                 {"single-status", "multi-status", "all-positions", "split-state", "full-state", "touch-only"})) {
    std::fprintf(stderr, "[ERROR] Unknown read strategy: %s\n", args.read_strategy.c_str());
    return false;
  }
  if (!is_one_of(args.control_strategy, {"none", "single-position", "all-positions", "single-mit"})) {
    std::fprintf(stderr, "[ERROR] Unknown control strategy: %s\n", args.control_strategy.c_str());
    return false;
  }
  if (!std::isfinite(args.duration_secs) || args.duration_secs <= 0.0) {
    std::fprintf(stderr, "[ERROR] --duration must be a positive finite number, got %.3f\n", args.duration_secs);
    return false;
  }
  if (!std::isfinite(args.amplitude_deg) || args.amplitude_deg < 0.0f) {
    std::fprintf(stderr, "[ERROR] --amplitude must be a non-negative finite number, got %.3f\n", args.amplitude_deg);
    return false;
  }
  if (!std::isfinite(args.sine_hz) || args.sine_hz < 0.0f) {
    std::fprintf(stderr, "[ERROR] --sine-hz must be a non-negative finite number, got %.3f\n", args.sine_hz);
    return false;
  }
  return true;
}

bool connect_revo3(const Args &args, Revo3Context &ctx) {
  if (args.port) {
    ctx.handle = modbus_open(args.port, args.baudrate);
    ctx.protocol = STARK_PROTOCOL_TYPE_MODBUS;
    ctx.slave_id = args.slave_id;
    if (!ctx.handle) {
      std::fprintf(stderr, "[ERROR] Failed to open Modbus port: %s\n", args.port);
      return false;
    }
    return true;
  }

  CDetectedDeviceList *list = stark_auto_detect(false, nullptr, STARK_PROTOCOL_TYPE_AUTO, 0, 0, 0, false);
  if (!list || list->count == 0) {
    std::fprintf(stderr, "[ERROR] No Revo3 device detected.\n");
    if (list) free_detected_device_list(list);
    return false;
  }

  const CDetectedDevice &device = list->devices[0];
  ctx.handle = init_from_detected(&device);
  ctx.protocol = device.protocol;
  ctx.slave_id = device.slave_id;
  std::printf("[INFO] Detected Revo3: port=%s, slave_id=%u, protocol=%u\n",
              device.port_name ? device.port_name : "", ctx.slave_id, ctx.protocol);
  free_detected_device_list(list);
  return ctx.handle != nullptr;
}

bool run_control(DeviceHandler *handle,
                 uint8_t slave_id,
                 const Args &args,
                 const std::array<float, kMotorCount> &base_positions,
                 double phase) {
  float target = base_positions[args.motor_id] + args.amplitude_deg * static_cast<float>(std::sin(phase));

  if (args.control_strategy == "none") {
    return true;
  }
  if (args.control_strategy == "single-position") {
    revo3_set_motor_position(handle, slave_id, static_cast<uint8_t>(args.motor_id), target);
    return true;
  }
  if (args.control_strategy == "all-positions") {
    std::array<float, kMotorCount> positions = base_positions;
    positions[args.motor_id] = target;
    revo3_set_all_motor_positions(handle, slave_id, positions.data());
    return true;
  }
  if (args.control_strategy == "single-mit") {
    revo3_joint_mit_control(handle, slave_id, static_cast<uint8_t>(args.motor_id), 1.0f, 0.1f, target, 0.0f, 0.0f);
    return true;
  }
  return false;
}

bool read_motor(DeviceHandler *handle,
                uint8_t slave_id,
                const std::string &strategy,
                int motor_id,
                Stats &stats) {
  if (strategy == "single-status") {
    uint16_t statuses[kMotorCount] = {0};
    if (revo3_get_all_motor_status(handle, slave_id, statuses) != 0) return false;
    stats.last_motor_sample = static_cast<float>(statuses[motor_id]);
  } else if (strategy == "multi-status") {
    uint16_t statuses[kMotorCount] = {0};
    uint16_t errors[kMotorCount] = {0};
    if (revo3_get_all_motor_status(handle, slave_id, statuses) != 0) return false;
    if (revo3_get_all_motor_errors(handle, slave_id, errors) != 0) return false;
    stats.last_motor_sample = static_cast<float>(statuses[motor_id] + errors[motor_id]);
  } else if (strategy == "all-positions") {
    float positions[kMotorCount] = {0.0f};
    if (revo3_get_all_motor_positions(handle, slave_id, positions) != 0) return false;
    stats.last_motor_sample = positions[motor_id];
  } else if (strategy == "split-state") {
    float positions[kMotorCount] = {0.0f};
    float velocities[kMotorCount] = {0.0f};
    float currents[kMotorCount] = {0.0f};
    uint16_t errors[kMotorCount] = {0};
    if (revo3_get_all_motor_positions(handle, slave_id, positions) != 0) return false;
    if (revo3_get_all_motor_velocities(handle, slave_id, velocities) != 0) return false;
    if (revo3_get_all_motor_currents(handle, slave_id, currents) != 0) return false;
    if (revo3_get_all_motor_errors(handle, slave_id, errors) != 0) return false;
    stats.last_motor_sample = positions[motor_id] + velocities[motor_id] + currents[motor_id]
                              + static_cast<float>(errors[motor_id]);
  } else if (strategy == "full-state") {
    CRevo3MotorStatusData *status = revo3_get_motor_status_data(handle, slave_id);
    if (!status) return false;
    stats.last_motor_sample = status->positions[motor_id];
    free_revo3_motor_status_data(status);
  } else if (strategy == "touch-only") {
    return true;
  } else {
    return false;
  }

  stats.motor_reads += 1;
  return true;
}

bool run_reads(DeviceHandler *handle,
               uint8_t slave_id,
               const Args &args,
               Stats &total,
               Stats &interval) {
  if (args.read_strategy != "touch-only") {
    if (!read_motor(handle, slave_id, args.read_strategy, args.motor_id, total)) return false;
    interval.motor_reads += 1;
  }

  bool needs_touch = args.scenario == "motor-touch" || args.scenario == "closed-loop"
                     || args.read_strategy == "touch-only";
  if (needs_touch) {
    CRevo3TouchData touch = {};
    if (revo3_get_all_touch_data(handle, slave_id, &touch) != 0) return false;
    total.last_touch_sample = touch.summary[0];
    total.touch_reads += 1;
    interval.touch_reads += 1;
  }
  return true;
}

double elapsed_seconds(Clock::time_point start) {
  return std::chrono::duration<double>(Clock::now() - start).count();
}

void print_interval(double elapsed, double window, const Stats &stats) {
  std::printf("[%5.1fs] loop=%7.1fHz motor=%7.1fHz touch=%7.1fHz control_cmd=%7.1fHz "
              "latency(avg/min/max)=%.2f/%.2f/%.2fms errors=%llu sample=%.2f touch=%u\n",
              elapsed,
              static_cast<double>(stats.loops) / window,
              static_cast<double>(stats.motor_reads) / window,
              static_cast<double>(stats.touch_reads) / window,
              static_cast<double>(stats.control_writes) / window,
              stats.avg_latency_ms(),
              stats.latency_min_us / 1000.0,
              stats.latency_max_us / 1000.0,
              static_cast<unsigned long long>(stats.errors),
              stats.last_motor_sample,
              static_cast<unsigned>(stats.last_touch_sample));
}

void print_summary(double duration, const Stats &stats) {
  std::printf("=== Summary ===\n");
  std::printf("duration=%.2fs loops=%llu errors=%llu\n",
              duration,
              static_cast<unsigned long long>(stats.loops),
              static_cast<unsigned long long>(stats.errors));
  std::printf("loop_hz=%.1f\n", static_cast<double>(stats.loops) / duration);
  std::printf("motor_read_hz=%.1f\n", static_cast<double>(stats.motor_reads) / duration);
  std::printf("touch_read_hz=%.1f\n", static_cast<double>(stats.touch_reads) / duration);
  std::printf("control_cmd_hz=%.1f\n", static_cast<double>(stats.control_writes) / duration);
  std::printf("latency_ms avg=%.2f, min=%.2f, max=%.2f\n",
              stats.avg_latency_ms(),
              stats.latency_min_us / 1000.0,
              stats.latency_max_us / 1000.0);
}

} // namespace

int main(int argc, char **argv) {
  init_logging(LOG_LEVEL_INFO);

  Args args;
  if (!parse_args(argc, argv, args)) {
    return 1;
  }
  if (args.motor_id < 0 || args.motor_id >= kMotorCount) {
    std::fprintf(stderr, "[ERROR] motor must be 0..%d, got %d\n", kMotorCount - 1, args.motor_id);
    return 1;
  }

  Revo3Context ctx;
  if (!connect_revo3(args, ctx)) {
    return 1;
  }

  StarkHardwareType hw_type =
      args.scenario == "motor" && args.read_strategy != "touch-only"
          ? STARK_HARDWARE_TYPE_REVO3_ULTRA
          : STARK_HARDWARE_TYPE_REVO3_ULTRA_TOUCH;
  stark_set_hardware_type(ctx.handle, ctx.slave_id, hw_type);

  bool needs_touch = args.scenario == "motor-touch" || args.scenario == "closed-loop"
                     || args.read_strategy == "touch-only";
  CDeviceInfo *device_info = revo3_get_device_info(ctx.handle, ctx.slave_id);
  if (!device_info) {
    std::fprintf(stderr, "[WARN] Device info query failed, continuing benchmark.\n");
  }
  TouchVendor touch_vendor = revo3_get_touch_vendor(ctx.handle, ctx.slave_id);
  if (needs_touch && touch_vendor == TOUCH_VENDOR_UNKNOWN) {
    std::fprintf(stderr,
                 "[ERROR] UNSUPPORTED_FEATURE: Device does not support touch sensor "
                 "(TouchVendor is Unknown).\n");
    if (device_info) {
      free_device_info(device_info);
    }
    revo3_close(ctx);
    return 1;
  }

  std::printf("=== Revo3 Feedback Benchmark ===\n");
  if (device_info) {
    std::printf("DEVICE_INFO: sn=%s, fw=%s, hw=%s, type=%u, touch_vendor=%u\n",
                device_info->serial_number ? device_info->serial_number : "",
                device_info->firmware_version ? device_info->firmware_version : "",
                device_info->hardware_version ? device_info->hardware_version : "",
                static_cast<unsigned>(device_info->hardware_type),
                static_cast<unsigned>(touch_vendor));
    free_device_info(device_info);
  } else {
    std::printf("DEVICE_INFO: unavailable, touch_vendor=%u\n", static_cast<unsigned>(touch_vendor));
  }
  std::printf("scenario=%s\n", args.scenario.c_str());
  std::printf("read_strategy=%s\n", args.read_strategy.c_str());
  std::printf("control_strategy=%s\n", args.control_strategy.c_str());
  std::printf("duration=%.1fs, motor_id=%d\n", args.duration_secs, args.motor_id);
  std::printf("Note: single-status uses the public bulk status API and consumes only one motor value.\n");

  std::array<float, kMotorCount> base_positions = {};
  if (args.control_strategy != "none") {
    float positions[kMotorCount] = {0.0f};
    if (revo3_get_all_motor_positions(ctx.handle, ctx.slave_id, positions) != 0) {
      std::fprintf(stderr, "[ERROR] Failed to read base positions before control benchmark.\n");
      revo3_close(ctx);
      return 1;
    }
    for (int i = 0; i < kMotorCount; ++i) {
      base_positions[i] = positions[i];
    }
  }

  Stats total;
  Stats interval;
  auto start = Clock::now();
  auto last_print = start;

  while (elapsed_seconds(start) < args.duration_secs) {
    auto loop_start = Clock::now();
    double phase = 2.0 * kPi * args.sine_hz * elapsed_seconds(start);

    if (run_control(ctx.handle, ctx.slave_id, args, base_positions, phase)) {
      if (args.control_strategy != "none") {
        total.control_writes += 1;
        interval.control_writes += 1;
      }
    } else {
      total.errors += 1;
      interval.errors += 1;
    }

    if (!run_reads(ctx.handle, ctx.slave_id, args, total, interval)) {
      total.errors += 1;
      interval.errors += 1;
    }

    double latency_us = std::chrono::duration<double, std::micro>(Clock::now() - loop_start).count();
    total.record_loop(latency_us);
    interval.record_loop(latency_us);

    double window = elapsed_seconds(last_print);
    if (window >= 1.0) {
      print_interval(elapsed_seconds(start), window, interval);
      interval = Stats();
      last_print = Clock::now();
    }
  }

  print_summary(elapsed_seconds(start), total);

  if (args.control_strategy != "none") {
    revo3_set_all_motor_positions(ctx.handle, ctx.slave_id, base_positions.data());
  }
  revo3_close(ctx);
  return 0;
}
