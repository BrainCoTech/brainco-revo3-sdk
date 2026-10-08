#include <revo3/revo3.hpp>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>

int main(int argc, char **argv) {
  revo3::init_logging(LOG_LEVEL_INFO, true);
  using namespace std::chrono_literals;

  revo3::DiscoveryOptions discovery;
  bool calibrate = false;
  bool reboot = false;
  bool run = false;
  int new_slave_id = 0;
  for (int index = 1; index < argc; ++index) {
    if (std::strcmp(argv[index], "--help") == 0 ||
        std::strcmp(argv[index], "-h") == 0) {
      std::printf("Usage: %s [PORT] [--calibrate] [--reboot] [--new-slave-id ID [--run]]\n", argv[0]);
      std::printf("ID changes are read-only unless --run is given. Isolate the target hand first.\n");
      return 0;
    } else if (std::strcmp(argv[index], "--calibrate") == 0) {
      calibrate = true;
    } else if (std::strcmp(argv[index], "--reboot") == 0) {
      reboot = true;
    } else if (std::strcmp(argv[index], "--run") == 0) {
      run = true;
    } else if (std::strcmp(argv[index], "--new-slave-id") == 0) {
      if (++index >= argc) {
        std::fprintf(stderr, "--new-slave-id requires a value in 1..247\n");
        return 1;
      }
      char *end = nullptr;
      const long value = std::strtol(argv[index], &end, 0);
      if (*end != '\0' || value < 1 || value > 247) {
        std::fprintf(stderr, "--new-slave-id must be in 1..247\n");
        return 1;
      }
      new_slave_id = static_cast<int>(value);
    } else {
      discovery.port = argv[index];
    }
  }
  if (new_slave_id && (calibrate || reboot)) {
    std::fprintf(stderr, "Do not combine an ID change with calibration or reboot\n");
    return 1;
  }

  try {
    revo3::Manager manager;
    auto hand = manager.connect_auto(discovery);
    // A later touch read failure does not discard successful motor reads.
    try {
      hand.refresh_device_info();
    } catch (const revo3::SdkError &error) {
      std::fprintf(stderr, "Device metadata refresh incomplete: %s\n", error.what());
    }
    try {
      hand.refresh_firmware_info();
    } catch (const revo3::SdkError &error) {
      std::fprintf(stderr, "Firmware metadata refresh incomplete: %s\n", error.what());
    }
    for (const auto &sn : hand.device_info().motor_serial_numbers) {
      std::printf("Motor SN: %s\n", sn.c_str());
    }
    for (const auto &version : hand.firmware_info().motor_firmware_versions) {
      std::printf("Motor firmware: %s\n", version.c_str());
    }
    const auto config = hand.config().snapshot();
    const auto runtime = hand.config().runtime_options();
    std::printf("DeviceConfig: slave=%u RS485=%u CANFD=%u buzzer=%s vibration=%s "
                "power_on_auto_calibration=%s auto_clear_motor_faults=%s\n",
                config.slave_id, config.rs485_baudrate, config.canfd_baudrate,
                config.buzzer_enabled ? "on" : "off",
                config.vibration_enabled ? "on" : "off",
                config.power_on_auto_calibration_enabled ? "on" : "off",
                config.auto_clear_motor_faults_enabled ? "on" : "off");
    std::printf("RuntimeOptions: state=%lldms touch=%lldms health=%lldms servo_command_timeout=%lldms\n",
                static_cast<long long>(runtime.state_subscription_period.count()),
                static_cast<long long>(runtime.touch_subscription_period.count()),
                static_cast<long long>(runtime.health_subscription_period.count()),
                static_cast<long long>(runtime.servo_command_timeout.count()));

    if (new_slave_id) {
      if (!run) {
        std::printf("Read-only: would set slave ID to %d; add --run to write\n", new_slave_id);
        return 0;
      }
      const auto serial_number = hand.device_info().serial_number;
      try {
        hand.config().set_slave_id(static_cast<std::uint8_t>(new_slave_id));
      } catch (...) {
        manager.close();
        throw;
      }
      manager.close();
      revo3::Manager new_manager;
      discovery.slave_id = static_cast<std::uint8_t>(new_slave_id);
      discovery.broadcast = false;
      auto new_hand = new_manager.connect_auto(discovery);
      const auto actual_config = new_hand.config().snapshot();
      if (actual_config.slave_id != new_slave_id ||
          (!serial_number.empty() && new_hand.device_info().serial_number != serial_number)) {
        throw std::runtime_error("Rediscovered device has an unexpected identity");
      }
      std::printf("New Manager connected; verified slave ID: %u\n", actual_config.slave_id);
      new_hand.close();
      new_manager.close();
      return 0;
    }

    if (calibrate) {
      hand.calibration().calibrate_joints();
      std::printf("Calibration command sent\n");
    }
    if (reboot) {
      auto operation = hand.maintenance().reboot();
      std::printf("Reboot state=%d\n",
                  static_cast<int>(operation.wait(30s)));
    }
    return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Error: %s\n", error.what());
    return 1;
  }
}
