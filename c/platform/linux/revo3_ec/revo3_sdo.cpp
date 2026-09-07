#include "revo3_ethercat.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <ecrt.h>
#include <iomanip>
#include <iostream>
#include <limits>
#include <string>

namespace {

struct NamedU16Subindex {
  std::uint8_t subindex;
  const char *name;
};

constexpr std::array<NamedU16Subindex, 5> kMotorSystemParams = {{
    {0x01, "System status"},
    {0x02, "System current"},
    {0x03, "System voltage"},
    {0x04, "System power"},
    {0x05, "System temperature"},
}};

std::uint16_t parse_u16(const char *text) {
  const unsigned long value = std::stoul(text, nullptr, 0);
  if (value > std::numeric_limits<std::uint16_t>::max()) {
    throw std::out_of_range("value exceeds uint16 range");
  }
  return static_cast<std::uint16_t>(value);
}

void usage(const char *program) {
  std::cerr << "Usage:\n"
            << "  " << program << " [slave-position] info\n"
            << "  " << program
            << " [slave-position] read index subindex u8|u16|u32|string\n"
            << "  " << program
            << " [slave-position] write index subindex u8|u16|u32 value\n";
}

template <typename T>
bool read_integer(revo3::ethercat::Master &master, std::uint16_t index,
                  std::uint8_t subindex, T *value) {
  std::array<std::uint8_t, sizeof(T)> bytes{};
  std::size_t size = 0;
  std::uint32_t abort_code = 0;
  if (!master.read_sdo(index, subindex, bytes.data(), bytes.size(), &size,
                       &abort_code) ||
      size != bytes.size()) {
    std::cerr << "SDO read failed, abort=0x" << std::hex << abort_code
              << std::dec << '\n';
    return false;
  }
  if constexpr (sizeof(T) == 1) {
    *value = static_cast<T>(bytes[0]);
  } else if constexpr (sizeof(T) == 2) {
    *value = static_cast<T>(EC_READ_U16(bytes.data()));
  } else {
    *value = static_cast<T>(EC_READ_U32(bytes.data()));
  }
  return true;
}

bool read_string(revo3::ethercat::Master &master, std::uint16_t index,
                 std::string *value) {
  std::array<char, 64> buffer{};
  std::size_t size = 0;
  std::uint32_t abort_code = 0;
  if (!master.read_sdo(index, 0, buffer.data(), buffer.size() - 1, &size,
                       &abort_code)) {
    std::cerr << "SDO read failed, abort=0x" << std::hex << abort_code
              << std::dec << '\n';
    return false;
  }
  buffer[std::min(size, buffer.size() - 1)] = '\0';
  *value = buffer.data();
  return true;
}

} // namespace

int main(int argc, char **argv) {
  try {
    int arg = 1;
    std::uint16_t slave_position = 0;
    if (arg < argc && std::string(argv[arg]) != "info" &&
        std::string(argv[arg]) != "read" && std::string(argv[arg]) != "write") {
      slave_position = parse_u16(argv[arg++]);
    }
    if (arg >= argc) {
      usage(argv[0]);
      return 2;
    }

    revo3::ethercat::Master master(slave_position);
    std::string error;
    if (!master.initialize_sdo(&error)) {
      std::cerr << error << '\n';
      return 1;
    }

    const std::string operation = argv[arg++];
    if (operation == "info") {
      // CoE Object Dictionary mappings:
      // - 0x8001: Firmware version string (e.g. "0.0.8.ML")
      // - 0x8002: Hardware version string (e.g. "0.0.1")
      // - 0x8003: Product serial number string
      // - 0x801A: Motor system status/current/voltage/power/temperature
      // - 0x801B: Stark Hardware Type enum (e.g. 20=Ultra, 23=Pro, 26=Basic)
      std::string firmware;
      std::string hardware;
      std::string serial;
      std::array<std::uint16_t, kMotorSystemParams.size()> system_params{};
      std::uint16_t hand_type = 0;
      bool ok = read_string(master, revo3::ethercat::kFirmwareVersionObjectIndex,
                            &firmware) &&
                read_string(master,
                            revo3::ethercat::kHardwareVersionObjectIndex,
                            &hardware) &&
                read_string(master, revo3::ethercat::kSerialNumberObjectIndex,
                            &serial);
      for (std::size_t i = 0; ok && i < kMotorSystemParams.size(); ++i) {
        ok = read_integer(master, revo3::ethercat::kMotorSystemParamsObjectIndex,
                          kMotorSystemParams[i].subindex, &system_params[i]);
      }
      ok = ok && read_integer(master, revo3::ethercat::kHandTypeObjectIndex, 0,
                              &hand_type);
      if (!ok) {
        return 1;
      }
      std::cout << "Firmware: " << firmware << "\nHardware: " << hardware
                << "\nSerial: " << serial;
      for (std::size_t i = 0; i < kMotorSystemParams.size(); ++i) {
        std::cout << '\n' << kMotorSystemParams[i].name << ": "
                  << system_params[i];
      }
      std::cout << "\nHand type: " << hand_type << '\n';
      return 0;
    }

    if (arg + 2 >= argc) {
      usage(argv[0]);
      return 2;
    }
    const std::uint16_t index = parse_u16(argv[arg++]);
    const std::uint16_t parsed_subindex = parse_u16(argv[arg++]);
    if (parsed_subindex > std::numeric_limits<std::uint8_t>::max()) {
      throw std::out_of_range("subindex exceeds uint8 range");
    }
    const std::uint8_t subindex = static_cast<std::uint8_t>(parsed_subindex);
    const std::string type = argv[arg++];

    if (operation == "read") {
      if (type == "u8") {
        std::uint8_t value = 0;
        if (!read_integer(master, index, subindex, &value)) {
          return 1;
        }
        std::cout << static_cast<unsigned int>(value) << " (0x" << std::hex
                  << static_cast<unsigned int>(value) << ")\n";
      } else if (type == "u16") {
        std::uint16_t value = 0;
        if (!read_integer(master, index, subindex, &value)) {
          return 1;
        }
        std::cout << value << " (0x" << std::hex << value << ")\n";
      } else if (type == "u32") {
        std::uint32_t value = 0;
        if (!read_integer(master, index, subindex, &value)) {
          return 1;
        }
        std::cout << value << " (0x" << std::hex << value << ")\n";
      } else if (type == "string") {
        std::array<char, 128> buffer{};
        std::size_t size = 0;
        std::uint32_t abort_code = 0;
        if (!master.read_sdo(index, subindex, buffer.data(), buffer.size() - 1,
                             &size, &abort_code)) {
          std::cerr << "SDO read failed, abort=0x" << std::hex << abort_code
                    << '\n';
          return 1;
        }
        buffer[std::min(size, buffer.size() - 1)] = '\0';
        std::cout << buffer.data() << '\n';
      } else {
        usage(argv[0]);
        return 2;
      }
      return 0;
    }

    if (operation != "write" || arg >= argc ||
        (type != "u8" && type != "u16" && type != "u32")) {
      usage(argv[0]);
      return 2;
    }
    const unsigned long long parsed_input = std::stoull(argv[arg], nullptr, 0);
    const unsigned long long max_input =
        type == "u8"    ? std::numeric_limits<std::uint8_t>::max()
        : type == "u16" ? std::numeric_limits<std::uint16_t>::max()
                        : std::numeric_limits<std::uint32_t>::max();
    if (parsed_input > max_input) {
      throw std::out_of_range("write value exceeds selected type range");
    }
    const std::uint32_t input = static_cast<std::uint32_t>(parsed_input);
    std::array<std::uint8_t, 4> bytes{};
    std::size_t size = 0;
    if (type == "u8") {
      bytes[0] = static_cast<std::uint8_t>(input);
      size = 1;
    } else if (type == "u16") {
      EC_WRITE_U16(bytes.data(), static_cast<std::uint16_t>(input));
      size = 2;
    } else {
      EC_WRITE_U32(bytes.data(), input);
      size = 4;
    }
    std::uint32_t abort_code = 0;
    if (!master.write_sdo(index, subindex, bytes.data(), size, &abort_code)) {
      std::cerr << "SDO write failed, abort=0x" << std::hex << abort_code
                << '\n';
      return 1;
    }
    std::cout << "SDO write completed\n";
    return 0;
  } catch (const std::exception &error) {
    std::cerr << "Invalid argument: " << error.what() << '\n';
    usage(argv[0]);
    return 2;
  }
}
