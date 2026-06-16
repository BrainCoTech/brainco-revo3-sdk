#include "../common/revo3_common.h"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <string>

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
  std::printf("  %s [--scan-all] [--stream] [--stop-on-first] [--verbose] [--broadcast] [--port <name>] [--slave-id <id>] [--modbus-baudrate <bps>] [--protocol auto|modbus|canfd|ethercat]\n", program);
}

void print_device(size_t index, const CDetectedDevice &device) {
  std::printf("[%zu] %s %s slave=%u baud=%u data_baud=%u hw=%s serial=%s fw=%s\n",
              index,
              protocol_name(device.protocol),
              device.port_name ? device.port_name : "",
              device.slave_id,
              device.baudrate,
              device.data_baudrate,
              revo3_hw_type_name(device.hardware_type),
              device.serial_number ? device.serial_number : "",
              device.firmware_version ? device.firmware_version : "");
}

struct StreamState {
  size_t count = 0;
  bool select_first = false;
  bool selected = false;
  StarkProtocolType protocol = STARK_PROTOCOL_TYPE_AUTO;
  std::string port_name;
  uint8_t slave_id = 0;
  uint32_t baudrate = 0;
  uint32_t data_baudrate = 0;
  StarkHardwareType hardware_type = static_cast<StarkHardwareType>(0);
  SkuType sku_type = static_cast<SkuType>(0);
  std::string serial_number;
  std::string firmware_version;
};

bool on_device_found(const CDetectedDevice *device, void *user_data) {
  if (!device || !user_data) {
    return false;
  }

  auto *state = static_cast<StreamState *>(user_data);
  state->count += 1;
  print_device(state->count, *device);
  if (!state->select_first || state->selected) {
    return true;
  }

  state->selected = true;
  state->protocol = device->protocol;
  state->port_name = device->port_name ? device->port_name : "";
  state->slave_id = device->slave_id;
  state->baudrate = device->baudrate;
  state->data_baudrate = device->data_baudrate;
  state->hardware_type = device->hardware_type;
  state->sku_type = device->sku_type;
  state->serial_number = device->serial_number ? device->serial_number : "";
  state->firmware_version = device->firmware_version ? device->firmware_version : "";
  return false;
}

CDetectedDevice to_c_detected_device(const StreamState &state) {
  CDetectedDevice device{};
  device.protocol = state.protocol;
  device.port_name = const_cast<char *>(state.port_name.c_str());
  device.slave_id = state.slave_id;
  device.baudrate = state.baudrate;
  device.data_baudrate = state.data_baudrate;
  device.hardware_type = state.hardware_type;
  device.sku_type = state.sku_type;
  device.serial_number = state.serial_number.empty() ? nullptr : const_cast<char *>(state.serial_number.c_str());
  device.firmware_version = state.firmware_version.empty() ? nullptr : const_cast<char *>(state.firmware_version.c_str());
  return device;
}

} // namespace

int main(int argc, char **argv) {
  bool scan_all = false;
  bool stream = false;
  bool stop_on_first = false;
  bool verbose = false;
  bool broadcast = false;
  uint8_t slave_id_filter = 0;
  uint32_t modbus_baudrate_filter = 0;
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
    if (std::strcmp(argv[i], "--stream") == 0) {
      stream = true;
      continue;
    }
    if (std::strcmp(argv[i], "--stop-on-first") == 0) {
      stop_on_first = true;
      continue;
    }
    if (std::strcmp(argv[i], "--verbose") == 0) {
      verbose = true;
      continue;
    }
    if (std::strcmp(argv[i], "--broadcast") == 0) {
      broadcast = true;
      continue;
    }
    if (std::strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
      port = argv[++i];
      continue;
    }
    if (std::strcmp(argv[i], "--slave-id") == 0 && i + 1 < argc) {
      slave_id_filter = static_cast<uint8_t>(std::strtoul(argv[++i], nullptr, 0));
      continue;
    }
    if (std::strcmp(argv[i], "--modbus-baudrate") == 0 && i + 1 < argc) {
      modbus_baudrate_filter = static_cast<uint32_t>(std::strtoul(argv[++i], nullptr, 0));
      continue;
    }
    if (std::strcmp(argv[i], "--protocol") == 0 && i + 1 < argc) {
      protocol = parse_protocol(argv[++i]);
      continue;
    }
    print_usage(argv[0]);
    return 1;
  }

  init_logging(verbose ? LOG_LEVEL_INFO : LOG_LEVEL_WARN);

  std::printf("=== Revo3 C++ Auto Detect ===\n");
  if (stream) {
    StreamState state;
    state.select_first = stop_on_first;
    Revo3AutoDetectHandle *scan = revo3_auto_detect_start(
        stop_on_first,
        port,
        protocol,
        slave_id_filter,
        modbus_baudrate_filter,
        broadcast,
        on_device_found,
        &state);
    if (!scan) {
      std::printf("Failed to start streaming auto-detect.\n");
      return 1;
    }

    // This CLI demo waits synchronously so the process can print all streaming
    // results before exiting. GUI applications should keep the handle, return
    // to the event loop, and call stop/join/free when the user selects a device
    // or cancels scanning.
    revo3_auto_detect_join(scan);
    revo3_auto_detect_free_handle(scan);

    if (state.count == 0) {
      std::printf("No Revo3 device detected.\n");
      return 1;
    }

    if (state.selected) {
      CDetectedDevice selected = to_c_detected_device(state);
      DeviceHandler *handle = init_from_detected(&selected);
      if (handle) {
        std::printf("\nInitialized selected streaming device and read device info:\n");
        revo3_print_device_info(handle, selected.slave_id);
        close_device_handler(handle, static_cast<uint8_t>(selected.protocol));
      }
    }
    return 0;
  }

  CDetectedDeviceList *list = stark_auto_detect(
      scan_all,
      port,
      protocol,
      slave_id_filter,
      modbus_baudrate_filter,
      broadcast);
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
    print_device(i + 1, device);
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
