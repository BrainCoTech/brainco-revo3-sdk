#include <revo3/revo3.hpp>

#include <chrono>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <stdexcept>
#include <string>

namespace {

const char *state_name(revo3::OperationState state) {
  switch (state) {
  case revo3::OperationState::Pending:
    return "Pending";
  case revo3::OperationState::Running:
    return "Running";
  case revo3::OperationState::Succeeded:
    return "Succeeded";
  case revo3::OperationState::Cancelled:
    return "Cancelled";
  case revo3::OperationState::Preempted:
    return "Preempted";
  case revo3::OperationState::Failed:
    return "Failed";
  case revo3::OperationState::Indeterminate:
    return "Indeterminate";
  }
  return "Unknown";
}

revo3::FirmwareTarget parse_target(const std::string &target) {
  if (target == "main") {
    return revo3::FirmwareTarget::MainFirmware;
  }
  if (target == "image") {
    return revo3::FirmwareTarget::Image;
  }
  if (target == "motor") {
    return revo3::FirmwareTarget::MotorFirmware;
  }
  throw std::invalid_argument("--target must be main, image, or motor");
}

long parse_non_negative(const char *value, const char *option, bool positive) {
  std::size_t parsed = 0;
  const std::string text(value);
  const long result = std::stol(text, &parsed);
  if (parsed != text.size() || result < 0 || (positive && result == 0)) {
    throw std::invalid_argument(std::string(option) +
                                (positive ? " must be positive"
                                          : " must be non-negative"));
  }
  return result;
}

}  // namespace

int main(int argc, char **argv) {
  revo3::init_logging(LOG_LEVEL_INFO, true);
  revo3::DiscoveryOptions discovery;
  std::string firmware;
  std::string target_name = "main";
  long wait_seconds = 5;
  long timeout_seconds = 600;
  bool run = false;

  try {
    for (int index = 1; index < argc; ++index) {
      if (std::strcmp(argv[index], "--help") == 0 ||
          std::strcmp(argv[index], "-h") == 0) {
        std::printf(
            "Usage: %s --firmware <file> [--target main|image|motor] "
            "[--port <name>] [--wait-secs <seconds>] "
            "[--timeout <seconds>] --run\n",
            argv[0]);
        return 0;
      }
      if (std::strcmp(argv[index], "--firmware") == 0 && index + 1 < argc) {
        firmware = argv[++index];
      } else if (std::strcmp(argv[index], "--target") == 0 &&
                 index + 1 < argc) {
        target_name = argv[++index];
      } else if (std::strcmp(argv[index], "--port") == 0 &&
                 index + 1 < argc) {
        discovery.port = argv[++index];
      } else if (std::strcmp(argv[index], "--wait-secs") == 0 &&
                 index + 1 < argc) {
        wait_seconds = parse_non_negative(argv[++index], "--wait-secs", false);
      } else if (std::strcmp(argv[index], "--timeout") == 0 &&
                 index + 1 < argc) {
        timeout_seconds = parse_non_negative(argv[++index], "--timeout", true);
      } else if (std::strcmp(argv[index], "--run") == 0) {
        run = true;
      } else {
        throw std::invalid_argument(std::string("unknown or incomplete option: ") +
                                    argv[index]);
      }
    }

    if (firmware.empty()) {
      throw std::invalid_argument("--firmware is required");
    }
    std::ifstream input(firmware, std::ios::binary);
    if (!input.good()) {
      throw std::invalid_argument("firmware file is not readable: " + firmware);
    }
    const auto target = parse_target(target_name);
    if (!run) {
      throw std::invalid_argument(
          "refusing firmware update without explicit --run acknowledgement");
    }

    std::printf("Firmware: %s\nTarget: %s\n", firmware.c_str(),
                target_name.c_str());
    std::printf(
        "Do not disconnect power or communication while DFU is running.\n");
    revo3::Manager manager;
    auto hand = manager.connect_auto(discovery);
    auto operation = hand.maintenance().update_firmware(
        firmware, target, static_cast<std::size_t>(wait_seconds));
    const auto state = operation.wait(std::chrono::seconds(timeout_seconds));
    std::printf("DFU state: %s (%d)\n", state_name(state),
                static_cast<int>(state));
    if (const auto error = operation.error()) {
      std::fprintf(stderr,
                   "DFU error: code=%u effect=%u recovery=%u retryable=%s "
                   "message=%s\n",
                   static_cast<unsigned>(error->code()),
                   static_cast<unsigned>(error->operation_effect()),
                   static_cast<unsigned>(error->recovery_requirement()),
                   error->retryable() ? "true" : "false", error->what());
      return 1;
    }
    if (state != revo3::OperationState::Succeeded) {
      std::fprintf(stderr,
                   "DFU did not succeed; inspect device state before retrying.\n");
      return 1;
    }
    std::printf("Firmware update succeeded\n");
    return 0;
  } catch (const revo3::SdkError &error) {
    std::fprintf(stderr,
                 "SDK error: code=%u effect=%u recovery=%u retryable=%s "
                 "message=%s\n",
                 static_cast<unsigned>(error.code()),
                 static_cast<unsigned>(error.operation_effect()),
                 static_cast<unsigned>(error.recovery_requirement()),
                 error.retryable() ? "true" : "false", error.what());
    return 1;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Error: %s\n", error.what());
    return 2;
  }
}
