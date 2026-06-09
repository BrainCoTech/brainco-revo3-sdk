#include "revo3_common.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

namespace {

uint32_t parse_u32(const char *s, uint32_t fallback) {
  if (!s) {
    return fallback;
  }
  char *end = nullptr;
  unsigned long value = std::strtoul(s, &end, 10);
  return end && *end == '\0' ? static_cast<uint32_t>(value) : fallback;
}

void print_usage(const char *program) {
  std::printf("Usage:\n");
  std::printf("  %s                         # auto-detect Revo3\n", program);
  std::printf("  %s --modbus <port> [baud] [slave_id]\n", program);
  std::printf("\nDefaults: baud=5000000, slave_id=1\n");
}

} // namespace

const char *revo3_hw_type_name(StarkHardwareType hw_type) {
  switch (hw_type) {
  case STARK_HARDWARE_TYPE_REVO3_ULTRA:
    return "Revo3 Ultra";
  case STARK_HARDWARE_TYPE_REVO3_ULTRA_TOUCH:
    return "Revo3 Ultra Touch";
  case STARK_HARDWARE_TYPE_REVO3_ULTRA_VISION_TOUCH:
    return "Revo3 Ultra VisionTouch";
  case STARK_HARDWARE_TYPE_REVO3_PRO:
    return "Revo3 Pro";
  case STARK_HARDWARE_TYPE_REVO3_PRO_TOUCH:
    return "Revo3 Pro Touch";
  case STARK_HARDWARE_TYPE_REVO3_BASIC:
    return "Revo3 Basic";
  case STARK_HARDWARE_TYPE_REVO3_BASIC_TOUCH:
    return "Revo3 Basic Touch";
  default:
    return "Revo3";
  }
}

bool revo3_init_from_args(Revo3Context &ctx, int argc, char **argv) {
  if (argc > 1 && std::strcmp(argv[1], "--help") == 0) {
    print_usage(argv[0]);
    return false;
  }

  if (argc > 2 && std::strcmp(argv[1], "--modbus") == 0) {
    const char *port = argv[2];
    uint32_t baudrate = argc > 3 ? parse_u32(argv[3], 5000000) : 5000000;
    uint8_t slave_id = argc > 4 ? static_cast<uint8_t>(parse_u32(argv[4], 1)) : 1;

    ctx.handle = modbus_open(port, baudrate);
    ctx.protocol = STARK_PROTOCOL_TYPE_MODBUS;
    ctx.slave_id = slave_id;
    if (!ctx.handle) {
      std::fprintf(stderr, "[ERROR] Failed to open Modbus port: %s\n", port);
      return false;
    }
    stark_set_hardware_type(ctx.handle, ctx.slave_id, STARK_HARDWARE_TYPE_REVO3_ULTRA);
    return true;
  }

  if (argc > 1) {
    print_usage(argv[0]);
    return false;
  }

  CDetectedDeviceList *list = stark_auto_detect(false, nullptr, STARK_PROTOCOL_TYPE_AUTO, 0, 0);
  if (!list || list->count == 0) {
    std::fprintf(stderr, "[ERROR] No Revo3 device detected.\n");
    if (list) {
      free_detected_device_list(list);
    }
    return false;
  }

  const CDetectedDevice &device = list->devices[0];
  ctx.handle = init_from_detected(&device);
  ctx.protocol = device.protocol;
  ctx.slave_id = device.slave_id;
  if (!ctx.handle) {
    std::fprintf(stderr, "[ERROR] Failed to initialize detected device.\n");
    free_detected_device_list(list);
    return false;
  }

  std::printf("[INFO] Detected Revo3: port=%s, slave_id=%u, protocol=%u\n",
              device.port_name ? device.port_name : "", ctx.slave_id, ctx.protocol);

  free_detected_device_list(list);
  return true;
}

void revo3_close(Revo3Context &ctx) {
  if (!ctx.handle) {
    return;
  }

  close_device_handler(ctx.handle, static_cast<uint8_t>(ctx.protocol));
  ctx.handle = nullptr;
}

void revo3_print_device_info(DeviceHandler *handle, uint8_t slave_id) {
  CDeviceInfo *info = stark_get_device_info(handle, slave_id);
  if (!info) {
    std::printf("[WARN] Failed to read device info.\n");
    return;
  }

  std::printf("Serial:   %s\n", info->serial_number ? info->serial_number : "");
  std::printf("Firmware: %s\n", info->firmware_version ? info->firmware_version : "");
  std::printf("Hardware: %s (%u)\n", revo3_hw_type_name(info->hardware_type),
              static_cast<unsigned>(info->hardware_type));
  std::printf("Side:     %s\n", info->hand_type == HAND_TYPE_RIGHT ? "Right" : "Left");

  free_device_info(info);
}

void revo3_sleep_ms(int ms) {
  std::this_thread::sleep_for(std::chrono::milliseconds(ms));
}
