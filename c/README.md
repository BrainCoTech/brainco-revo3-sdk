# Revo3 C and C++ Examples

The public C ABI header is C11 compatible. C++ examples require a C++17
compliant compiler or newer and use the RAII wrapper from
`dist/include/revo3/revo3.hpp`. They are Revo3-only and cover Modbus and CANFD
discovery, device operations, motion, state, and touch data.

The independent Linux EtherCAT example under `platform/linux/revo3_ec` uses
IgH `libethercat` directly and does not depend on the Rust SDK shared library.

## Build

From the repository root:

```bash
bash download-lib.sh
make -C c
```

Use `dist/include/revo3-sdk.h` for pure C projects, embedded C projects, and
cross-language bindings. C++ applications can include `revo3/revo3.hpp` for
the move-only `revo3::Manager`, `revo3::Hand`, and `revo3::OperationHandle` API.
The C++ object methods omit the redundant `revo3_` prefix; only C ABI symbols
retain it.

Minimal C++ usage:

```cpp
#include <revo3/revo3.hpp>

#include <cstdio>

int main() {
  try {
    revo3::Manager manager;
    auto hand = manager.connect_auto();
    const auto device_info = hand.device_info();
    const auto state = hand.state().snapshot();
    const auto health = hand.health().snapshot();
    std::printf("Connected to %s with %zu motor values; safety=%u\n",
                device_info.serial_number.c_str(), state.motors.positions_deg.size(),
                static_cast<unsigned>(health.safety_state));
    return 0;
  } catch (const revo3::SdkError &error) {
    std::fprintf(stderr, "Revo3 error: %s\n", error.what());
    return 1;
  }
}
```

Use one of `move_joint()`, `flex_finger()`, or `move_thumb()` instead when the
application needs a narrower motion scope. The `quickstart` flags demonstrate
each alternative without starting overlapping motions.

`move_to()` returns immediately with a handle, so the C++ API does not need
coroutines for the core motion path. A future C++20 async adapter should only be
added after discovery, subscriptions, cancellation, and executor behavior are
truly asynchronous end to end.

Build the pure C++ EtherCAT example on Linux:

```bash
make -C c/platform/linux/revo3_ec
```

Before running it, verify the IgH master, `/dev/EtherCAT0`, and the selected
NIC with `c/platform/linux/revo3_ec/README.md`.

Run the standalone EtherCAT benchmark:

```bash
./c/platform/linux/revo3_ec/revo3_benchmark \
  --scenario motor --read full-state --duration 10
```

## Run

Device discovery and examples:

```bash
./c/build/demo/quickstart
./c/build/demo/discover_devices --scan-all
./c/build/demo/subscriptions --count 3
./c/build/demo/multi_hand
./c/build/demo/device_operations
./c/build/demo/firmware_update --firmware <FILE> --target main --run
./c/build/demo/touch_sensor
./c/build/demo/touch_hybrid
./c/build/demo/streaming_control --move
./c/build/demo/mit_plan --run
./c/build/demo/teaching_mode --move
```

`firmware_update` is the standalone destructive maintenance workflow. It
supports `main`, `image`, and `motor` targets, defaults to a 600-second
operation timeout, and refuses to connect unless `--run` is present. If the
result is `Indeterminate`, do not immediately retry: inspect the reported
operation effect and recovery requirement, then verify device state.

`mit_plan` runs the same default plan as the Python `mit_plan.py` example:
a 100 Hz quintic trajectory from the initial feedback position to the 50% point
of each target joint's configured position range and back, with 800 ms per
segment, `Kp=3.0`, `Kd=0.3`, and zero feedforward current. Invalid position
or speed limits, including a quintic peak velocity above the configured speed
envelope, stop the example before opening the ServoSession. The demo reuses
`common/revo3_mit_plan.hpp`, which is also shared with the EtherCAT example,
and prints periodic position feedback plus the measured command rate.

`touch_hybrid` requires a confirmed `hp_*` + `mt_*` hardware layout. It changes
only the current SDK session's parsing layout by default. Pass `--test-tare`
only when changing touch calibration state is intended.

`discover_devices` stops after the first match by default. Add `--scan-all` to
scan every candidate. Use `--port`, `--protocol`, `--slave-id`,
`--modbus-baudrate`, or `--canfd-data-baudrate` to constrain the scan. By
default, CANFD auto-detect tries data baudrates in order:
`5M`, `4M`, `2M`, `1M` on adapters that support them. BrainCo USB2CANFD
supports only `5M`; add `--canfd-data-baudrate 2000000` to probe only one
known CANFD data baudrate on compatible adapters.

`subscriptions` performs finite State, optional Touch, and Health pull
subscriptions, closes each subscription explicitly, and prints the resulting
runtime counters. The requested period is a minimum SDK pull interval, not a
device sampling-rate guarantee.

For lower-level C integrations that need callback delivery or cancellation
before discovery completes, use the asynchronous C ABI directly:

```cpp
struct ScanState {
  bool selected = false;
};

bool on_device_found(const CRevo3DetectedDevice *device, void *user_data) {
  auto *state = static_cast<ScanState *>(user_data);
  std::printf("Found %s slave=%u\n", device->port_name, device->slave_id);
  state->selected = true;
  return false; // stop scanning after this device
}

ScanState state;
Revo3AutoDetectHandle *scan = revo3_auto_detect_start(
    true,
    nullptr,
    REVO3_PROTOCOL_TYPE_AUTO,
    0,
    0,
    0,
    true, // broadcast
    on_device_found,
    &state);

revo3_auto_detect_join(scan);
revo3_auto_detect_free_handle(scan);
```

The `CRevo3DetectedDevice` pointer passed to the callback is valid only during the
callback. Copy fields you need before returning.

Pass a non-zero `slave_id` to `revo3_auto_detect_start()` to probe only one
known slave ID. Pass `0` to probe the default Revo3 IDs. Pass a non-zero
`modbus_baudrate`, such as `5000000`, to probe only one known Modbus baudrate;
pass `0` to probe the default list.
Pass a non-zero `canfd_data_baudrate`, such as `2000000`, to probe only one
known CANFD data baudrate; pass `0` to probe the default CANFD data baudrate
list (`5M`, `4M`, `2M`, `1M`).

For GUI or event-loop applications, keep the handle instead of joining
immediately:

```cpp
Revo3AutoDetectHandle *scan = revo3_auto_detect_start(
    false,
    nullptr,
    REVO3_PROTOCOL_TYPE_AUTO,
    0,
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

## Troubleshooting & Serial Port Cleanup

If `connect_auto` or device scanner fails with `Failed to open ... at 5000000 bps: Invalid argument` or `No Revo3 device detected`, it typically indicates an active background process (e.g. from a previously killed shell or interrupted debug session) holding an open handle on the physical serial port `/dev/tty.usbserial-*`.

To inspect and release the occupied serial port:

```bash
# 1. Find process holding the serial port
lsof /dev/tty.usbserial*

# 2. Terminate the zombie process
kill -9 <PID>
```

Always ensure `hand.close()` and `manager.close()` are called on application exit, and handle `SIGINT` (Ctrl+C) signals appropriately to release underlying OS file descriptors cleanly.
