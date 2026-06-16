# Revo3 C++ Examples

These examples use the C ABI from `dist/include/stark-sdk.h` in C++ programs.
They are Revo3-only and cover Modbus, CANFD auto-detect, motor control, touch data, and buffered monitoring.

## Build

From the repository root:

```bash
sh download-lib.sh
make -C c
```

## Run

Auto-detect:

```bash
./c/demo/auto_detect
./c/demo/auto_detect --stream
./c/demo/hand_demo
./c/demo/hand_trajectory
./c/demo/hand_dfu firmware.bin
./c/demo/revo3_motor
./c/demo/revo3_touch
./c/demo/revo3_monitor
./c/demo/revo3_servo
```

`--stream` uses `revo3_auto_detect_start()` and prints each device as soon as
it is found. Add `--stop-on-first` for quick-connect behavior, `--verbose` to
show SDK scan logs, or `--modbus-baudrate 5000000` to probe one known Modbus
baudrate.

Minimal streaming usage:

```cpp
struct ScanState {
  bool selected = false;
};

bool on_device_found(const CDetectedDevice *device, void *user_data) {
  auto *state = static_cast<ScanState *>(user_data);
  std::printf("Found %s slave=%u\n", device->port_name, device->slave_id);
  state->selected = true;
  return false; // stop scanning after this device
}

ScanState state;
Revo3AutoDetectHandle *scan = revo3_auto_detect_start(
    true,
    nullptr,
    STARK_PROTOCOL_TYPE_AUTO,
    0,
    0,
    true, // broadcast
    on_device_found,
    &state);

revo3_auto_detect_join(scan);
revo3_auto_detect_free_handle(scan);
```

The `CDetectedDevice` pointer passed to the callback is valid only during the
callback. Copy fields you need before returning.

Pass a non-zero `slave_id` to `revo3_auto_detect_start()` or
`stark_auto_detect()` to probe only one known slave ID. Pass `0` to probe the
default Revo3 IDs. Pass a non-zero `modbus_baudrate`, such as `5000000`, to
probe only one known Modbus baudrate; pass `0` to probe the default list.

For GUI or event-loop applications, keep the handle instead of joining
immediately:

```cpp
Revo3AutoDetectHandle *scan = revo3_auto_detect_start(
    false,
    nullptr,
    STARK_PROTOCOL_TYPE_AUTO,
    0,
    0,
    true, // broadcast
    on_device_found,
    &state);

// UI keeps running. When the user chooses a device or cancels:
revo3_auto_detect_stop(scan);
revo3_auto_detect_join(scan);
revo3_auto_detect_free_handle(scan);
```

Manual Modbus:

```bash
./c/demo/hand_demo --modbus /dev/ttyUSB0 5000000 1
./c/demo/hand_trajectory --modbus /dev/ttyUSB0 5000000 1
./c/demo/hand_dfu --modbus /dev/ttyUSB0 5000000 1 firmware.bin
./c/demo/revo3_motor --modbus /dev/ttyUSB0 5000000 1
./c/demo/revo3_touch --modbus /dev/ttyUSB0 5000000 1
./c/demo/revo3_monitor --modbus /dev/ttyUSB0 5000000 1
./c/demo/revo3_servo --modbus /dev/ttyUSB0 5000000 1
```

The examples intentionally avoid legacy transports and APIs.

## Zero Position

There are two separate APIs for zero-position calibration:
1. `revo3_set_zero_position`: Writes explicit offset values in degrees for all 21 motors to registers 60~80, and registers them to take effect.
2. `revo3_set_current_position_as_zero`: Registers the current feedback positions as zero (register 81).
   * **Recommended Workflow**: Disable motors -> manually pose the hand -> enable motors -> call this API to lock in the zero pose.

```cpp
// 1. Set explicit offsets
float offsets_deg[21] = {0.0f};
revo3_set_zero_position(handle, slave_id, offsets_deg);

// 2. Set current position as zero (requires clamping/posing)
// Step 1: Disable motors
// Step 2: Manually pose hand to zero-reference
// Step 3: Enable motors
revo3_set_current_position_as_zero(handle, slave_id);
```
