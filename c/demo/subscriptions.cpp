#include <revo3/revo3.hpp>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>

namespace {

long parse_positive(const char *value, const char *option) {
  char *end = nullptr;
  const auto parsed = std::strtol(value, &end, 10);
  if (value[0] == '\0' || end == value || *end != '\0' || parsed <= 0) {
    throw std::invalid_argument(std::string(option) + " must be positive");
  }
  return parsed;
}

std::uint8_t parse_slave_id(const char *value) {
  char *end = nullptr;
  const auto parsed = std::strtoul(value, &end, 0);
  if (value[0] == '\0' || end == value || *end != '\0' || parsed > 255) {
    throw std::invalid_argument("--slave-id must fit in uint8");
  }
  return static_cast<std::uint8_t>(parsed);
}

const char *require_value(int argc, char **argv, int &index,
                          const char *option) {
  if (index + 1 >= argc) {
    throw std::invalid_argument(std::string(option) + " requires a value");
  }
  return argv[++index];
}

void print_usage(const char *program) {
  std::printf(
      "Usage: %s [--port NAME] [--slave-id ID] [--period-ms MS] "
      "[--health-period-ms MS] [--count N]\n",
      program);
}

}  // namespace

int main(int argc, char **argv) {
  try {
    revo3::DiscoveryOptions discovery;
    auto period = std::chrono::milliseconds(20);
    auto health_period = std::chrono::milliseconds(1000);
    int count = 3;

    for (int index = 1; index < argc; ++index) {
      if (std::strcmp(argv[index], "-h") == 0 ||
          std::strcmp(argv[index], "--help") == 0) {
        print_usage(argv[0]);
        return 0;
      }
      if (std::strcmp(argv[index], "--port") == 0) {
        discovery.port = require_value(argc, argv, index, "--port");
      } else if (std::strcmp(argv[index], "--slave-id") == 0) {
        discovery.slave_id = parse_slave_id(
            require_value(argc, argv, index, "--slave-id"));
      } else if (std::strcmp(argv[index], "--period-ms") == 0) {
        period = std::chrono::milliseconds(parse_positive(
            require_value(argc, argv, index, "--period-ms"), "--period-ms"));
      } else if (std::strcmp(argv[index], "--health-period-ms") == 0) {
        health_period = std::chrono::milliseconds(parse_positive(
            require_value(argc, argv, index, "--health-period-ms"),
            "--health-period-ms"));
      } else if (std::strcmp(argv[index], "--count") == 0) {
        const auto value = parse_positive(
            require_value(argc, argv, index, "--count"), "--count");
        if (value > std::numeric_limits<int>::max()) {
          throw std::invalid_argument("--count is too large");
        }
        count = static_cast<int>(value);
      } else {
        throw std::invalid_argument(std::string("unknown option: ") +
                                    argv[index]);
      }
    }

    revo3::Manager manager;
    auto hand = manager.connect_auto(discovery);

    auto state_subscription = hand.state().subscribe(period);
    for (int index = 0; index < count; ++index) {
      const auto state = state_subscription.next();
      std::printf("State timestamp=%lld.%09lld J0=%.2f degree\n",
                  static_cast<long long>(state.timestamp.sec),
                  static_cast<long long>(state.timestamp.nsec),
                  state.motors.positions_deg[0]);
    }
    state_subscription.close();

    try {
      static_cast<void>(hand.touch().layout());
      auto touch_subscription = hand.touch().subscribe(period);
      for (int index = 0; index < count; ++index) {
        const auto frame = touch_subscription.next();
        std::size_t force_modules = 0;
        for (const auto &module : frame.modules) {
          if (module.has_force3d || module.has_torque2d ||
              module.has_resultant_force) {
            ++force_modules;
          }
        }
        std::printf("Touch sequence=%llu modules=%zu force_modules=%zu\n",
                    static_cast<unsigned long long>(frame.sequence),
                    frame.modules.size(), force_modules);
      }
      touch_subscription.close();
    } catch (const revo3::SdkError &error) {
      if (error.code() != revo3::SdkErrorCode::UnsupportedCapability) {
        throw;
      }
      std::printf("Touch subscription skipped: %s\n", error.what());
    }

    auto health_subscription = hand.health().subscribe(health_period);
    for (int index = 0; index < count; ++index) {
      const auto health = health_subscription.next();
      std::printf(
          "Health safety=%u system=%u error=%u faulted_motors=%u "
          "voltage=%u V\n",
          health.safety_state, health.system_state, health.system_error_code,
          health.faulted_motor_count, health.voltage_v);
    }
    health_subscription.close();

    const auto statistics = hand.statistics();
    std::printf(
        "RuntimeStatistics: state_reads=%llu touch_reads=%llu "
        "failed_operations=%llu\n",
        static_cast<unsigned long long>(statistics.state_reads),
        static_cast<unsigned long long>(statistics.touch_reads),
        static_cast<unsigned long long>(statistics.failed_operations));
    return 0;
  } catch (const revo3::SdkError &error) {
    std::fprintf(stderr, "Revo3 error: %s\n", error.what());
    return 1;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Error: %s\n", error.what());
    print_usage(argv[0]);
    return 1;
  }
}
