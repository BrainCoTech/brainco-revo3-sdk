#include <revo3/revo3.hpp>

#include <cstdint>
#include <cstdio>
#include <limits>
#include <stdexcept>
#include <string>

namespace {

const char *protocol_name(revo3::ProtocolType protocol) {
  switch (protocol) {
  case revo3::ProtocolType::Modbus:
    return "Modbus";
  case revo3::ProtocolType::CanFd:
    return "CANFD";
  case revo3::ProtocolType::Auto:
    return "Auto";
  }
  return "Unknown";
}

const char *side_name(revo3::HandSide side) {
  switch (side) {
  case revo3::HandSide::Left:
    return "Left";
  case revo3::HandSide::Right:
    return "Right";
  case revo3::HandSide::Unknown:
    return "Unknown";
  }
  return "Unknown";
}

std::uint32_t parse_u32(const char *value, const char *option) {
  std::size_t consumed = 0;
  const auto parsed = std::stoull(value, &consumed, 0);
  if (value[0] == '\0' || consumed != std::string(value).size() ||
      parsed > std::numeric_limits<std::uint32_t>::max()) {
    throw std::invalid_argument(std::string("invalid value for ") + option);
  }
  return static_cast<std::uint32_t>(parsed);
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
      "Usage: %s [--scan-all] [--port NAME] [--protocol auto|modbus|canfd] "
      "[--slave-id ID] [--modbus-baudrate BPS] "
      "[--canfd-data-baudrate BPS]\n",
      program);
}

}  // namespace

int main(int argc, char **argv) {
  try {
    revo3::DiscoveryOptions options;
    for (int index = 1; index < argc; ++index) {
      const std::string argument = argv[index];
      if (argument == "-h" || argument == "--help") {
        print_usage(argv[0]);
        return 0;
      }
      if (argument == "--scan-all") {
        options.scan_all = true;
      } else if (argument == "--port") {
        options.port = require_value(argc, argv, index, "--port");
      } else if (argument == "--protocol") {
        const std::string value =
            require_value(argc, argv, index, "--protocol");
        if (value == "auto") {
          options.protocol = revo3::ProtocolType::Auto;
        } else if (value == "modbus") {
          options.protocol = revo3::ProtocolType::Modbus;
        } else if (value == "canfd") {
          options.protocol = revo3::ProtocolType::CanFd;
        } else {
          throw std::invalid_argument(
              "--protocol must be auto, modbus, or canfd");
        }
      } else if (argument == "--slave-id") {
        const auto value = parse_u32(
            require_value(argc, argv, index, "--slave-id"), "--slave-id");
        if (value > std::numeric_limits<std::uint8_t>::max()) {
          throw std::invalid_argument("--slave-id must fit in uint8");
        }
        options.slave_id = static_cast<std::uint8_t>(value);
      } else if (argument == "--modbus-baudrate") {
        options.modbus_baudrate = parse_u32(
            require_value(argc, argv, index, "--modbus-baudrate"),
            "--modbus-baudrate");
      } else if (argument == "--canfd-data-baudrate") {
        options.canfd_data_baudrate = parse_u32(
            require_value(argc, argv, index, "--canfd-data-baudrate"),
            "--canfd-data-baudrate");
      } else {
        throw std::invalid_argument("unknown option: " + argument);
      }
    }

    revo3::Manager manager;
    const auto devices = manager.discover(options);
    if (devices.empty()) {
      std::printf("No Revo3 device detected.\n");
      return 2;
    }

    std::printf("Detected %zu Revo3 device(s):\n", devices.size());
    for (const auto &device : devices) {
      std::printf(
          "  protocol=%s port=%s slave=%u nominal=%u data=%u side=%s "
          "serial=%s firmware=%s\n",
          protocol_name(device.protocol_type), device.port_name.c_str(),
          device.slave_id, device.nominal_baudrate_bps,
          device.data_baudrate_bps, side_name(device.hand_side),
          device.serial_number.empty() ? "unknown" : device.serial_number.c_str(),
          device.firmware_version.empty() ? "unknown"
                                          : device.firmware_version.c_str());
    }
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
