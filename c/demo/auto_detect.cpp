#include "../common/revo3_common.h"

#include <cstdio>
#include <cstring>

namespace {

StarkProtocolType parse_protocol(const char *value) {
  if (!value || std::strcmp(value, "auto") == 0) {
    return STARK_PROTOCOL_TYPE_AUTO;
  }
  if (std::strcmp(value, "modbus") == 0) {
    return STARK_PROTOCOL_TYPE_MODBUS;
  }
  if (std::strcmp(value, "canfd") == 0) {
    return STARK_PROTOCOL_TYPE_CAN_FD;
  }
  if (std::strcmp(value, "ethercat") == 0) {
    return STARK_PROTOCOL_TYPE_ETHER_CAT;
  }
  return STARK_PROTOCOL_TYPE_AUTO;
}

const char *protocol_name(StarkProtocolType protocol) {
  switch (protocol) {
  case STARK_PROTOCOL_TYPE_MODBUS:
    return "Modbus";
  case STARK_PROTOCOL_TYPE_CAN_FD:
    return "CANFD";
  case STARK_PROTOCOL_TYPE_ETHER_CAT:
    return "EtherCAT";
  default:
    return "Auto";
  }
}

void print_usage(const char *program) {
  std::printf("Usage:\n");
  std::printf("  %s [--scan-all] [--port <name>] [--protocol auto|modbus|canfd|ethercat]\n", program);
}

} // namespace

int main(int argc, char **argv) {
  init_logging(LOG_LEVEL_INFO);

  bool scan_all = false;
  const char *port = nullptr;
  StarkProtocolType protocol = STARK_PROTOCOL_TYPE_AUTO;

  for (int i = 1; i < argc; ++i) {
    if (std::strcmp(argv[i], "--help") == 0) {
      print_usage(argv[0]);
      return 0;
    }
    if (std::strcmp(argv[i], "--scan-all") == 0) {
      scan_all = true;
      continue;
    }
    if (std::strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
      port = argv[++i];
      continue;
    }
    if (std::strcmp(argv[i], "--protocol") == 0 && i + 1 < argc) {
      protocol = parse_protocol(argv[++i]);
      continue;
    }
    print_usage(argv[0]);
    return 1;
  }

  std::printf("=== Revo3 C++ Auto Detect ===\n");
  CDetectedDeviceList *list = stark_auto_detect(scan_all, port, protocol);
  if (!list || list->count == 0) {
    std::printf("No Revo3 device detected.\n");
    if (list) {
      free_detected_device_list(list);
    }
    return 1;
  }

  std::printf("Found %zu Revo3 device(s):\n", list->count);
  for (size_t i = 0; i < list->count; ++i) {
    const CDetectedDevice &device = list->devices[i];
    std::printf("[%zu] %s %s slave=%u baud=%u data_baud=%u hw=%s serial=%s fw=%s\n",
                i + 1,
                protocol_name(device.protocol),
                device.port_name ? device.port_name : "",
                device.slave_id,
                device.baudrate,
                device.data_baudrate,
                revo3_hw_type_name(device.hardware_type),
                device.serial_number ? device.serial_number : "",
                device.firmware_version ? device.firmware_version : "");
  }

  DeviceHandler *handle = init_from_detected(&list->devices[0]);
  if (handle) {
    std::printf("\nInitialized first device and read device info:\n");
    revo3_print_device_info(handle, list->devices[0].slave_id);
    close_device_handler(handle, static_cast<uint8_t>(list->devices[0].protocol));
  }

  free_detected_device_list(list);
  return 0;
}
