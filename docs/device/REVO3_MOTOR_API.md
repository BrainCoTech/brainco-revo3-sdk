# Revo3 Motor Protocol and Register Reference

This document describes the internal Modbus/CANFD motor register contract used
by the SDK. It is not a public C, C++, or Python API reference. Applications
should use the 2.0 `Manager` / `Hand` object API documented in
[Revo3 SDK 2.0 API Reference](../api/REVO3_API.zh-CN.md), or the generated C ABI
in `dist/include/revo3-sdk.h`.

The SDK supports the current Revo3 motor families: Ultra (21 DOF), Pro (16 DOF),
and Basic (13 DOF). Ultra and Pro production models are released; Ultra
VisionTouch and Basic variants remain Hardware Pilot products. Applications
must use `DeviceInfo.model` and `JointLayout` to determine the connected model
and active joint count instead of assuming a fixed 21-joint layout.

## Physical Units and Naming

| Quantity | Public unit | Wire encoding |
| --- | --- | --- |
| Position | degree | signed value multiplied by 100 |
| Velocity | rpm | signed value multiplied by 100 |
| `Kp`, `Kd` | device coefficient | unsigned value multiplied by 100 |
| Motor current | mA | signed integer, no scale factor |
| Temperature | degree C | unsigned integer, no scale factor |

The device reports motor current in mA. It does not report calibrated joint
torque in Nm, and the SDK does not apply a motor-current-to-joint-torque model.
Consequently, public feedback fields remain `current` / `current_ma`.

The last term in an MIT command is also an electrical feedforward current in
mA. Some legacy protocol notes called this field "torque" because it influences
motor torque, but it is not a measured or calibrated joint-torque value. SDK
2.0 names it `feedforward_current_ma`.

## Logical Joint Order

Public arrays use this fixed 21-joint logical order:

| Group | Logical joints | Count |
| --- | --- | ---: |
| Pinky | J0..J3 | 4 |
| Ring | J4..J7 | 4 |
| Middle | J8..J11 | 4 |
| Index | J12..J15 | 4 |
| Thumb | J16..J20 | 5 |

For each non-thumb finger the logical order is Abd, MCP, PIP, DIP. Finger
indexing in object APIs is Thumb=0, Index=1, Middle=2, Ring=3, Pinky=4. The
four non-thumb controller blocks are stored Pinky first; the adapter converts a
finger index with `(4 - finger_index) * 4`.

The public Thumb order is Rotation, MCP, IP, Abd, Flex. Its controller channels
are 4, 3, 0, 1, 2 respectively. This mapping is internal and must not leak into
application arrays.

## Control Modes

| Value | Mode | Parameter |
| ---: | --- | --- |
| 0 | Position | target position in degree |
| 1 | Velocity | target velocity in rpm |
| 2 | Current | target motor current in mA |
| 4 | Impedance | `Kp` coefficient |
| 5 | Damping | `Kd` coefficient |

## Command Registers

| Address | Count | Internal payload |
| --- | ---: | --- |
| 1000..1002 | 3 | joint ID, mode, parameter |
| 1010..1031 | 22 | mode plus 21 joint parameters |
| 1050..1055 | 6 | joint ID, `Kp`, `Kd`, position, velocity, feedforward current |
| 1100..1204 | 105 | 21 interleaved MIT tuples: `Kp`, `Kd`, position, velocity, feedforward current |
| 1300..1320 | 21 | grouped MIT `Kp` values |
| 1321..1341 | 21 | grouped MIT `Kd` values |
| 1342..1362 | 21 | grouped MIT positions |
| 1363..1383 | 21 | grouped MIT velocities |
| 1384..1404 | 21 | grouped MIT feedforward currents in mA |
| 1500..1505 | 6 | non-thumb finger selector, mode, four parameters |
| 1510..1515 | 6 | Thumb mode and five parameters |
| 1520..1540 | 21 | non-thumb finger selector and four MIT tuples |
| 1550..1574 | 25 | five Thumb MIT tuples |

The 1100 block is interleaved by joint. The 1300 block is grouped by
parameter. Mixing these layouts can produce valid writes with invalid motion,
so the public SDK exposes typed operations rather than raw arrays.

## Configuration Registers

| Address | Count | Description |
| --- | ---: | --- |
| 60..80 | 21 | joint zero offsets in degree |
| 81 | 1 | set current feedback positions as zero; write 1 |
| 200 | 1 | global protection current in mA |
| 201..221 | 21 | per-joint protection current in mA |
| 240..260 | 21 | minimum joint positions |
| 270..290 | 21 | maximum joint positions |
| 300..320 | 21 | minimum joint velocities in rpm |
| 321..341 | 21 | maximum joint velocities in rpm |

## Feedback Registers

| Address | Count | Description |
| --- | ---: | --- |
| 2000..2020 | 21 | motor operating-state bitmasks |
| 2030..2050 | 21 | motor velocities in rpm, signed value multiplied by 100 |
| 2060..2080 | 21 | motor positions in degree, signed value multiplied by 100 |
| 2090..2110 | 21 | motor currents in mA |
| 2120..2140 | 21 | motor fault codes |
| 2150..2170 | 21 | motor temperatures in degree C |
| 3020..3021 | 2 | motor-online bitmask |
| 3030..3039 | 10 | controller firmware version, ASCII |
| 3040..3049 | 10 | hardware revision, ASCII |
| 3050..3059 | 10 | hand serial number, ASCII |
| 3060..3269 | 210 | 21 motor serial numbers, 10 registers each |

## Motor Status Bitmask

Each motor status is a `u16` bitmask. The Running bit is status, not an error,
and is excluded from SDK motor-error counts.

| Bit | Flag | Meaning |
| ---: | --- | --- |
| 0 | OverCurrent | sustained over-current condition |
| 1 | OverVoltage | supply voltage above allowed range |
| 2 | UnderVoltage | supply voltage below allowed range |
| 3 | OverTemperature | motor temperature protection active |
| 4 | CurrentSpike | peak-current protection active |
| 5..7 | Reserved | do not interpret |
| 8 | Stalled | motor stall or obstruction reported |
| 9..10 | Reserved | do not interpret |
| 11 | Running | motor is active; not an error |
| 12..15 | Reserved | do not interpret |

Exact protection thresholds and recovery behavior are firmware properties and
must be validated against the firmware release used by the device. SDK-side
experimental collision detection is a separate, non-safety-rated feature; see
[Collision Detection](REVO3_COLLISION_DETECTION.md).

## Transport and Retry Semantics

Modbus and CANFD share the logical register model but use different transport
framing. Normal configuration writes may use the SDK retry policy. Streaming
MIT writes avoid automatic replay because a late retry can apply stale motion.
Applications should use `Motion.open_servo()` / `motion().open_servo()` and its
send timeout rather than depending on internal no-retry functions.
