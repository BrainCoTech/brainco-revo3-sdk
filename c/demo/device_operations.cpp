#include <revo3/revo3.hpp>

#include <chrono>
#include <cstdio>
#include <cstring>

int main(int argc, char **argv) {
  using namespace std::chrono_literals;

  revo3::DiscoveryOptions discovery;
  bool calibrate = false;
  bool reboot = false;
  for (int index = 1; index < argc; ++index) {
    if (std::strcmp(argv[index], "--calibrate") == 0) {
      calibrate = true;
    } else if (std::strcmp(argv[index], "--reboot") == 0) {
      reboot = true;
    } else {
      discovery.port = argv[index];
    }
  }

  try {
    revo3::Manager manager;
    auto hand = manager.connect_auto(discovery);
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
