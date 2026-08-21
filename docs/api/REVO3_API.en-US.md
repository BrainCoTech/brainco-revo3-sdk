# Revo3 SDK API Reference Manual

> API Version: 2.0.0
>
> Language: [简体中文 (`zh-CN`)](REVO3_API.zh-CN.md) | English (`en-US`)

This specification defines the object model, method signatures, and invocation specs for the BrainCo Revo3 SDK public API.

## 1. Overview & Scope

### 1.1 Hardware Support & Capabilities

SDK 2.0 recognizes the Revo3 Ultra (21 DOF), Pro (16 DOF), and Basic (13 DOF)
families and reports their logical joint count and layout through `JointLayout`.
The current SDK runtime enables feature domains only for the 21-DOF Ultra
family. Pro and Basic currently expose identity and `JointLayout`; other
runtime capabilities remain fail-closed. Unverified capabilities report
`NotVerified`, while capabilities without corresponding hardware report
`HardwareMissing`. Product lifecycle and SDK runtime support are
independent: Ultra, Ultra Touch, Pro, and Pro Touch are released products,
while Ultra VisionTouch, Basic, and Basic Touch are Hardware Pilot products.

Ultra VisionTouch hand motion, state, and maintenance use the same hand
transport as other Ultra models. Vision-tactile fingertip data is supplied by a
separate vendor SDK over another USB or serial connection; it does not traverse
this SDK's Modbus/CANFD transport and is not exposed by `hand.touch`. The two
channels have independent lifecycles and no atomic timestamp guarantee.

| Product Line | DoF | Tactile Sensing | Product Status | SDK Runtime Status |
| --- | ---: | --- | --- | --- |
| Revo3 Ultra | 21 | None | Released | Supported |
| Revo3 Ultra Touch | 21 | Integrated array touch | Released | Supported |
| Revo3 Ultra VisionTouch | 21 | Vendor SDK over separate USB/serial | Hardware Pilot | Hand functions supported; vision touch external |
| Revo3 Pro / Pro Touch | 16 | Integrated touch on Touch SKU | Released | Identity and `JointLayout` only; runtime domains are not enabled |
| Revo3 Basic / Basic Touch | 13 | Integrated touch on Touch SKU | Hardware Pilot | Identity and `JointLayout` only; runtime domains are not enabled |

### 1.2 Object Model Architecture

[`Manager`](#21-manager) serves as the device manager handling device discovery and connection lifecycles; [`Hand`](#22-hand) represents the device handle for a single dexterous hand, providing device metadata and feature domain objects:

```text
Manager (Device Discovery & Connection Management)
└── Hand (Single Hand Device Handle)
    ├── Device Information & Metadata
    │   ├── DeviceInfo           Physical identity for the hand, motors & touch modules
    │   ├── FirmwareInfo         Controller, motor & touch firmware versions
    │   └── JointLayout          Joint mapping & topology
    └── Feature Domain Objects
        ├── Motion               Trajectory motion, real-time streaming, zero force & Software Stop
        ├── State                Motor feedback snapshots & subscriptions
        ├── Touch                Tactile array & force-torque sensor sampling
        ├── Health               System diagnostics, motor health & runtime health state
        ├── ExperimentalCollision Experimental SDK-side collision detection
        ├── Config               Device settings & runtime options
        ├── Calibration          Joint zero calibration
        └── Maintenance          Device reboot & firmware updates
```

The diagram above illustrates feature ownership; exact signatures appear in Sections 2 through 5.

## 2. Core Entry Objects & Basic Usage

[`Manager`](#21-manager) and [`Hand`](#22-hand) form the core entry objects of SDK 2.0, responsible for device discovery, session establishment, and handle lifecycle management.

### 2.1 Manager

Applications create a `Manager` instance to perform discovery, connection management, and handle lifecycles:

- **Discovery & Connection**:
  - `list_ports()`: Enumerates visible communication ports or adapters for UI, CLI, or manual port selection. It does not probe devices or return `Hand` instances.
  - `discover(scan_all=False)`: Scans for available bus devices (returning port name, transport protocol, and `slave_id`). Stops at the first device by default; set `scan_all=True` to scan all devices.
  - `connect_auto()`: Discovers and connects to a matching device, ideal for quickstarts and single-hand defaults. Accepts optional `port`, `slave_id`, `protocol`, or `model` filters.
  - `connect(detected, model=None)`: Connects to a known `DetectedDevice`, useful when the app calls `discover()` first to present a device picker to the user.
  - `connect_all(devices)`: Connects to multiple known devices in batch and returns `list[Hand]`. This supports multiple hands on one bus and multiple Modbus ports.
- **Bus Sharing & Lifecycle Rules**:
  - **Port Isolation & Sharing**: Opens only one Transport connection per physical port (such as RS485 or CANFD). Multiple `Hand` handles (different `slave_id`) on the same bus share this connection.
  - **CANFD Session Limit**: A process may have only one active CANFD Transport session. Multiple `slave_id` values on that CANFD bus share the session. Close it before connecting another CANFD adapter or starting CANFD discovery; a session also cannot be created while CANFD discovery is running. This limit does not apply to Modbus.
  - **Independent Close**: Closing a single `Hand` releases only that handle and its references. The SDK releases the underlying bus connection only after the last `Hand` on that port is closed.
  - **Global Cleanup**: Closing `Manager` atomically closes all managed `Hand` handles and underlying physical connections.
  - **Disconnection & Invalidations**: After bus disconnects and reconnection recoveries, previous `Hand` handles, subscriptions, and caches automatically invalidate, requiring the application to re-obtain a handle.

### 2.2 Hand

`Hand` is the active handle for a connected robotic hand, aggregating read-only metadata snapshots and functional domain sub-modules:

```text
Hand / revo3::Hand
├── device_info / device_info()       --> Basic device info (model/SN/hand_side/hw_ver)
├── firmware_info / firmware_info()   --> Firmware versions (controller/drivers/touch)
├── joint_layout / joint_layout()     --> Joint topology & mapping (21 DoF logical order)
├── slave_id / slave_id()             --> Modbus slave ID
├── motion / motion()                 --> Motion control API (move_to, move_joint, teach)
├── state / state()                   --> Status & telemetry API (snapshot state)
├── touch / touch()                   --> Tactile sensing API (layout, stream & maintenance)
├── health / health()                 --> Health & safety diagnostics API
├── experimental_collision / experimental_collision() --> Experimental collision API
├── config / config()                 --> Device parameter configuration API
├── calibration / calibration()       --> Joint zeroing & calibration API
├── maintenance / maintenance()       --> Firmware OTA & DFU maintenance API
└── close()                           --> Close handle & release connection
```

- **Resource Ownership**: Supports calling `close()` to release the handle; multiple devices on the same bus share a single connection, so closing one `Hand` does not affect other hands on the same port.

### 2.3 Basic Usage

Revo3 SDK provides consistent object-oriented basic usage patterns across Python and C++:

#### Python Basic Usage

```python
import asyncio
from bc_revo3_sdk import main_mod as sdk


async def main():
    manager = sdk.Manager()
    hand = None
    try:
        hand = await manager.connect_auto()

        # 1. Read device metadata and layout
        info = hand.device_info
        layout = hand.joint_layout
        if layout is None:
            raise RuntimeError("Joint layout is unavailable")
        print(f"Hand Model: {info.model}, SN: {info.serial_number}")

        # 2. Build a target from the latest state snapshot
        state = await hand.state.snapshot()
        target = list(state.positions_deg)
        target[0] = 45.0  # Target angle for J0 in degrees

        # 3. Dispatch one motion command and wait for completion
        handle = await hand.motion.move_to(target, duration=0.8)
        result = await handle.wait(timeout=2.0)
        print(f"Motion result: {result}")
    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


asyncio.run(main())
```

#### C++ Basic Usage

```cpp
#include <iostream>
#include <revo3/revo3.hpp>
#include <stdexcept>
#include <vector>

using namespace std::chrono_literals;

int main() {
    revo3::Manager manager;
    auto hand = manager.connect_auto();

    // 1. Read device metadata and layout
    const auto info = hand.device_info();
    std::cout << "Hand Model: " << static_cast<int>(info.model)
              << ", SN: " << info.serial_number << "\n";

    // 2. Build a safe motion target from state snapshot
    auto state = hand.state().snapshot();
    const auto layout = hand.joint_layout();
    if (!layout) {
        throw std::runtime_error("Joint layout is unavailable");
    }
    std::vector<float> target(
        state.motors.positions_deg,
        state.motors.positions_deg + layout->joint_count);
    target[0] = 45.0f;  // Target angle for J0 in degrees

    // 3. Dispatch motion command and wait for completion
    auto handle = hand.motion().move_to(target, 800ms);
    const auto result = handle.wait(2s);
    std::cout << "Motion result status: " << static_cast<int>(result) << "\n";

    // 4. Release handle & resources
    hand.close();
    return 0;
}
```

## 3. Device View & Metadata

Device info and metadata are provided across two lifecycle stages: **Device Discovery** and **Device Connection**:

- **Device Discovery Stage**: Returned by `Manager.discover()` as [`DetectedDevice`](#31-discovered-device-detecteddevice), capturing endpoint parameters and baseline descriptors for connection input;
- **Device Connection Stage**: After establishing a connection via `connect()` or `connect_auto()`, accessed via the [`Hand`](#22-hand) handle.

### 3.1 Discovered Device (DetectedDevice)

```text
DetectedDevice / revo3::DetectedDevice
├── protocol_type                      --> Transport protocol type (ModbusRTU / CANFD)
├── port_name                          --> Serial port or CAN interface name (e.g. /dev/ttyUSB0, can0)
├── slave_id                           --> Device Modbus slave ID
├── nominal_baudrate_bps              --> RS485 baudrate or CAN nominal baudrate (e.g. 115200, 1000000)
├── data_baudrate_bps                 --> CANFD data-phase baudrate (e.g. 5000000)
├── model                              --> Detected device model (e.g. UltraTouch)
├── hand_side                          --> Detected hand side (Left / Right)
├── serial_number                      --> Device unique serial number (e.g. BCUTL40124000001)
├── firmware_version                   --> Controller firmware version
└── hardware_revision                   --> Hardware revision identifier
```

### 3.2 Device Info (DeviceInfo)

```text
DeviceInfo
├── model                              --> Product model (e.g. UltraTouch)
├── serial_number                      --> Device unique serial number (e.g. BCUTL40124000001)
├── hand_side                          --> Hand side (Left / Right)
├── hardware_revision                   --> Hardware revision identifier
├── motor_serial_numbers               --> Motor serial number list
└── touch_serial_numbers               --> Touch module serial number list
```

`DeviceInfo` is a snapshot of basic info and hardware metadata for the connected device, used for device identification, logging traceability, and compatibility diagnostics. The snapshot is automatically fetched and cached upon connection; calling `await hand.refresh_device_info()` is required only during factory testing, servicing, or forced sync.

If the device serial number or hardware version is missing, `hand.device_info` returns `None` (without faking info via empty strings). Unread or unsupported component serial numbers appear as empty lists `[]` without blocking `DeviceInfo` creation.

#### Field Specifications

- **`model`**: Product model ([`Revo3Model`](#35-product-model-enum-revo3model)), determining product line, degree-of-freedom count, and touch configuration.
- **`serial_number`**: Device unique serial number (e.g. `"BCUTL40124000001"`), used for device identification, multi-hand logging, and asset management.
- **`hand_side`**: Hand side (`Left` / `Right`), used for mirror kinematics, 3D pose transformations, and control mappings.
- **`hardware_revision`**: Hardware revision identifier for production traceability. Applications should use concrete domain APIs and structured errors for runtime availability checks.
- **`motor_serial_numbers`**: Known physical motor serial numbers ordered by logical joints.
- **`touch_serial_numbers`**: Known touch-module serial numbers (empty for non-Touch SKUs or unreadable SNs).

#### Model Resolution & Explicit Overrides

Current device firmware does not store an independent product model field. The SDK automatically resolves `model` from serial number prefixes:

- **Normal Connection**: `DetectedDevice.model` carries the auto-detected model; simply call `connect(detected)` or `connect_auto()`.
- **Explicit Override**: For older firmware with missing, incorrect, or incomplete serial numbers, pass an explicit `model` upon connection. Overrides take precedence over SN detection for the current connection context without altering device firmware.

::: code-group
```python [Python]
# Example: Connect with explicit model override in Python
hand = await manager.connect_auto(model=sdk.Revo3Model.UltraTouch)
```

```cpp [C++]
// Example: Connect with explicit model override in C++
auto devices = manager.discover();
auto detected = devices.front();
detected.model = REVO3_MODEL_ULTRA_TOUCH;
auto hand = manager.connect(detected);
```
:::

The low-level touch protocol resolution state is SDK-internal and omitted from `DeviceInfo`. Applications should query [`hand.touch.layout`](#54-state-touch-and-health) for touch layout and touch data shape.

```python
# Example: Read basic device info and model
info = hand.device_info
if info is not None:
    print(f"SN: {info.serial_number}, Model: {info.model}, Hand side: {info.hand_side}")
    print(f"Motor SN count: {len(info.motor_serial_numbers)}, Touch SN count: {len(info.touch_serial_numbers)}")
```

### 3.3 Firmware Info (FirmwareInfo)

```text
FirmwareInfo
├── controller_firmware_version
├── motor_firmware_versions
└── touch_firmware_versions
```

Firmware information is separate from basic device info and hardware metadata and must be re-read after an upgrade or reconnect. The controller firmware belongs to the main device, but it remains in `FirmwareInfo` because it is software rather than hardware metadata. Field definitions:

- **`controller_firmware_version`**: Main controller firmware version.
- **`motor_firmware_versions`**: Currently known motor controller firmware versions in logical joint order.
- **`touch_firmware_versions`**: Currently known touch module firmware versions. The list is empty for non-Touch SKUs.

An empty list means that the current snapshot has no known versions. It may indicate that the device has no corresponding modules or that their versions have not been read. The current API does not expose a firmware-inventory completeness field. Call `await hand.refresh_firmware_info()` when component versions need to be refreshed.

```python
# Example: Read firmware versions
fw = hand.firmware_info
print(f"Controller FW: {fw.controller_firmware_version}, Motor FW count: {len(fw.motor_firmware_versions)}")
```

### 3.4 Joint Layout Model (JointLayout)

Python and C++ use `hand.joint_layout` to identify the active layout and validate array lengths. The property contains `layout_id`, `version`, and `joint_count`:

```text
JointLayout
├── layout_id                          --> Joint topology identifier (e.g. Revo3Ultra21 / Revo3Pro16 / Revo3Basic13)
├── version                            --> Version of the layout specification (currently 1)
└── joint_count                        --> Total number of logical joints (21 / 16 / 13)
```

The 21-DOF Ultra layout uses the fixed logical order below. Tools that inspect Pro or Basic metadata must use `JointLayout.joint_count` for their 16/13-DOF layouts and must not treat all 21 storage slots as active joints. This metadata support does not enable Motion, State, Touch, Health, Config, Calibration, or Maintenance for those models. Ultra position and velocity limits come from `DeviceConfig`; the SDK maps controller channels at the protocol boundary instead of exposing them through the Python or C++ API.

The current 21-DOF logical grouping is:

| Group | Logical indices | Joint count |
| --- | --- | ---: |
| Pinky | 0..3 | 4 |
| Ring | 4..7 | 4 |
| Middle | 8..11 | 4 |
| Index | 12..15 | 4 |
| Thumb | 16..20 | 5 |

The public Thumb order is Rotation, MCP, IP, Abd, and Flex. The protocol adapter converts this order to controller-channel order.

### 3.5 Product Model Enum (Revo3Model)

`Revo3Model` defines product identity values. Enum presence does not imply that
the product has entered SDK runtime validation; use the status column below.

| Enum Identifier (Revo3Model) | Generated C Symbol | DoF | Touch Type | SN Prefix | Product Status | SDK Runtime Status |
| :--- | :--- | :---: | :--- | :---: | :--- | :--- |
| `Ultra` | `REVO3_MODEL_ULTRA` | 21 | No Touch | `UBL` / `UBR` | Released | Enabled; Modbus/CANFD |
| `UltraTouch` | `REVO3_MODEL_ULTRA_TOUCH` | 21 | Integrated Array Touch | `UTL` / `UTR` | Released | Enabled; integrated touch over Modbus/CANFD |
| `UltraVisionTouch` | `REVO3_MODEL_ULTRA_VISION_TOUCH` | 21 | External Vision Touch | `UVL` / `UVR` | Hardware Pilot | Hand domains enabled; vision touch uses a separate vendor SDK |
| `Pro` | `REVO3_MODEL_PRO` | 16 | No Touch | `PBL` / `PBR` | Released | Identity and `JointLayout` only; runtime domains are not enabled |
| `ProTouch` | `REVO3_MODEL_PRO_TOUCH` | 16 | Integrated Array Touch | `PTL` / `PTR` | Released | Identity and `JointLayout` only; runtime domains are not enabled |
| `Basic` | `REVO3_MODEL_BASIC` | 13 | No Touch | `DBL` / `DBR` | Hardware Pilot | Identity and `JointLayout` only; runtime domains are not enabled |
| `BasicTouch` | `REVO3_MODEL_BASIC_TOUCH` | 13 | Integrated Array Touch | `DTL` / `DTR` | Hardware Pilot | Identity and `JointLayout` only; runtime domains are not enabled |

### 3.6 Connection, Logging, And Firmware Target Enums

Public Python integer enums expose a read-only `int_value` property containing the integer representation shared with the C ABI and protocol. Application logic should still compare enum members instead of hard-coding integers.

#### ProtocolType (Enum)

`ProtocolType` is used by discovery and connection options. `Auto` means that the SDK selects a supported transport; it is not a separate device protocol.

| Option | Value | Description |
| --- | ---: | --- |
| `Auto` | `0` | Auto-detect Modbus RTU or CANFD |
| `Modbus` | `1` | Use Modbus RTU over RS485 |
| `CanFd` | `3` | Use CANFD |

#### Rs485Baudrate (Enum)

Python connection APIs use this strongly typed enum. C++ currently represents `DiscoveryOptions.modbus_baudrate` as an integer in bps.

| Option | Value | Line Rate |
| --- | ---: | ---: |
| `Baud1Mbps` | `1` | 1,000,000 bps |
| `Baud2Mbps` | `2` | 2,000,000 bps |
| `Baud3Mbps` | `3` | 3,000,000 bps |
| `Baud5Mbps` | `5` | 5,000,000 bps |

#### CanFdBaudrate (Enum)

Python connection APIs use this strongly typed enum. C++ currently represents `DiscoveryOptions.canfd_data_baudrate` as an integer in bps. This enum configures the CANFD data-phase rate. The adapter and transport implementation determine the arbitration-phase rate; this enum does not configure it.

| Option | Value | Data-Phase Rate |
| --- | ---: | ---: |
| `Baud1Mbps` | `1` | 1,000,000 bps |
| `Baud2Mbps` | `2` | 2,000,000 bps |
| `Baud4Mbps` | `4` | 4,000,000 bps |
| `Baud5Mbps` | `5` | 5,000,000 bps |

#### LogLevel (Enum)

Python uses this enum with `init_logging()`. The C++ object API does not currently expose a corresponding logging initialization entry point.

| Option | Value | Description |
| --- | ---: | --- |
| `Error` | `0` | Error messages only |
| `Warn` | `1` | Warning and error messages |
| `Info` | `2` | Normal operational information; the default level |
| `Debug` | `3` | Debug information |
| `Trace` | `4` | Most detailed tracing information |

#### FirmwareTarget (Enum)

Python names this type `FirmwareTarget`; C++ names it `FirmwareTarget`.

| Python Option | C++ Option | Value | Description |
| --- | --- | ---: | --- |
| `MainFirmware` | `MainFirmware` | `0` | Main controller firmware |
| `Image` | `Image` | `1` | Device image target; available only when explicitly supported by the corresponding firmware |
| `MotorFirmware` | `MotorFirmware` | `2` | Motor-module firmware |

An enum member identifies an update target; it does not establish that the current device, firmware, or transport supports that target. Non-main-controller targets also require firmware support for writing and reading back the target register. The update fails when that confirmation fails and must not silently switch to another target.

## 4. Hand Domain APIs

### 4.1 Motion Control API

Target motion, trajectory generation, and real-time streaming control all start from `hand.motion`. API calling patterns are categorized as follows:

| Interface Class | Primary Use | Caller Responsibility |
| --- | --- | --- |
| Standard Device API | Discovery, normal motion, state, touch, config, and maintenance | Check returned states and errors |
| Motion Streaming-Control Mode | Data gloves, teleoperation, or custom controllers that continuously send new targets | Maintain an interval compatible with the configured send timeout and handle disconnect and exit behavior; do not describe non-deterministic transports and general-purpose operating systems as hard real time |
| Low-level Protocol API | Registers, raw frames, no-retry writes, and protocol diagnostics | Own protocol, safety, and compatibility risk |

```text
Hand
└── Motion
    ├── move_to() -> OperationHandle               --> Whole-hand timed target motion
    ├── move_joint() -> OperationHandle            --> Single-joint timed target motion
    ├── move_finger() -> OperationHandle           --> Full finger posture motion
    ├── flex_finger() -> OperationHandle           --> Simple finger flexion motion
    ├── move_thumb() -> OperationHandle            --> Independent thumb posture motion
    ├── open_servo() -> ServoSession            --> Open real-time streaming session
    ├── start_servo_drag()                      --> Start SDK-managed drag worker
    ├── update_servo_drag()                     --> Update drag target position
    ├── stop_servo_drag()                       --> Stop drag & send hold frame
    ├── cancel_servo_drag()                     --> Cancel drag & stop transmission
    ├── teach_joint()                           --> Record single-joint trajectory
    ├── teach_hand()                            --> Record whole-hand trajectory
    ├── replay_joint()                          --> Replay single-joint trajectory
    ├── replay_hand()                           --> Replay whole-hand trajectory
    ├── set_zero_force_enabled(enabled)                 --> Switch zero-torque / teach mode
    ├── software_stop() -> None                 --> Software-level motion pause
    └── recover_software_stop() -> None         --> Recover from software pause
```

- Provides timed target motion for the whole hand, one joint, one finger, and the Thumb.
- Typed position, velocity, current, and impedance commands.
- Long-running motion returns a `OperationHandle` for status, waiting, and cancellation requests.
- A cancellation request does not mean mechanical motion has stopped when the call returns.
- `teach_joint()`, `teach_hand()`, `replay_joint()`, and `replay_hand()` live under `hand.motion` because they capture or replay motion trajectories and share control ownership with other Motion modes.
- `hand.motion.set_zero_force_enabled(enabled)` maps the existing Teaching Mode command to enter or leave whole-hand zero-torque/backdrive mode. It is a Motion operating mode, not a Stop or functional-safety capability, and it conflicts with other active Motion operations when sent.
- `hand.motion.software_stop()` and `hand.motion.recover_software_stop()` call the existing firmware stop and recovery commands. The SDK does not define how motors stop; firmware documentation defines their behavior and states.

#### 4.1.1 Trajectory Motion API: move_to, move_joint, move_finger & move_thumb

> [!NOTE]
> **Underlying Trajectory & Transmission Mechanism**: Timed motion APIs (`move_to`, `move_joint`, `move_finger`, `move_thumb`) use **Quintic Polynomial Trajectory Interpolation** internally to guarantee continuous velocity and acceleration transitions. During motion execution, the SDK streams interpolated position and velocity targets as **Five-parameter MIT Hybrid Control Commands (Kp, Kd, Pos, Vel, Feedforward Current)** at high frequency to motor drivers. The feedback and feedforward fields remain named `current` / `current_ma`: the device reports electrical current in mA, not calibrated joint torque in Nm.

Use `move_to()` for timed whole-hand motion:

```python
handle = await hand.motion.move_to(
    target_positions,
    duration=0.8,
    dt=0.01,
)
await handle.wait(timeout=2.0)
```

| Parameter | Meaning |
| --- | --- |
| `target_positions` | Target position of every joint in degrees; ordering follows `hand.joint_layout`, and the array length must equal `joint_count` |
| `duration` | Total time to move from the current state to the target, in seconds; must be greater than zero and is mutually exclusive with `speed` |
| `speed` | Target motion speed in rpm; must be greater than zero, and the SDK derives duration from current and target positions |
| `kp`, `kd` | Optional uniform gains; SDK defaults are used when omitted |
| `dt` | Interval between trajectory points generated and sent by the SDK, in seconds; defaults to `0.01` and must be greater than zero |

The SDK generates a quintic trajectory and sends whole-hand targets. In Python, `await move_to()` validates the arguments, creates the motion task, and returns a `OperationHandle`; it does not wait for trajectory transmission or the complete motion. Errors after task creation are reported through the handle. The C++ equivalent is:

```cpp
auto handle = hand.motion().move_to(target_positions, 800ms, 10ms);
handle.wait(2000ms);
```

C++ uses `std::chrono::milliseconds` for `duration` and `period`. Motion can continue after `move_to()` returns; `wait()` is the call that blocks the current thread for the result.

`OperationHandle` provides:

| Member | Purpose |
| --- | --- |
| `state` | Read `Pending`, `Running`, `Succeeded`, `Cancelled`, `Preempted`, `Failed`, or `Indeterminate` |
| `wait(timeout)` | Wait for completion; a timeout ends only this wait and does not stop motion automatically |
| `cancel()` | Stop further trajectory sends by the SDK; the current firmware cannot confirm that mechanical motion has stopped, so the final result may be `Indeterminate` |
| `error` | Read the error when motion fails; empty after success |

Calling `move_to()` during an active target motion replaces the old target. The SDK regenerates the trajectory from current position and velocity feedback, and the old handle becomes `Preempted`. This is intended for occasional target changes, not continuous updates from a data glove, teleoperation system, or controller; use `open_servo()` for those cases.

<!-- 5.1.1 sub -->

These convenience methods use the same trajectory, control ownership, and `OperationHandle` behavior as `move_to()`:

```python
joint_motion = await hand.motion.move_joint(
    joint_index=0,
    target_position=20.0,
    duration=0.8,
)

finger_motion = await hand.motion.move_finger(
    finger_index=1,
    target_positions=[0.0, 30.0, 30.0, 0.0],
    duration=0.8,
)

flex_motion = await hand.motion.flex_finger(
    finger_index=1,
    flexion_position=30.0,
    duration=0.8,
)

thumb_motion = await hand.motion.move_thumb(
    target_positions=[0.0, 20.0, 20.0, 0.0, 20.0],
    duration=0.8,
)
```

| Method | Parameters |
| --- | --- |
| `move_joint()` | `joint_index` is a zero-based logical joint index; `target_position` is in degrees |
| `move_finger()` | `finger_index` is `1=Index`, `2=Middle`, `3=Ring`, or `4=Pinky`; the target array contains exactly 4 degree values on a 21-DOF hand, ordered as Abd, MCP, PIP, and DIP |
| `flex_finger()` | Uses the same `finger_index` as `move_finger()`; `flexion_position` is applied to MCP, PIP, and DIP while Abd stays at the current feedback position |
| `move_thumb()` | The target array contains exactly 5 degree values on a 21-DOF hand, ordered as Rotation, MCP, IP, Abd, and Flex |

`move_joint()` uses the same `duration`/`speed`, uniform `kp/kd`, and `dt` arguments as `move_to()`. `move_finger()`, `flex_finger()`, and `move_thumb()` are duration-based and accept optional uniform or per-joint `kp/kd`. `move_finger()` is the full finger-posture API and controls Abd; `flex_finger()` is the semantic bending API for quick starts, grasp actions, or GUI controls. All four return a `OperationHandle`. They can replace one another or `move_to()` for low-rate target changes; the old handle becomes `Preempted`. They conflict with `open_servo()`.

#### 4.1.2 Real-time Servo Control (open_servo)

Calling `hand.motion.open_servo()` creates a `ServoSession`. Callers supply targets via `send_position()`, `send_velocity()`, `send_current()`, `send_impedance()`, or `send_mit()`.

#### 4.1.3 Managed Drag Control (start_servo_drag)

For event-driven input sources (e.g. GUI sliders), call `Motion.start_servo_drag(joint_index, initial_position)` to initialize, and `update_servo_drag(joint_index, target_position)` on target changes.

#### 4.1.4 Real-time Control Entry Points: open_servo vs. start_servo_drag

For real-time streaming and continuous motion, the SDK provides two distinct entry points at different abstraction levels:

- **`open_servo()`** (Caller-managed loop): Opens a `ServoSession`, delegating high-frequency streaming control to a caller-owned loop. Ideal for VR gloves, teleoperation, or RL policies issuing targets every 5–20ms.
- **`start_servo_drag(...)`** (SDK-managed worker): Starts an SDK-managed background worker for a single joint. Ideal for GUI sliders and joystick controls, where the caller invokes `update_servo_drag()` on event changes, while the SDK automatically maintains continuous transmission with filtering, velocity limits, and collision protection.

**Comparison Table**:

| Feature / Dimension | `open_servo()` (Streaming Session) | `start_servo_drag()` (Managed Drag Stream) |
| :--- | :--- | :--- |
| **Core Concept** | **"Delegate real-time control to caller loop"** | **"SDK manages background loop for single joint"** |
| **Primary Use Cases** | Teleoperation, VR gloves, RL policies updating multiple joints every 5–20ms | GUI Slider dragging, interactive UI, joystick single-joint control |
| **Loop Ownership** | **Caller Loop** (caller maintains loop & send frequency) | **SDK Background Worker** (SDK transmits periodically) |
| **Control Scope** | Joint, Finger, Thumb, Full Hand | Single Joint |
| **Method List** | `send_position()`, `send_velocity()`, `send_mit()`, etc. | `start_servo_drag()`, `update_servo_drag()`, `stop_servo_drag()` |
| **Lifecycle & Timeout** | Explicit `session.close()`, auto-expire via `command_timeout_ms` | `stop_servo_drag()` for normal release; `cancel_servo_drag()` for emergency stop |
| **Safety Features** | Relies on algorithm layer for smoothing | Built-in filtering, velocity limits, collision checks & idle hold |

#### 4.1.5 Teach And Replay API

`teach_joint()` and `teach_hand()` sample joint feedback positions for a specified duration and return trajectory arrays that can be replayed later. `replay_joint()` and `replay_hand()` replay those trajectories using the provided `dt`, `kp`, and `kd`. These are Motion-domain APIs: while running, they own motion control and conflict with `move_to()`, local trajectory motion, `open_servo()`, and managed drag control.

```python
joint_positions = await hand.motion.teach_joint(
    joint_index=0,
    duration=3.0,
    dt=0.01,
)
await hand.motion.replay_joint(
    joint_index=0,
    positions=joint_positions,
    dt=0.01,
    kp=1.0,
    kd=0.1,
)

hand_trajectory = await hand.motion.teach_hand(duration=3.0, dt=0.01)
await hand.motion.replay_hand(hand_trajectory, dt=0.01, kp=1.0, kd=0.1)
```

### 4.2 State API

`HandState` contains status, position, velocity, current, and error for each motor. System state and the global error code are available from `HealthSnapshot`. A failed read returns `SdkError`.

State also contains one receive `timestamp`. Linux SocketCAN uses the kernel software timestamp from `SO_TIMESTAMPNS`; other CANFD and Modbus paths record when the SDK finishes reading. Only timestamps with the same `clock` value may be compared. This is not firmware sample time and cannot be used for cross-device synchronization.

```python
# Example: Read feedback snapshot or subscribe at 50Hz
snapshot = await hand.state.snapshot()
print(f"Current positions (degree): {snapshot.positions_deg}")

# Async subscription
sub = hand.state.subscribe(period=0.02)
try:
    frame = await sub.next()
finally:
    sub.close()
```

### 4.3 Touch API

The SDK exposes raw touch data through `TouchLayout` and a normalized `TouchFrame`. Applications can read:

- `mt_*`: Contains 11 palm/finger modules, supporting `PointArray` and the 42-value `LegacyForceSummary` compatibility mode used by a small number of shipped devices; the latter is scheduled for removal.
- `mx_*`: Contains 11 palm/finger modules; point counts are dynamically read from device input registers.
- `hp_*`: Contains 5 fingertip modules, providing 48-point arrays, 3D force, 2D torque, and module resultant force.
- `hp_* + mt_*`: Hybrid tactile topology; the 11 public modules use sparse numbering aligned with the protocol physical IDs: module 0 is the `mt_*` palm, modules 1/3/5/7/9 are `hp_*` fingertips, and modules 2/4/6/8/10 are `mt_*` fingerpads. Fingertip and fingerpad indices each increase from Thumb to Pinky (1/3/5/7/9 and 2/4/6/8/10 respectively); unused `mt_*` fingertip channels in the hybrid hardware are not exposed.
- `hp_* + mx_*`: Hybrid tactile topology with the same sparse numbering: module 0 is the `mx_*` palm, modules 1/3/5/7/9 are `hp_*` fingertips, and modules 2/4/6/8/10 are `mx_*` fingerpads.
- `hp_* + mx_* + mt_*`: Region-split hybrid tactile topology; module 0 is the `mt_*` palm, modules 1/3/5/7/9 are `hp_*` fingertips, and modules 2/4/6/8/10 are `mx_*` fingerpads.

All descriptions above refer to integrated tactile modules read over the hand's primary communication transport. Ultra VisionTouch fingertip sensors are accessed through vendor SDKs over separate USB/serial channels and do not enter `hand.touch`, `TouchLayout`, `TouchFrame`, or `TouchSubscription`. The SDK does not stitch supplier frames with Modbus/CANFD states into an ostensibly atomic frame.

Declared hybrid tactile layouts are `hp_*` fingertips + `mt_*` fingerpads/palm, `hp_*` fingertips + `mx_*` fingerpads/palm, and `hp_*` fingertips + `mx_*` fingerpads + `mt_*` palm. All three layouts use 11 stable public module IDs. Other unconfirmed module-by-module register mapping combinations remain fail-closed without fabricating or stitching incomplete touch frames.

1. `TouchLayout`: `TouchRegion` groupings plus per-module point layout and `TouchSignal` data shape.
2. `TouchFrame`: receive timestamp, sequence number, and a normalized list of `TouchModuleData` modules; regional force values are stored per module.
3. `TouchModuleData`: region, region-local index, stable module ID, layout ID, and sample state. `points`, `regional_forces_mn`, `force3d`, `torque2d`, `resultant_force_mn`, `module_status`, and `sensor_status` are optional according to frame mode and module capability. All public force values use mN.

`TouchLayout.regions` stores only region groupings and `module_ids`; `TouchLayout.modules` stores module-level layout: `module_id`, `region`, `region_index`, `signals`, `point_count`, and `layout_id`; per-module compatibility-mode regional forces are read from `TouchModuleData.regional_forces_mn`. `layout_id` is the public, code-based schema key for module layout and capability, not a supplier name. `TouchSignal` includes `TouchPoint`, `Force3D`, `Torque2D`, `ResultantForce`, `ModuleStatus`, and `SensorStatus`. `LegacyForceSummary` is a frame-level read mode rather than a per-module signal, so it is not part of `TouchSignal`. The public API does not expose supplier names or a `TouchPayloadType`. `TouchReadMode` (`4023`) applies only to `mt_*`: `PointArray` (0) returns point-array data whose value type is selected by register `4024` (`Adc` (0) or `Force` (2)); `LegacyForceSummary` (1) returns secondary-calibrated regional resultant-force values for a small number of shipped devices and is scheduled for removal. New applications should not depend on it. `mx_*` uses its own `output_mode`. If the touch register mapping cannot be identified, `snapshot()` returns an unsupported error instead of guessing an existing data shape.

`LegacyForceSummary` and `ResultantForce` describe different layers: the former is the `mt_*` secondary-calibrated compatibility mode represented by `TouchModuleData.regional_forces_mn`; the latter is a per-`hp_*`-module signal represented by `TouchModuleData.resultant_force_mn`. It is the scalar resultant over the entire module tactile area in mN, not the local `Fz` component.

Hybrid tactile `snapshot()` reads `hp_*` fingertips, the declared fingerpad modules, and the declared palm module in sequence during a single SDK operation. If any branch read fails, the entire snapshot fails without publishing partially stitched frames. An `mt_*` region returns point arrays in `PointArray` mode. In `LegacyForceSummary`, its modules are `Valid`, their `points` are `None`, and secondary-calibrated regional force values are written to `regional_forces_mn`. An `mx_*` region returns module data using its runtime `point_count` and `output_mode`; one frame mode is not used to summarize these data shapes when they coexist.

`PointArray` and `LegacyForceSummary` are mutually exclusive. `points = None` in a compatibility-mode frame means only that the current mode does not return point arrays; it does not mean the module was not sampled or is unavailable. The two modes may use different sampling paths, filtering, or calibration algorithms. Secondary-calibrated summary and point frames observed across a mode switch are not guaranteed to represent the same physical sample, and the SDK does not combine adjacent frames into an atomic sample.

`hp_*` module `force3d.x/y/z` represent `Fx/Fy/Fz` in the module-local coordinate system in mN; `torque2d.x/y` represent `Mx/My` around the local X/Y axes in Nm. Positive directions follow the coordinate system arrows, and torque directions follow the right-hand rule shown in hardware drawings.

Python exposes `hand.touch.layout` as `TouchLayout | None`. The C++ `hand.touch().layout()` method returns `TouchLayout` and throws `SdkError` when the touch layout is unavailable; it does not return an empty layout.

Public operation arguments use `module_index`, which takes the public `module_id` of the target module. Revo3 SDK 2.0 defines `module_id` as the stable logical ID for the active layout. In pure `mt_*` / `mx_*` layouts, `module_id` is a dense 0~10 numbering and equals the array position in `TouchLayout.modules` and `TouchFrame.modules`. In hybrid layouts, `module_id` uses sparse numbering aligned with the protocol physical IDs (palm 0, `hp_*` fingertips at odd IDs 1/3/5/7/9, fingerpads at even IDs 2/4/6/8/10), while the `TouchLayout.modules` and `TouchFrame.modules` arrays stay compactly ordered as fingertips, fingerpads, then palm; the array position no longer matches `module_id`, so applications must match modules by `module_id`, not by array position. This rule applies to `TouchLayout`, `TouchFrame`, and region groupings. Other register-level private IDs exist only in the SDK's private routing layer and are neither accepted as application input nor written to public frames. New hardware topologies must add private routing without changing existing 2.0 public module IDs. A custom layout must match a supported canonical layout field by field (including `modules` order and `module_id`) and is otherwise rejected before device I/O.

```text
Hand
└── Touch
    ├── layout -> TouchLayout | None
    ├── snapshot() -> TouchFrame
    ├── subscribe(period=None) -> TouchSubscription
    ├── enabled_mask()
    ├── set_enabled_mask(mask)
    ├── module_enabled(module_index)
    ├── set_module_enabled(module_index, enabled)
    ├── tare(module_index=None)
    ├── cancel_tare(module_index=None)
    ├── tare_status(module_index=None)
    ├── read_mode() / set_read_mode(mode)
    ├── value_mode(module_index=None) / set_value_mode(mode, module_index=None)
    ├── point_counts()
    └── restart(module_index=None)
```

```python
# Example: Read touch layout and tactile snapshot
layout = hand.touch.layout
if layout:
    for region in layout.regions:
        print(region.region, region.module_ids)
    for module in layout.modules:
        print(module.module_id, module.layout_id, module.point_count, module.signals)
    frame = await hand.touch.snapshot()
    print(f"Touch modules: {len(frame.modules)}")
    for module in frame.modules:
        if module.regional_forces_mn is not None:
            print(module.module_id, module.region, module.region_index, module.regional_forces_mn)
    print(f"First module: state={frame.modules[0].sample_state}, points={frame.modules[0].points}")
```

Use a subscription for continuous reads. `period` is the SDK polling interval, not a firmware sample-period guarantee. `TouchSubscription.next()` returns the next `TouchFrame`; `close()` releases the subscription.

```python
sub = hand.touch.subscribe(period=0.02)
try:
    frame = await sub.next()
finally:
    sub.close()
```

Tactile module enablement indicates whether a physical sensor module is active for sampling. When enabled, the module samples and returns tactile data; when disabled, the module stops sampling and its `sample_state` is normally `Disabled`.

`enabled_mask` is a bitmask representing the enablement of all modules: each bit corresponds to one module (bit 0 for module 0, bit 1 for module 1, etc.); bit value `1` means enabled, and `0` means disabled. Standard 11-module tactile (`mt_*` / `mx_*`) is `0x07FF` when all enabled; 5-module fingertip tactile (`hp_*`) is `0x001F` when all enabled; all three declared hybrid layouts have 11 public modules and are `0x07FF` when all enabled.

```python
mask = await hand.touch.enabled_mask()

# Enable module 0 while preserving the other module states.
await hand.touch.set_enabled_mask(mask | (1 << 0))

# Read the updated mask before changing another module.
mask = await hand.touch.enabled_mask()

# Disable module 3 while preserving the other module states.
await hand.touch.set_enabled_mask(mask & ~(1 << 3))

enabled = await hand.touch.module_enabled(0)
await hand.touch.set_module_enabled(0, not enabled)

await hand.touch.tare()
await hand.touch.tare(module_index=0)
```

When modifying only a single module, prefer `module_enabled()` and `set_module_enabled()` to avoid overwriting other modules. `tare()` without arguments performs zero-offset calibration across all supported touch modules.

Touch configuration and maintenance operations are exposed directly through `hand.touch`; vendor-specific subobjects and command enums are not part of the public API:

```text
Touch
├── read_mode()
├── set_read_mode(mode)
├── value_mode(module_index=None)
├── set_value_mode(mode, module_index=None)
├── tare(module_index=None)
├── cancel_tare(module_index=None)
├── tare_status(module_index=None)
├── point_counts()
└── restart(module_index=None)
```

These methods route by the active layout. An unsupported operation returns `UnsupportedCapability` before any device command is sent. In particular:

- `read_mode` and `set_read_mode` apply to layouts containing `mt_*`.
- `value_mode` and `set_value_mode` expose only `Adc` (0) and `Force` (2). Register value `1` is unused for `mt_*` and is not part of the public enum.
- `tare` routes to every supported touch family. `cancel_tare` and `tare_status` require a protocol that provides a cancellable tare state machine.
- `point_counts` and `restart` currently require a layout containing `mx_*`.

Public operation arguments use `module_index`, taking the public `module_id` of the target module. `TouchLayout` and `TouchFrame` expose `module_id` as a stable logical module ID; hybrid layouts use sparse IDs aligned with the protocol physical IDs, so `module_id` does not equal the `modules` array position there. Other register-level private IDs remain private to the routing layer and are never accepted by the public API.

Touch-module serial numbers are read from `hand.device_info.touch_serial_numbers`.

`point_counts()` currently depends on `mx_*` metadata registers and returns `UnsupportedCapability` when the layout does not contain `mx_*`. When a layout contains `mx_*` modules, the C ABI `revo3_device_touch_get_layout()` refreshes their runtime point counts and returns them through `CRevo3TouchLayout.modules[*].point_count`; other touch families return their known layout point counts directly. Touch-module serial numbers are read from `hand.device_info.touch_serial_numbers` or `CRevo3DeviceInfo.touch_serial_numbers`. Protocols without module serial-number registers report an empty list rather than fabricated values.

### 4.4 Health & Safety State API

`HealthSnapshot` is read-only. It contains system state, the global error code, current, voltage, power, system temperature, faulted motor count, and `safety_state`. Per-motor fault codes remain in `HandState.fault_codes`. Motor-module temperatures and the online bitmask are health diagnostic queries exposed as `hand.health.motor_module_temperatures_c()` and `hand.health.motor_online_mask()`. These values are not duplicated in `HealthSnapshot`. A complete protection-state model and its `SafetyState` mapping still require confirmed firmware semantics and on-device fault-path tests.

`HealthSnapshot` and `SafetyState` are software-level diagnostics collected and aggregated over ordinary Modbus RTU or CAN FD links. They are not functional-safety states and must not be used as evidence for an ISO 13849 PL or IEC 61508 SIL claim, a safety PLC decision, an Emergency Stop circuit, or STO. Confirmed errors produce `SafetyState::Faulted`; insufficient information produces `SafetyState::Unknown`. Software Stop and Servo timeout provide software-level control degradation only. Independent safety measures must be selected through the system risk assessment.

```python
# Example: Read health diagnostic snapshot
health = await hand.health.snapshot()
print(f"Safety State: {health.safety_state}, Faulted Motors: {health.faulted_motor_count}")

temperatures = await hand.health.motor_module_temperatures_c()
online_mask = await hand.health.motor_online_mask()
motor_0_online = bool(online_mask & (1 << 0))
```

C++ can read motor-module temperatures and the online bitmask together through `hand.health().motor_module_diagnostics()`.

### 4.5 ExperimentalCollision API

Collision detection is an explicit experimental domain and is not part of
`Health`. Python uses `hand.experimental_collision`, C++ uses
`hand.experimental_collision()`, and C uses
`revo3_experimental_collision_*`.

The feature is disabled by default. It currently relies mainly on SDK-side
position error, motor current, and the age of cached state, then applies a
software stop, zero-force mode, or actual-position hold strategy. It is not a
functional-safety mechanism, does not guarantee fixed detection latency, and
can produce false positives or missed collisions. Transport timing, status
update timing, thresholds, and firmware feedback timing all affect its behavior.
It must not replace an Emergency Stop, hardware limits, or a safety-rated
controller interlock. Experimental configuration fields and semantics may be
adjusted in later 2.x minor releases as hardware validation progresses.

```python
config = sdk.ExperimentalCollisionConfig(
    enable=True,
    source=sdk.CollisionDetectionSource.HardwareOnly,
    strategy=sdk.CollisionProtectionStrategy.SoftStop,
)
await hand.experimental_collision.configure(config)
active_joints = await hand.experimental_collision.active_joints()
await hand.experimental_collision.reset()
```

```cpp
revo3::ExperimentalCollisionConfig config;
config.enabled = true;
hand.experimental_collision().configure(config);
const auto active_joints = hand.experimental_collision().active_joints();
hand.experimental_collision().reset();
```

#### CollisionDetectionSource (Enum)

| Option | Value | Description |
| --- | ---: | --- |
| `HardwareOnly` | `0` | Use only collision state reported by the device |
| `SoftwareOnly` | `1` | Use only SDK-side position-error and motor-current thresholds |
| `Hybrid` | `2` | Use both device state and SDK-side thresholds |

#### CollisionProtectionStrategy (Enum)

| Option | Value | Description |
| --- | ---: | --- |
| `SoftStop` | `0` | Trigger an SDK software stop |
| `ZeroForce` | `1` | Send the zero-force control command |
| `HoldActualPosition` | `2` | Hold the actual feedback position observed at detection time |

Python and C++ callers must pass a defined enum member. An unknown integer is an `InvalidArgument`; the SDK must not fall back to a default detection source or protection strategy. This input contract does not change the experimental and non-functional-safety boundaries stated above.

### 4.6 Config API

`Config` manages device configuration snapshots and SDK runtime options. Device configuration is persisted by firmware; runtime options affect only the current SDK process.

- `hand.config.snapshot()` returns `DeviceConfig`, including `slave_id`, RS485 baud rate, device switches, protection current, position and speed limits, and `persistence_scope`. `hand.config` also provides explicitly named per-setting setters, but no bulk update that overwrites unrelated fields. Firmware is the sole source of truth for persistence.
- `hand.config.runtime_options` returns `RuntimeOptions`, and `hand.config.set_runtime_options(...)` updates process-local defaults for pull interval and streaming-control send timeout. They are not written to the device. A pull interval is not a device sample period or a fixed-rate guarantee.

```python
config = await hand.config.snapshot()
print(f"Slave ID: {config.slave_id}, Baudrate: {config.rs485_baudrate}")
runtime = hand.config.runtime_options
```

### 4.7 Calibration API

`Calibration` provides joint calibration, calibration-current, and zero-position operations. Calibration validates that Motion is idle and does not invent firmware progress or cancellation state.

```python
await hand.calibration.calibrate_joints()  # Joint calibration
await hand.calibration.set_current(120.0)
await hand.calibration.set_current_position_as_zero()
```

### 4.8 Maintenance API

`Maintenance` provides factory reset, reboot, and firmware update. `update_firmware(file_path, target=None, wait_secs=10)` is the only object-level update entry point; the current implementation uses the device DFU/OTA flow internally. Reboot and firmware update return queryable `OperationHandle` objects.

```python
reboot_handle = hand.maintenance.reboot()  # Reboot device
ota_handle = hand.maintenance.update_firmware("revo3_controller.bin")
```

## 5. Public API Reference

This section lists the Python and C++ object-layer public APIs. Python methods that perform I/O usually return awaitables; `await ...` in the table shows the recommended call style. C++ APIs live in the `revo3` namespace.

### 5.1 Manager / Manager

| Python | C++ | Returns | Behavior |
| --- | --- | --- | --- |
| `sdk.Manager()` | `revo3::Manager manager;` | manager | Create a device manager |
| `manager.list_ports()` | - | `list[SerialPortInfo]` | List local ports/adapters without probing devices |
| `await manager.discover(...)` | `manager.discover(options)` | `list[DetectedDevice]` | Discover devices (supports `on_found` streaming callback and cancellation) |
| `await manager.connect_auto(...)` | `manager.connect_auto(options)` | `Hand` | Discover and connect the first matching hand |
| `await manager.connect(detected, model=None)` | `manager.connect(detected)` | `Hand` | Connect a selected discovered device |
| `await manager.connect_all(devices)` | `manager.connect_all(devices)` | `list[Hand]` / `std::vector<Hand>` | Connect multiple devices |
| `await manager.close()` | `manager.close()` | `None` | Close managed hands and transports |

Python returns a standard `list[Hand]` with iteration, slicing, and zero-based indexed access. Applications can select a device by filtering on `hand.device_info.serial_number`. C++ returns `std::vector<Hand>` for multi-device connections.

Python `SerialPortInfo` exposes these read-only fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `port_name` | `str` | Operating-system port name |
| `manufacturer` | `str \| None` | USB manufacturer string, or `None` when unavailable |
| `product_name` | `str \| None` | USB product string, or `None` when unavailable |
| `serial_number` | `str \| None` | Adapter serial number, or `None` when unavailable |
| `vid` / `pid` | `int \| None` | USB VID/PID, or `None` for non-USB or unavailable metadata |

#### discover(...) Streaming Callback

- **Python Signature**: `await manager.discover(scan_all=False, port=None, protocol=None, slave_id=None, modbus_baudrate=None, canfd_data_baudrate=None, broadcast=True, on_found=None)`
  - `on_found`: Optional callback `Callable[[DetectedDevice], bool | None]`. Invoked for each device discovered. Returning `False` stops the scan early.
- **C++ Signature**: `std::vector<DetectedDevice> manager.discover(const DiscoveryOptions &options)`
  - `DiscoveryOptions.on_found`: Optional callback `std::function<bool(const DetectedDevice &device)>`. Returning `false` stops probing.

### 5.2 Hand And Metadata

| Python | C++ | Returns | Behavior |
| --- | --- | --- | --- |
| `hand.device_info` | `hand.device_info()` | [`DeviceInfo`](#deviceinfo) / `None` | Basic device information |
| `hand.firmware_info` | `hand.firmware_info()` | [`FirmwareInfo`](#firmwareinfo) | Controller, motor, and touch firmware versions |
| `hand.joint_layout` | `hand.joint_layout()` | [`JointLayout`](#jointlayout) / `None` | Joint count and topology |
| `await hand.refresh_device_info()` | `hand.refresh_device_info()` | [`DeviceInfo`](#deviceinfo) | Refresh basic device information |
| `await hand.refresh_firmware_info()` | `hand.refresh_firmware_info()` | [`FirmwareInfo`](#firmwareinfo) | Refresh firmware versions |
| `hand.motion` | `hand.motion()` | [`Motion`](#53-motion-and-servosession) | Motion domain |
| `hand.state` | `hand.state()` | [`State`](#54-state-touch-and-health) | Motor feedback domain |
| `hand.touch` | `hand.touch()` | [`Touch`](#54-state-touch-and-health) | Touch domain |
| `hand.health` | `hand.health()` | [`Health`](#54-state-touch-and-health) | Health diagnostics domain |
| `hand.experimental_collision` | `hand.experimental_collision()` | [`ExperimentalCollision`](#45-experimentalcollision-api) | Experimental software collision detection and response |
| `hand.config` | `hand.config()` | [`Config`](#56-touch-config-calibration-and-maintenance) | Configuration domain |
| `hand.calibration` | `hand.calibration()` | [`Calibration`](#56-touch-config-calibration-and-maintenance) | Calibration domain |
| `hand.maintenance` | `hand.maintenance()` | [`Maintenance`](#56-touch-config-calibration-and-maintenance) | Maintenance domain |
| `hand.statistics` | `hand.statistics()` | [`RuntimeStatistics`](#runtimestatistics) | Runtime read/write, failure, and timeout statistics |
| `await hand.close()` | `hand.close()` | `None` | Close this hand handle |

### 5.3 Motion And ServoSession

| Python | C++ | Returns | Behavior |
| --- | --- | --- | --- |
| `await hand.motion.move_to(...)` | `hand.motion().move_to(...)` | [`OperationHandle`](#7-waiting-cancellation-and-motion-conflicts) | Whole-hand joint angle control (all 21 joints) |
| `await hand.motion.move_joint(...)` | `hand.motion().move_joint(...)` | [`OperationHandle`](#7-waiting-cancellation-and-motion-conflicts) | Single-joint target angle control |
| `await hand.motion.move_thumb(...)` | `hand.motion().move_thumb(...)` | [`OperationHandle`](#7-waiting-cancellation-and-motion-conflicts) | Thumb motion control (all 5 joints, including opposition & abduction) |
| `await hand.motion.move_finger(...)` | `hand.motion().move_finger(...)` | [`OperationHandle`](#7-waiting-cancellation-and-motion-conflicts) | Single-finger all-joint control (all 4 joints, including abduction & flexion) |
| `await hand.motion.flex_finger(...)` | `hand.motion().flex_finger(...)` | [`OperationHandle`](#7-waiting-cancellation-and-motion-conflicts) | Semantic finger flexion (flexion only, holding abduction) |
| `hand.motion.open_servo(...)` | `hand.motion().open_servo(...)` | [`ServoSession`](#servosessionstate-enum) | Create a streaming session synchronously; `send_*()` performs asynchronous I/O |
| `await session.send_position(...)` | `session.send_position(...)` | `None` | Send position stream frame |
| `await session.send_velocity(...)` | `session.send_velocity(...)` | `None` | Send velocity stream frame |
| `await session.send_current(...)` | `session.send_current(...)` | `None` | Send current stream frame |
| `await session.send_impedance(...)` | `session.send_impedance(...)` | `None` | Send impedance stream frame |
| `await session.send_mit(...)` | `session.send_mit(...)` | `None` | Send MIT stream frame |
| `session.state` | `session.state()` | [`ServoSessionState`](#servosessionstate-enum) | Read session state |
| `session.close()` | `session.close()` | `None` | Close streaming session |
| `await hand.motion.start_servo_drag(...)` | `hand.motion().start_servo_drag(...)` | `None` | Start managed drag |
| `hand.motion.update_servo_drag(...)` | `hand.motion().update_servo_drag(...)` | `None` | Update managed drag target |
| `await hand.motion.stop_servo_drag(...)` | `hand.motion().stop_servo_drag(...)` | `None` | Stop drag normally |
| `await hand.motion.cancel_servo_drag(...)` | `hand.motion().cancel_servo_drag(...)` | `None` | Cancel drag transmission |
| `await hand.motion.teach_joint(...)` | `hand.motion().teach_joint(...)` | `list[float]` | Record one joint trajectory |
| `await hand.motion.teach_hand(...)` | `hand.motion().teach_hand(...)` | `list[list[float]]` | Record whole-hand trajectory |
| `await hand.motion.replay_joint(...)` | `hand.motion().replay_joint(...)` | `None` | Replay one joint trajectory |
| `await hand.motion.replay_hand(...)` | `hand.motion().replay_hand(...)` | `None` | Replay whole-hand trajectory |
| `await hand.motion.set_zero_force_enabled(enabled)` | `hand.motion().set_zero_force_enabled(enabled)` | `None` | Zero-force / teach-mode switch |
| `await hand.motion.software_stop()` | `hand.motion().software_stop()` | `None` | Send software stop and wait for this device I/O to finish |
| `await hand.motion.recover_software_stop()` | `hand.motion().recover_software_stop()` | `None` | Send software stop recovery and wait for this device I/O to finish |

### 5.4 State, Touch, And Health

| Python | C++ | Returns | Behavior |
| --- | --- | --- | --- |
| `await hand.state.snapshot()` | `hand.state().snapshot()` | [`HandState`](#handstate) | Read motor feedback snapshot |
| `hand.state.subscribe(period)` | `hand.state().subscribe(period)` | [`StateSubscription`](#statesubscription-touchsubscription-healthsubscription) | Create state polling subscription |
| `await sub.next()` | `sub.next()` | [`HandState`](#handstate) | Read next state frame |
| `hand.touch.layout` | `hand.touch().layout()` | [`TouchLayout`](#touchlayout) `| None` / [`TouchLayout`](#touchlayout) | Read touch region groups and module layout; C++ throws when unavailable |
| `await hand.touch.snapshot()` | `hand.touch().snapshot()` | [`TouchFrame`](#touchframe) | Read touch snapshot |
| `hand.touch.subscribe(period)` | `hand.touch().subscribe(period)` | [`TouchSubscription`](#statesubscription-touchsubscription-healthsubscription) | Create touch subscription |
| `await hand.touch.enabled_mask()` | `hand.touch().enabled_mask()` | `int` | Read touch enable bitmask |
| `await hand.touch.set_enabled_mask(mask)` | `hand.touch().set_enabled_mask(mask)` | `None` | Set touch enable bitmask |
| `await hand.touch.module_enabled(i)` | `hand.touch().module_enabled(i)` | `bool` | Read one module enable state |
| `await hand.touch.set_module_enabled(i, enabled)` | `hand.touch().set_module_enabled(i, enabled)` | `None` | Set one module enable state |
| `await hand.touch.tare(module_index=None)` | `hand.touch().tare()` / `hand.touch().tare(module_index)` | `None` | Universal tactile zero-offset calibration entry point; leaving out `module_index` clears all modules, while passing one clears a single module (auto-routes to the current code family’s `mt_*` / `mx_*` / `hp_*` modules) |
| `await hand.health.snapshot()` | `hand.health().snapshot()` | [`HealthSnapshot`](#healthsnapshot) | Read system health snapshot |
| `await hand.health.motor_module_temperatures_c()` | `hand.health().motor_module_diagnostics()` | `list[float]` / [`MotorModuleDiagnostics`](#motormodulediagnostics) | Motor-module temperatures |
| `await hand.health.motor_online_mask()` | `hand.health().motor_module_diagnostics()` | `int` / [`MotorModuleDiagnostics`](#motormodulediagnostics) | Motor online bitmask |
| `await hand.health.clear_motor_faults()` | `hand.health().clear_motor_faults()` | `None` | Clear motor faults |
### 5.5 ExperimentalCollision

| Python | C++ | C | Returns | Behavior |
| --- | --- | --- | --- | --- |
| `await hand.experimental_collision.configure(config)` | `hand.experimental_collision().configure(config)` | `revo3_experimental_collision_configure(...)` | `None` | Configure or disable experimental collision detection |
| `await hand.experimental_collision.active_joints()` | `hand.experimental_collision().active_joints()` | `revo3_experimental_collision_get_active(...)` | 21 booleans | Query latched experimental collision state |
| `await hand.experimental_collision.reset()` | `hand.experimental_collision().reset()` | `revo3_experimental_collision_reset(...)` | `None` | Reset experimental collision state |

`ExperimentalCollisionConfig`, `revo3::ExperimentalCollisionConfig`, and
`CRevo3ExperimentalCollisionConfig` carry enablement, detection source,
position-error and current thresholds, debounce duration, maximum cached-state
age, response strategy, and auto-clear duration. See [4.5](#45-experimentalcollision-api)
for the safety and stability limits.

Python configuration fields and constructor defaults are:

| Field | Default | Unit or meaning |
| --- | --- | --- |
| `enable` | `False` | Master enable |
| `source` | `HardwareOnly` | Detection source |
| `position_error_threshold_deg` | `15.0` | degree |
| `current_threshold_ma` | `800.0` | mA |
| `debounce_time_ms` | `100` | ms |
| `max_cached_status_age_ms` | `50` | ms |
| `strategy` | `SoftStop` | Protection strategy |
| `auto_clear_time_ms` | `1000` | ms |

### 5.6 Touch, Config, Calibration, And Maintenance

`Touch` provides the unified read, configuration, and maintenance surface. Availability is determined by the current `TouchLayout` and protocol capabilities.

#### Read and Subscribe

- `hand.touch.layout`: read the current `TouchLayout`.
- `await hand.touch.snapshot()`: read a single `TouchFrame`.
- `hand.touch.subscribe(period)`: create a `TouchSubscription`; pull the next frame via `next()` and release it via `close()`.

#### Layout Configuration

- `await hand.touch.set_layout(layout)`: set a confirmed complete layout for the current connection session; it does not write device registers and only updates the SDK's parsing routing.
- Only Revo3 Ultra Touch supports layout override; unknown or incomplete layouts fail before any device request is sent.

#### Module Enable State

- `set_module_enabled(module_index, enabled)` / `module_enabled(module_index)`: operate on one logical module.
- `set_enabled_mask(enabled_mask)` / `enabled_mask()`: operate on or read the logical module bitmask.
- `module_index` takes the public `module_id`: in pure `mt_*` / `mx_*` layouts it equals the `TouchLayout.modules` array position (dense 0~10); in hybrid layouts it uses sparse numbering and no longer matches the array position.

#### Read Mode

- `set_read_mode(mode)` / `read_mode()`: switch or read the `mt_*` `PointArray` / `LegacyForceSummary` mode.
- `LegacyForceSummary` exists only for a small number of shipped devices and is scheduled for removal. In this mode, `points` is `None` and secondary-calibrated regional forces are written to `regional_forces_mn`. New applications should not depend on it.

#### Value Mode

- `set_value_mode(mode, module_index=None)` / `value_mode(module_index=None)`: read or set the `mt_*` / `mx_*` ADC or force mode.
- The public enum contains only `Adc` (0) and `Force` (2); unused `mt_*` register value `1` is rejected.

#### Zero Calibration

- `tare(module_index=None)`: unified zero-offset calibration entry for `mt_*`, `mx_*`, and `hp_*`.
- `cancel_tare(module_index=None)`: `mx_*` only; writes a cancel command to restore the default/factory zero baseline. It does not imply an in-progress asynchronous procedure exists.
- `tare_status(module_index=None)`: `mx_*` only; reads the protocol-defined tare status. `hp_*` has no corresponding status register.

#### Module Information and Maintenance

- `point_counts()`: read the `mx_*` runtime point counts.
- `restart(module_index=None)`: restart `mx_*` modules.
- `hand.device_info.touch_serial_numbers`: read the discovered touch module serial numbers; the C ABI exposes them through `CRevo3DeviceInfo.touch_serial_numbers`.

| Python | C++ | Returns | Behavior |
| --- | --- | --- | --- |
| `await hand.touch.read_mode()` | `hand.touch().read_mode()` | `TouchReadMode` | Read touch layout mode |
| `await hand.touch.set_read_mode(mode)` | `hand.touch().set_read_mode(mode)` | `None` | Set touch layout mode |
| `await hand.touch.value_mode(module_index=None)` | `hand.touch().value_mode(module_index)` | `TouchValueMode` | Read touch value mode |
| `await hand.touch.set_value_mode(mode, module_index=None)` | `hand.touch().set_value_mode(mode, module_index)` | `None` | Set touch value mode |
| `await hand.touch.tare(module_index=None)` | `hand.touch().tare(module_index)` | `None` | Run zero-offset calibration |
| `await hand.touch.cancel_tare(module_index=None)` | `hand.touch().cancel_tare(module_index)` | `None` | Cancel a protocol-supported tare operation |
| `await hand.touch.tare_status(module_index=None)` | `hand.touch().tare_status(module_index)` | `TouchTareStatus` | Query tare status |
| `await hand.touch.point_counts()` | - | `list[int]` | Read module point counts |
| `await hand.touch.restart(module_index=None)` | `hand.touch().restart(module_index)` | `None` | Restart touch modules |
| `await hand.config.snapshot()` | `hand.config().snapshot()` | [`DeviceConfig`](#deviceconfig) | Read device config |
| `hand.config.runtime_options` | `hand.config().runtime_options()` | [`RuntimeOptions`](#runtimeoptions) | Read SDK runtime options |
| `hand.config.set_runtime_options(options)` | `hand.config().set_runtime_options(options)` | `None` | Set SDK runtime options |
| `await hand.config.set_buzzer(enabled)` | `hand.config().set_buzzer(enabled)` | `None` | Set buzzer |
| `await hand.config.set_vibration(enabled)` | `hand.config().set_vibration(enabled)` | `None` | Set vibration |
| `await hand.config.set_touch_screen(enabled)` | `hand.config().set_touch_screen(enabled)` | `None` | Set touch screen |
| `await hand.config.set_use_broadcast_id(enabled)` | `hand.config().set_use_broadcast_id(enabled)` | `None` | Set broadcast-ID usage |
| `await hand.config.set_power_on_auto_calibration(enabled)` | `hand.config().set_power_on_auto_calibration(enabled)` | `None` | Enable or disable automatic calibration on power-up |
| `await hand.config.set_auto_clear_motor_faults(enabled)` | `hand.config().set_auto_clear_motor_faults(enabled)` | `None` | Enable or disable automatic motor fault clearing |
| `await hand.config.set_max_continuous_current(ma)` | `hand.config().set_max_continuous_current(ma)` | `None` | Set max continuous current |
| `await hand.config.set_global_protect_current(ma)` | `hand.config().set_global_protect_current(ma)` | `None` | Set global protection current |
| `await hand.config.set_joint_protect_current(i, ma)` | `hand.config().set_joint_protect_current(i, ma)` | `None` | Set joint protection current |
| `await hand.config.set_joint_position_limits(i, min, max)` | `hand.config().set_joint_position_limits(i, min, max)` | `None` | Set joint position limits |
| `await hand.config.set_joint_speed_limits(i, min, max)` | `hand.config().set_joint_speed_limits(i, min, max)` | `None` | Set joint speed limits |
| `await hand.config.set_rs485_baudrate(baudrate)` | - | `None` | Set RS485 baudrate |
| `await hand.config.set_canfd_baudrate(baudrate)` | - | `None` | Set CANFD baudrate |
| `await hand.calibration.calibrate_joints()` | `hand.calibration().calibrate_joints()` | `None` | Joint calibration |
| `await hand.calibration.set_current(ma)` | `hand.calibration().set_current(ma)` | `None` | Set calibration current |
| `await hand.calibration.zero_positions()` | `hand.calibration().zero_positions()` | `list[float]` | Read zero positions |
| `await hand.calibration.set_zero_positions(values)` | `hand.calibration().set_zero_positions(values)` | `None` | Set zero positions |
| `await hand.calibration.set_current_position_as_zero()` | `hand.calibration().set_current_position_as_zero()` | `None` | Set current posture as zero |
| `await hand.calibration.reset_finger_defaults()` | `hand.calibration().reset_finger_defaults()` | `None` | Reset finger defaults |
| `hand.maintenance.reboot()` | `hand.maintenance().reboot()` | [`OperationHandle`](#7-waiting-cancellation-and-motion-conflicts) | Reboot device |
| `hand.maintenance.update_firmware(path, target=None, wait_secs=10)` | `hand.maintenance().update_firmware(path, target)` | [`OperationHandle`](#7-waiting-cancellation-and-motion-conflicts) | Firmware update |
| `await hand.maintenance.factory_reset()` | `hand.maintenance().factory_reset()` | `None` | Factory reset |
| `await hand.maintenance.abort_firmware_update()` | `hand.maintenance().abort_firmware_update()` | `None` | Abort firmware update |
| `await hand.maintenance.reset_firmware_update_state()` | `hand.maintenance().reset_firmware_update_state()` | `None` | Reset firmware update state |

## 6. Data Structures & Types Reference

This section details public data structures, status enums, and attribute fields returned by the Revo3 2.0 SDK.

### 6.1 Health & Diagnostics Structures

#### HealthSnapshot
Read-only system health and safety status snapshot:

| Field | Type | Description |
| --- | --- | --- |
| `system_state` | `int` | Global system status (`0=Normal`, `1=Fault`) |
| `error_code` | `int` | Global error code (`0=Normal`, `1=CommError`, `2=NoCalibration`, `3=TempAbnormal`) |
| `current_ma` | `int` | Total system current (mA) |
| `voltage_v` | `int` | Bus voltage (V) |
| `power_w` | `int` | Total system power (W) |
| `temperature_c` | `int` | Controller chip/board temperature (°C) |
| `faulted_motor_count` | `int` | Number of motors with a non-zero defined fault code |
| `safety_state` | [`SafetyState`](#safetystate-enum) | System safety diagnostic state (`Normal` / `RecoveryRequired` / `Faulted` / `Unknown`) |
| `observed_at` | [`Timestamp`](#timestamp) | Observation timestamp |

#### RuntimeStatistics
SDK transport and communication quality statistics:

| Field | Type | Description |
| --- | --- | --- |
| `state_reads` | `int` | Successful motor status read count |
| `touch_reads` | `int` | Successful touch frame read count |
| `commands_sent` | `int` | Total write commands sent |
| `failed_operations` | `int` | Total failed operation count |
| `servo_command_timeouts` | `int` | Servo session heartbeat timeout count |

#### MotorModuleDiagnostics
Per-motor driver layer diagnostics:

| Field | Type | Description |
| --- | --- | --- |
| `temperatures_c` | `list[float]` / `std::array<float, 21>` | Per-motor temperatures (°C) |
| `online_mask` | `int` / `uint32_t` | 21-bit motor online bitmask (Bits 0~20 for motors 0~20) |
| `serial_numbers` | `list[str]` / `std::vector<std::string>` | Per-motor serial numbers |

#### SafetyState (Enum)
- `Normal (0)`: System operating normally.
- `RecoveryRequired (1)`: Recoverable error present, reboot/recovery required.
- `Faulted (2)`: Severe fault state, motion commands halted.
- `Unknown (3)`: State unknown.

### 6.2 Streaming Control & Subscriptions (ServoSession & Subscriptions)

#### HandState
Single frame snapshot of motor feedback states across all 21 joints:

| Field | Type | Description |
| --- | --- | --- |
| `operating_states` | `list[int]` / `std::array<int, 21>` | Per-joint raw operating-state bitmasks from input registers 2000..2020 |
| `positions_deg` | `list[float]` / `std::array<float, 21>` | Per-motor current positions (deg) |
| `velocities_rpm` | `list[float]` / `std::array<float, 21>` | Per-motor current velocities (rpm) |
| `currents_ma` | `list[float]` / `std::array<float, 21>` | Per-motor current values (mA) |
| `fault_codes` | `list[int]` / `std::array<int, 21>` | Per-joint raw fault codes from input registers 2120..2140 |
| `timestamp` | [`Timestamp`](#timestamp) | Frame arrival timestamp |

#### ServoSessionState (Enum)
- `Active (0)`: Servo session active, accepting high-frequency control frames.
- `Expired (1)`: Heartbeat timeout (>100ms), session automatically expired.
- `Closed (2)`: Session explicitly closed via `close()`.

`ServoSession.state` is an observational interface for diagnostics and for distinguishing timeout expiration from explicit closure. The state may change immediately after it is read, so applications must not treat an `Active` check followed by a send as a concurrency guarantee. The result or structured error of each send remains authoritative. Both `Expired` and `Closed` are terminal; open a new Servo session before sending again.

#### ServoFilterMode (Enum)

| Option | Value | Description |
| --- | ---: | --- |
| `Disabled` | `0` | Disable smoothing; targets enter the drag control loop directly |
| `FirstOrderLpf` | `1` | Smooth target positions with a first-order low-pass filter |
| `SecondOrderCriticallyDamped` | `2` | Smooth target positions with a second-order critically damped filter |

#### StateSubscription / TouchSubscription / HealthSubscription
Asynchronous periodic data subscription objects:

| Method | Returns | Description |
| --- | --- | --- |
| `await sub.next()` / `sub.next()` | [`HandState`](#handstate) / [`TouchFrame`](#touchframe) / [`HealthSnapshot`](#healthsnapshot) | Wait and receive next periodic sample frame |
| `sub.close()` | `None` | Explicitly close subscription handle |

### 6.3 Touch Sensor Structures (Touch)

#### TouchLayout
Touch sensor module topology and layout, including pure `mt_*`, `mx_*`, and `hp_*` layouts and the declared `hp_* + mt_*`, `hp_* + mx_*`, and `hp_* + mx_* + mt_*` hybrid layouts:

Applications dynamically inspect the hand's touch distribution via `TouchLayout`, obtaining anatomical region groupings (Palm / Fingertips / Fingerpads) via `regions`, and layout ID, point count, and signal modalities via `modules`. Secondary-calibrated regional forces from `LegacyForceSummary` are read directly from each `TouchModuleData.regional_forces_mn`.

> [!NOTE]
> Independent vision-tactile sensing (such as Ultra VisionTouch and independent vision-tactile fingertip modules) uses dedicated supplier data channels and is not merged into the main-link `TouchLayout` or `TouchFrame`.

| Field | Type | Description |
| --- | --- | --- |
| `regions` | list[[`TouchRegionLayout`](#touchregionlayout)] | Region-grouped touch module layouts |
| `modules` | list[[`TouchModuleLayout`](#touchmodulelayout)] | Touch module layout list |

#### TouchRegionLayout
Anatomical region groupings of touch modules:

| Field | Type | Description |
| --- | --- | --- |
| `region` | [`TouchRegion`](#touchregion-enum) | Touch region enum |
| `module_ids` | `list[int]` | List of stable module IDs belonging to this region |

#### TouchModuleLayout
Topology and channel configuration of a single touch module:

| Field | Type | Description |
| --- | --- | --- |
| `module_id` | `int` | Stable module ID (0~10) |
| `region` | [`TouchRegion`](#touchregion-enum) | Touch region enum |
| `region_index` | `int` | Index within the region |
| `layout_id` | `str` | Tactile layout ID (e.g. `mt_palm_36`, `hp_fingertip_48`) |
| `point_count` | `int` | Total tactile array point count |
| `signals` | list[[`TouchSignal`](#touchsignal-enum)] | Supported tactile signal modalities |

#### TouchFrame
Single frame touch sensor snapshot:

| Field | Type | Description |
| --- | --- | --- |
| `sequence` | `int` | Frame sequence number |
| `timestamp` | [`Timestamp`](#timestamp) | Packet reception timestamp |
| `modules` | list[[`TouchModuleData`](#touchmoduledata)] | Per-module touch data list |

`TouchFrame` does not use one mode to summarize the whole frame because a hybrid topology can carry tactile points, regional force values, and force/torque data together. Applications inspect `regional_forces_mn` and each module's `sample_state`, `points`, `force3d`, `torque2d`, and `resultant_force_mn`. Device read configuration is represented separately by `TouchReadMode`.

#### TouchModuleData
Multi-channel sensor data for a single touch module:

| Field | Type | Description |
| --- | --- | --- |
| `region` | [`TouchRegion`](#touchregion-enum) | Touch region |
| `region_index` | `int` | Region-local index |
| `module_id` | `int` | Stable module ID |
| `layout_id` | `str` | Module layout ID |
| `sample_state` | [`TouchSampleState`](#touchsamplestate-enum) | Sampling state of this module in the current frame |
| `points` | `list[int] \| None` | Tactile points, or `None` when disabled, not sampled, or unavailable |
| `regional_forces_mn` | `list[int] \| None` | One or more secondary-calibrated regional resultant-force values for this module in the `mt_*` `LegacyForceSummary` compatibility mode, in mN |
| `force3d` | [`TouchForce3D`](#touchforce3d-touchtorque2d) \| None | `hp_*` module `Fx/Fy/Fz` in the module-local coordinate system, in mN |
| `torque2d` | [`TouchTorque2D`](#touchforce3d-touchtorque2d) \| None | `hp_*` module `Mx/My` around the module-local x/y axes, in Nm |
| `resultant_force_mn` | `float \| None` | Scalar resultant `Fn` over the entire `hp_*` module tactile area, in mN; not `Fz` |
| `module_status` | `int \| None` | Module status code |
| `sensor_status` | `int \| None` | Sensor status code |

#### TouchForce3D / TouchTorque2D
3D Force and 2D Torque Vectors:

| Type | Field | Type | Description |
| --- | --- | --- | --- |
| `TouchForce3D` | `x`, `y`, `z` | `float` | 3D force vector `Fx`, `Fy`, `Fz` (mN) |
| `TouchTorque2D` | `x`, `y` | `float` | 2D torque vector `Mx`, `My` (Nm) |

#### TouchSampleState (Enum)

| Option | Value | Description |
| --- | ---: | --- |
| `Valid` | `1` | Module data is valid in this frame |
| `Disabled` | `2` | Module is disabled |
| `NotSampled` | `3` | The module was not polled and contributed no data to this frame |
| `ReadFailed` | `4` | Module read failed |
| `Unavailable` | `5` | Module data is unavailable |
| `WarmingUp` | `6` | `hp_*` module warm-up is not complete |
| `SensorFault` | `7` | `hp_*` module is ready but reports a sensor fault |

The SDK uses a whole-frame consistency policy for snapshot reads: if any enabled module fails to read, `snapshot()` returns an error for the whole operation instead of returning a partial frame zero-filled for failed modules. `NotSampled` and `ReadFailed` are reserved for potential future selective-polling or partial-frame policies and are not produced during normal snapshot reads.

##### Touch Module layout_id Examples

The base `layout_id` format is `<prefix>_<region>_<actual_point_count>`:

- `mt_*`: e.g., `mt_palm_36`, `mt_thumbtip_31`, `mt_fingertip_21`, `mt_thumbpad_57`, `mt_fingerpad_52`
- `mx_*`: generated from runtime-reported point counts. Recent hardware observations include `mx_palm_53`, `mx_fingertip_56`, `mx_fingerpad_22`, `mx_fingertip_21`, and `mx_fingerpad_27`. Protocol capacities `200/80/120` are not actual counts and must not be used to construct layout IDs
- `hp_*`: e.g., `hp_fingertip_48`

The base ID distinguishes only region and actual point count. If modules with the same count use different point order or geometry, a controlled hardware-revision or module-identity mapping must provide a suffix such as `_v2` or `_v3`. The SDK must not infer a layout revision from point count. Automatic detection currently emits only base IDs; a revision suffix must be added to the SDK's controlled layout mapping before it is published as a public ID. Applications encountering an unknown ID must not apply an existing coordinate map, although they may still consume the one-dimensional data using `point_count`.

#### TouchRegion (Enum)

| Option | Python value | C/C++ value | Description |
| --- | ---: | ---: | --- |
| `Fingertip` | `0` | `1` | Fingertip region; `region_index` identifies the digit |
| `FingerPad` | `1` | `2` | Fingerpad region; `region_index` identifies the digit |
| `Palm` | `2` | `3` | Palm region; `region_index` is `0` |

Within `Fingertip` and `FingerPad`, `region_index` maps `Thumb/Index/Middle/Ring/Pinky` to `0/1/2/3/4`. Applications must not reference nonexistent enum options such as `ThumbTip` or `IndexPad`.

The C ABI additionally defines `C_REVO3_TOUCH_REGION_UNKNOWN = 0` so unused region slots in a zero-initialized `CRevo3TouchLayout` have a valid representation. `CRevo3TouchLayout` has no explicit module count: valid modules must occupy contiguous slots starting at `modules[0]`, and the first slot whose `layout_id[0] == '\0'` ends the list. All later slots must remain unused. `revo3_device_touch_set_layout()` rejects an `Unknown` region in a valid module or a non-empty `layout_id` after the terminating slot. Python and C++ object APIs do not expose this sentinel member.

#### TouchSignal (Enum)

| Option | Description |
| --- | --- |
| `TouchPoint` | Tactile array pressure points |
| `Force3D` | 3D contact force (`Fx`, `Fy`, `Fz`) |
| `Torque2D` | 2D contact torque (`Mx`, `My`) |
| `ResultantForce` | Normal resultant contact force (`Fn`) |
| `ModuleStatus` | Module hardware status |
| `SensorStatus` | Sensor fault status |

#### TouchReadMode (Enum)
Touch data mode:

| Option | Value | Description |
| --- | --- | --- |
| `PointArray` | `0` | **Point-array mode**: Outputs point-array data; point values are selected by `TouchValueMode`. |
| `LegacyForceSummary` | `1` | **Secondary-calibrated force-summary compatibility mode**: Supports a small number of shipped devices and is scheduled for removal; new applications should not depend on it. |

> **Applicability**: Applies to layouts containing `mt_*` modules.

#### TouchValueMode (Enum)
Touch value mode:

| Option | Value | Description |
| --- | --- | --- |
| `Adc` | `0` | **ADC Value**: Raw circuit sample value (for debugging). |
| `Force` | `2` | **Force value**: Force value output by the device. |

> **Supported Modes**:
> - `mt_*` modules: Supports `Adc` (0) and `Force` (2). Register `4024` value `1` is unused and is not publicly exposed by the SDK.
> - `mx_*` modules: Supports `Adc` (0) and `Force` (2). The SDK maps public value `2` to the `mx_*` register value `1`.

#### TouchTareStatus (Enum)

| Option | Value | Description |
| --- | ---: | --- |
| `NotTared` | `0` | Zero-offset calibration has not completed |
| `Tared` | `1` | Zero-offset calibration completed |
| `BusyOrFailed` | `2` | The operation is in progress or failed; the protocol does not provide a more specific state |

### 6.4 Device Metadata Structures

#### DeviceInfo
Basic device identity and hardware identifiers:

| Field | Type | Description |
| --- | --- | --- |
| `model` | [`Revo3Model`](#35-product-model-enum-revo3model) | Device model (e.g. `Ultra`, `Pro`, `Basic`) |
| `serial_number` | `str` | Hand serial number (e.g. `BCUBR40124000001`) |
| `hand_side` | [`HandSide`](#handside-enum) | Hand side (`Left` / `Right`) |
| `hardware_revision` | `str` | Hardware revision string |
| `motor_serial_numbers` | `list[str]` | Per-motor serial numbers |
| `touch_serial_numbers` | `list[str]` | Per-touch-module serial numbers |

#### FirmwareInfo
Firmware versions across sub-modules:

| Field | Type | Description |
| --- | --- | --- |
| `main_controller` | `str` | Main controller firmware version string |
| `motor_driver` | `str` | Motor driver board firmware version string |
| `touch_module` | `str` | Touch module firmware version string |

#### JointLayout
Logical joint topology and degree-of-freedom specifications:

| Field | Type | Description |
| --- | --- | --- |
| `layout_id` | `str` | Logical joint topology identifier (e.g. `Revo3Ultra21`, `Revo3Pro16`, `Revo3Basic13`) |
| `version` | `int` | Layout specification version (e.g. `1`) |
| `joint_count` | `int` | Total number of logical joints (e.g. `21`, `16`, `13`) |

#### DeviceConfig
Device hardware and control configuration parameter snapshot:

| Field | Python / C++ type | Description |
| --- | --- | --- |
| `slave_id` | `int` / `std::uint8_t` | Current device slave ID |
| `rs485_baudrate` | `int` / `std::uint32_t` | Current RS485 baudrate (bps) |
| `canfd_baudrate` | `int` / `std::uint32_t` | Current CANFD data baudrate (bps) |
| `buzzer_enabled` | `bool` | Buzzer state |
| `vibration_enabled` | `bool` | Vibration motor state |
| `touch_screen_enabled` | `bool` | Touch screen state |
| `teaching_mode_enabled` | `bool` | Zero-force/teaching mode state |
| `software_stop_enabled` | `bool` | Software stop state |
| `use_broadcast_id` | `bool` | Broadcast ID usage state |
| `power_on_auto_calibration_enabled` | `bool` | Automatic calibration on power-up is enabled |
| `auto_clear_motor_faults_enabled` | `bool` | Automatic motor fault clearing enabled |
| `max_continuous_current_ma` | `float` | Maximum continuous current (mA) |
| `global_protect_current_ma` | `float` | Global protection current (mA) |
| `joint_protect_current_ma` | `list[float]` / `std::array<float, 21>` | Per-joint protection currents (mA); valid length is defined by `JointLayout.joint_count` |
| `joint_min_position_deg` | `list[float]` / `std::array<float, 21>` | Per-joint minimum position limits (deg); valid length is defined by `JointLayout.joint_count` |
| `joint_max_position_deg` | `list[float]` / `std::array<float, 21>` | Per-joint maximum position limits (deg); valid length is defined by `JointLayout.joint_count` |
| `joint_min_speed_rpm` | `list[float]` / `std::array<float, 21>` | Per-joint minimum speed limits (rpm); valid length is defined by `JointLayout.joint_count` |
| `joint_max_speed_rpm` | `list[float]` / `std::array<float, 21>` | Per-joint maximum speed limits (rpm); valid length is defined by `JointLayout.joint_count` |
| `persistence_scope` | `str` / - | Python-only persistence scope description; currently `firmware-defined` |

#### RuntimeOptions
SDK runtime client configuration (process-local defaults, not written to the device):

| Field | Type | Description |
| --- | --- | --- |
| `state_subscription_period_ms` | `int` | Default State subscription pull interval (ms); default 20 |
| `touch_subscription_period_ms` | `int` | Default Touch subscription pull interval (ms); default 20 |
| `health_subscription_period_ms` | `int` | Default Health subscription pull interval (ms); default 1000 |
| `servo_command_timeout_ms` | `int` | Default timeout (ms) between consecutive streaming Servo commands; default 100 |

#### Timestamp
Data frame arrival and system timestamps:

| Field | Type | Description |
| --- | --- | --- |
| `sec` | `int` | Seconds |
| `nsec` | `int` | Nanoseconds (0~999,999,999) |
| `clock` | `TimestampClock` | Clock source (`ProcessMonotonic`, `UnixRealtime`) |

#### TimestampClock (Enum)

| Enum Variant | Value | Description |
| --- | ---: | --- |
| `ProcessMonotonic` | `0` | Process-local monotonic clock (immune to wall clock adjustments) |
| `UnixRealtime` | `1` | UTC epoch realtime clock |

#### HandSide (Enum)

| Option | Value | Description |
| --- | ---: | --- |
| `Left` | `0` | Left hand |
| `Right` | `1` | Right hand |

## 7. Waiting, Cancellation, And Motion Conflicts

Target motion, device restart, and firmware update return a Handle. Applications use the Handle to inspect state, wait for completion, or request cancellation. `OperationHandle` is the caller-facing name for motion and maintenance operation handles; all such handles use `OperationState` and the SDK does not define a duplicate `MotionState`. Joint calibration, software stop, and software-stop recovery wait directly for one device I/O operation and do not return a Handle. A device restart cannot be withdrawn after device I/O begins, so calling `cancel()` leaves its Handle in the current state.

```text
OperationHandle
├── id
├── state
└── error
```

Handle states are Pending, Running, Succeeded, Cancelled, Preempted, Failed, and Indeterminate. With the current hardware communication model, cooperative cancellation requested through `cancel()` ends in `Indeterminate`: read actual state before deciding whether to retry. `Cancelled` is reserved for a future protocol that can confirm deterministic device-side cancellation. Current firmware does not provide common progress or device-side start and finish times, so the Handle does not include those fields. Indeterminate means that the SDK does not know how far the device executed the operation; callers must not retry immediately.

### 7.1 OperationState (Enum)

| Option | Value | Terminal | Description |
| --- | ---: | :---: | --- |
| `Pending` | `0` | No | Created but not yet executing |
| `Running` | `1` | No | Executing |
| `Succeeded` | `2` | Yes | Completed successfully |
| `Cancelled` | `3` | Yes | Device-side cancellation was confirmed; the current protocol generally cannot provide this confirmation |
| `Preempted` | `4` | Yes | Replaced by a newer operation of the same kind |
| `Failed` | `5` | Yes | Failed with an available error object |
| `Indeterminate` | `6` | Yes | Final device effect cannot be confirmed; read actual state first |

Target motion uses cooperative cancellation. The SDK lets the current register request finish, stops sending trajectory points at the next control-cycle boundary, and then releases software control ownership; it does not discard an in-flight serial request. Firmware update cancellation sends the device abort command at the next DFU polling or packet boundary. The Handle becomes `Indeterminate` when the cancellation request was issued but the final device position or write result cannot be confirmed.

Python `handle.error` and C++ `handle.error()` return the `SdkError` bound to that Handle; when no error exists, they return `None` and `std::nullopt`, respectively. Terminal state and error are published as one result. Therefore, when `Failed` or an error-bearing `Indeterminate` is observed, the corresponding error is already readable and does not depend on a thread-local last API error.

A Hand cannot run `move_to()` and a `ServoSession` at the same time; conflicts return `ControlConflict`. `move_to()` generates and sends a trajectory, while `ServoSession` accepts targets continuously from the caller.

Calling `move_to()` while another `move_to()` is active replaces the previous target. The SDK replans from the current feedback position and velocity, and the previous `OperationHandle` becomes `Preempted`. This behavior is intended only for low-rate replanning. For frequent target updates, use `open_servo()`.

Joint calibration uses a single command. The SDK checks that no motion is active before sending it. Touch reads and Touch calibration do not affect motion. Firmware does not provide calibration progress or completion status, so a write response confirms only that the command was sent.

## 8. Error Handling, Timeouts, And Retries

```text
SdkError
├── code
├── message
├── retryable
├── operation_effect
├── recovery_requirement
└── low_level_cause
```

`SdkError` is the structured error returned by all API failures. Applications inspect `code` and `message` for logging and UI display. After a failed write, callers must inspect `operation_effect`: if it is `Indeterminate`, the command may have taken effect on the device while the response was lost; read device state before deciding whether to retry. The remaining fields provide retry eligibility (`retryable`), recommended recovery action (`recovery_requirement`), and underlying driver cause (`low_level_cause`).

Python represents `code`, `operation_effect`, and `recovery_requirement` with the `SdkErrorCode`, `OperationEffect`, and `RecoveryRequirement` enums. C++ uses strongly typed enums with the same names and does not expose untyped integer error fields.

### 8.1 Error Enums

`SdkErrorCode` is the sole error identifier for programmatic branching. C++ additionally reserves `Unknown = 0` when converting an unrecognized C ABI value; Python does not export that member.

| Value | `SdkErrorCode` | Typical Meaning |
| ---: | --- | --- |
| `1` | `ConnectionFailed` | Connection establishment or transport failure |
| `2` | `InvalidArgument` | An argument violates the public contract |
| `3` | `InvalidState` | The current lifecycle or device state does not permit the operation |
| `4` | `Timeout` | Bounded wait or communication timeout |
| `5` | `UnsupportedCapability` | The current model, firmware, layout, or transport does not support the capability |
| `6` | `DeviceFault` | The device explicitly reported a fault |
| `7` | `Internal` | Internal SDK error |
| `8` | `ControlConflict` | Conflict with current motion or streaming-control ownership |

#### OperationEffect (Enum)

| Option | Value | Description |
| --- | ---: | --- |
| `NotApplied` | `1` | The operation is confirmed not to have been applied to the device |
| `PartiallyApplied` | `2` | The operation was only partially applied; read state and follow API-specific recovery |
| `Indeterminate` | `3` | Whether the operation took effect cannot be confirmed; do not retry a write immediately |

#### RecoveryRequirement (Enum)

| Python Option | C++ Option | Value | Description |
| --- | --- | ---: | --- |
| `None_` | `None` | `0` | No additional recovery action is required; Python uses `None_` to avoid the keyword |
| `Retry` | `Retry` | `1` | Retry only when allowed by `retryable` and the operation effect |
| `Reconnect` | `Reconnect` | `2` | Reconnect and reacquire session state |
| `OperatorAction` | `OperatorAction` | `3` | The device explicitly reported a fault that requires operator inspection or intervention |

The SDK returns only recovery actions for which it currently has an explicit decision rule. Safety-protection recovery and device power cycling do not yet have uniform firmware semantics or an automatic classification path, so they are not exposed as `RecoveryRequirement` values.

Retry rules:

- These rules apply to device requests made through the Hand API. Manager discovery, connection, and reconnection follow their own flows and are not command retries.
- A read-only request may be retried automatically only when the underlying connection has not been rebuilt and policy permits.
- If the response to a state-changing request is lost, the result is unknown: the command may or may not have run. The SDK must not send it again automatically.
- Disconnect, reconnect, safety recovery, and resending a command are distinct actions.
- A `wait(timeout)` timeout ends only that wait; it does not automatically cancel the device operation.
- Python and C++ use the same error codes and handling rules.

```python
# Example: Catch structured SdkError and handle Indeterminate results
try:
    await hand.motion.move_to(targets, duration=1.0)
except sdk.SdkError as error:
    print(f"Code: {error.code}")
    if error.operation_effect == sdk.OperationEffect.Indeterminate:
        # Lost response: read state to check if operation took effect before retrying
        state = await hand.state.snapshot()
```

## 9. Data, Timestamp, And Physical Unit Conventions

### 9.1 Time and Clock Model

- **Control & Feedback Units**: SDK public APIs uniformly use degrees (°) for positions, rpm for rotational velocities, and mA for currents. Lower-level drivers handle any necessary binary or unit conversions.
- **Current Is Not Calibrated Joint Torque**: Motor feedback and MIT feedforward fields are electrical current in mA. The device does not provide a calibrated joint-torque signal in Nm, so these fields remain `current` / `current_ma` rather than `torque`.

### 9.2 Timestamp Semantics

- **Receive Timestamp**: The `timestamp` field in `State` and `Touch` snapshots represents the SDK packet receive time. On Linux SocketCAN, kernel software timestamps are preferred; other transports use process monotonic clocks.
- **Scoping & Limits**: The `timestamp` is not the internal firmware sample instant and cannot be used for cross-device hardware clock sync. For multi-frame snapshots, `timestamp` marks when full assembly completes and does not guarantee simultaneous sampling for all fields.

### 9.3 Unit Conversion Tools

Physical unit conversion utilities are provided across languages for ROS / ROS 2 and SI compatibility:

#### Physical Unit Conversion Constants
- **Angle**: `deg_to_rad`, `rad_to_deg` (`1 deg = π / 180 rad`)
- **Velocity**: `rpm_to_rad_s`, `rad_s_to_rpm` (`1 rpm = π / 30 rad/s`)
- **Current**: `ma_to_a`, `a_to_ma` (`1 mA = 0.001 A`)

#### C ABI and C++ Tools
- **C ABI (`revo3-sdk.h`)**: `revo3_deg_to_rad`, `revo3_deg_to_rad_array`, etc.
- **C++ (`revo3::units`)**: `revo3::units::deg_to_rad`, `StateSnapshot.positions_rad`, etc.

#### Python Module Tools
- Import `main_mod` with `from bc_revo3_sdk import main_mod as sdk`.
- `sdk.get_sdk_version()` returns the exact SDK version string, including a pre-release suffix.
- `sdk.init_logging(level=LogLevel.Info)` initializes SDK logging.
- `sdk.list_available_ports()` returns `list[SerialPortInfo]` without probing devices.
- `sdk.configure_usb_vid_pid_allowlist(custom_ids=[], include_defaults=True)` configures the USB adapter VID/PID allowlist; set `include_defaults=False` to use only caller-provided entries.
- Unit helpers include `sdk.deg_to_rad`, `rad_to_deg`, `rpm_to_rad_s`, `rad_s_to_rpm`, `ma_to_a`, and `a_to_ma`; scalar and sequence inputs are supported.
- `HandState.positions_rad`, `velocities_rad_s`, and `currents_a` provide converted feedback views.

## 10. Language Binding Conventions

### 10.1 C/C++ API

- **Namespaces & Types**: The minimum compiler standard is C++17. Public types reside in the `revo3` namespace (e.g. `revo3::Manager`, `revo3::Hand`, `revo3::OperationHandle`), omitting redundant `revo3_` prefixes from class and method names.
- **Version Query**: `revo3::api_version()` returns encoded version numbers, major/minor/patch, and an exact string including pre-release suffixes (such as `2.0.0-rc.3`).
- **C ABI**: `revo3-sdk.h` can be directly included by C11 and C++17 compilers; C symbols uniformly use the `revo3_` prefix. SDK 2.0 does not export 1.x `DeviceHandler`, manual transport initialization, global callback setters, or unprefixed `stark_*` compatibility entries.
- **Object Layer**: The C++17 object API is implemented on top of the public C ABI, providing RAII, strongly typed parameters, and exception translation without forming a redundant second protocol stack.
- **Resource Management & Lifecycles**: `Manager` and `Hand` objects can be moved but not copied. They release resources when leaving scope, or when calling `close()` directly; repeated `close()` calls are safe and idempotent.
- **Async Handles & Waiting**: Long operations (such as target motion, reboot, and firmware update) return a Handle object immediately; call `wait(std::chrono::milliseconds)` to perform a blocking wait.
- **Exceptions & Status**: Runtime errors throw `revo3::SdkError`, while operation completion status is represented by `OperationState`.

### 10.2 Python API

- **Module Design & Types**: Exports only the classes, enums, and data structs defined by this specification; provides no 1.x module-level or `DeviceContext` compatibility aliases. Supports Python 3.10+ with precise `T | None`, `Sequence[T]`, and `Awaitable[T]` stub typing.
- **Resource Management & Lifecycles**: Supports calling `close()` explicitly or using `async with` context managers to close ports and connections automatically on exit.
- **Async Handles & Waiting**: Long operations (such as target motion, reboot, and firmware update) return a Handle object; call `await handle.wait(timeout)` to wait for completion (the Handle itself is not directly awaitable).
- **Exceptions & Status**: Shares identical `SdkError` exception structures and `OperationState` status representations with C++.
