#include "../common/revo3_common.h"
#include <cstdlib>
#include <cstdio>
#include <cstring>

// Build and run:
// Check examples/c/README.md or build instructions.
int main(int argc, char **argv) {
  init_logging(LOG_LEVEL_INFO);

  const char *port = nullptr;
  StarkProtocolType protocol = STARK_PROTOCOL_TYPE_AUTO;
  uint8_t target_slave_id = 0;

  for (int i = 1; i < argc; ++i) {
    if (std::strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
      port = argv[++i];
    } else if (std::strcmp(argv[i], "--protocol") == 0 && i + 1 < argc) {
      const char *p_str = argv[++i];
      if (std::strcmp(p_str, "modbus") == 0) {
        protocol = STARK_PROTOCOL_TYPE_MODBUS;
      } else if (std::strcmp(p_str, "canfd") == 0) {
        protocol = STARK_PROTOCOL_TYPE_CAN_FD;
      }
    } else if (std::strcmp(argv[i], "--slave-id") == 0 && i + 1 < argc) {
      target_slave_id = static_cast<uint8_t>(std::atoi(argv[++i]));
    }
  }

  std::printf("=== Revo3 C++ Collision and Stall Protection Demo ===\n");

  CDetectedDeviceList *list = stark_auto_detect(
      false,
      port,
      protocol,
      target_slave_id,
      0,
      0,
      true
  );

  if (!list || list->count == 0) {
    std::printf("[ERROR] No Revo3 device detected.\n");
    if (list) {
      free_detected_device_list(list);
    }
    return 1;
  }

  const CDetectedDevice &device = list->devices[0];
  DeviceHandler *handle = init_from_detected(&device);
  uint8_t slave_id = device.slave_id;
  StarkProtocolType detected_protocol = device.protocol;

  if (!handle) {
    std::printf("[ERROR] Failed to initialize detected device.\n");
    free_detected_device_list(list);
    return 1;
  }

  std::printf("[INFO] Detected Revo3: port=%s, slave_id=%u, protocol=%u\n",
              device.port_name ? device.port_name : "", slave_id, device.protocol);

  free_detected_device_list(list);

  // 1. Configure collision protection
  CollisionProtectionConfig config;
  config.enable = true;
  config.source = COLLISION_DETECTION_SOURCE_HYBRID;
  config.max_position_error = 10.0f;
  config.max_current = 500.0f;
  config.debounce_time_ms = 100;
  config.strategy = COLLISION_PROTECTION_STRATEGY_SOFT_STOP;

  if (revo3_set_collision_protection_config(handle, slave_id, config) != 0) {
    std::printf("[WARN] Failed to configure collision protection.\n");
  } else {
    std::printf("Collision protection configured (enable: true, strategy: SoftStop).\n");
  }

  // 2. Perform trajectory and ask user to obstruct
  uint16_t joint_id = 13; // Index MCP Flex
  std::printf("Please hold/obstruct Joint %d to trigger collision protection...\n", joint_id);
  std::printf("Moving Joint %d to 60 deg over 3.0 s...\n", joint_id);

  // We start the trajectory in non-blocking way so we can poll status
  revo3_move_joint(handle, slave_id, joint_id, 60.0f, 3.0f, 0.01f);

  bool collision_triggered = false;
  for (int i = 0; i < 80; ++i) { // Check for 4 seconds (80 * 50ms)
    revo3_sleep_ms(50);
    int active = 0;
    if (revo3_is_collision_active(handle, slave_id, joint_id, &active) == 0 && active != 0) {
      std::printf(">>> Collision actively detected on Joint %d! Aborting. <<<\n", joint_id);
      collision_triggered = true;
      break;
    }
  }

  if (collision_triggered) {
    std::printf("Collision triggered. Resetting collision state...\n");
    revo3_reset_collision_state(handle, slave_id);
    CRevo3MotorStatusData *status = revo3_get_motor_status_data(handle, slave_id);
    if (status) {
      float hold_pos = status->positions[joint_id];
      std::printf("Holding obstacle position %.2f deg actively for 3.0s...\n", hold_pos);
      free_revo3_motor_status_data(status);
      for (int i = 0; i < 150; ++i) { // 3.0s / 20ms = 150 ticks
        revo3_set_motor_mit(handle, slave_id, joint_id, hold_pos, 0.0f, 0.0f, 0.3f, 0.1f);
        revo3_sleep_ms(20);
      }
    } else {
      revo3_sleep_ms(3000);
    }
  } else {
    float target_pos = 60.0f;
    std::printf("Movement finished without collision. Holding target position %.2f deg actively for 1.0s...\n", target_pos);
    for (int i = 0; i < 50; ++i) { // 1.0s / 20ms = 50 ticks
      revo3_set_motor_mit(handle, slave_id, joint_id, target_pos, 0.0f, 0.0f, 1.0f, 0.2f);
      revo3_sleep_ms(20);
    }
  }

  close_device_handler(handle, static_cast<uint8_t>(detected_protocol));
  return 0;
}
