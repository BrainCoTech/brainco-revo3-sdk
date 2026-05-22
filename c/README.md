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
./c/demo/hand_demo
./c/demo/hand_trajectory
./c/demo/hand_dfu firmware.bin
./c/demo/revo3_motor
./c/demo/revo3_touch
./c/demo/revo3_monitor
./c/demo/revo3_servo
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

`revo3_set_zero_position` supports both Revo3 zero-position modes. Passing
`NULL` writes register 81 and lets the device use current feedback positions as
zero. Passing a pointer to 21 `float` values writes zero offset values in
degrees to registers 60~80.

```cpp
// Persistent calibration change: use only in the intended reference pose.
revo3_set_zero_position(handle, slave_id, NULL);

float offsets_deg[21] = {0.0f};
revo3_set_zero_position(handle, slave_id, offsets_deg);
```
