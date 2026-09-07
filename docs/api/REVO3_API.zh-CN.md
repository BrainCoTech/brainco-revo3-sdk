# Revo3 SDK API 参考手册

> API 版本：2.0.0
>
> 语言说明：简体中文（`zh-CN`）| [English (en-US)](REVO3_API.en-US.md)

本规范定义 BrainCo Revo3 灵巧手 SDK 公共 API 的对象模型、接口签名与调用规范。

## 1. 概述与适用范围

### 1.1 硬件支持范围

SDK 2.0 可识别 Revo3 Ultra (21 DOF)、Pro (16 DOF) 和 Basic (13 DOF) 系列，并通过 `JointLayout` 报告当前设备的逻辑关节数量和布局。当前 SDK runtime 仅对 Ultra 21 DOF 系列开放功能域；Pro 和 Basic 系列当前仅提供设备识别与 `JointLayout`，其他运行时能力保持 fail-closed：尚未验证的能力返回 `NotVerified`，型号不包含对应硬件时返回 `HardwareMissing`。产品生命周期与 SDK runtime 支持状态是两个独立维度：Ultra、Ultra Touch、Pro 和 Pro Touch 为已发布型号；Ultra VisionTouch、Basic 和 Basic Touch 为 Hardware Pilot。产品已发布不表示对应 SDK runtime 能力已开放。

Ultra VisionTouch 的整手运动、状态和运维能力与 Ultra 相同。指尖视触觉数据由独立 SDK 通过 USB 或 serial 通道提供，不经过本 SDK 的 Modbus/CANFD 通道，也不属于 `hand.touch` 快照。设备只读探测确认主链路存在 `mt_*` 或 `mx_*` 指腹/手掌阵列后，`hand.touch` 仅公开 5 个指腹和 1 个手掌模组。两条通道没有原子同步保证，应用需要分别管理其生命周期和时间对齐。

### 1.2 对象模型架构

[`Manager`](#21-manager) 为设备管理器，负责设备发现与连接生命周期管理；[`Hand`](#22-hand) 为单只灵巧手的设备句柄，提供设备信息与各功能模块对象：

```text
Manager (设备发现与连接管理)
└── Hand (单手设备句柄)
    ├── 设备信息与元数据
    │   ├── DeviceInfo           整手、电机与触觉模组基本信息
    │   ├── FirmwareInfo         主控、电机与触觉固件版本
    │   └── JointLayout          关节映射与自由度拓扑
    └── 功能模块对象
        ├── Motion               轨迹运动、实时流控、零力矩与软件停止
        ├── State                电机反馈快照与状态订阅
        ├── Touch                触觉区域能力、点阵触觉与力/力矩触觉采样
        ├── Health               系统诊断、电机健康与运行健康状态
        ├── ExperimentalCollision 实验性软件碰撞检测与响应
        ├── Config               设备参数与运行配置
        ├── Calibration          关节零位校准与标定
        └── Maintenance          设备重启与固件升级
```

上图只表示功能归属，不表示具体属性或方法写法。实际名称和参数见第 2 至 5 章。

## 2. 核心入口对象与基础范式

[`Manager`](#21-manager) 与 [`Hand`](#22-hand) 构成 SDK 2.0 的核心入口对象，负责设备发现、会话建立与句柄生命周期管理。

### 2.1 Manager

应用需首先创建 `Manager` 实例，负责设备发现、连接管理与句柄生命周期：

- **设备发现与连接**：
  - `list_ports()`：列出本机可见的通信端口或适配器，供 UI、CLI 和手动选择端口使用；它不访问设备，也不返回 `Hand`。
  - `discover(scan_all=False)`：扫描可用总线设备（包含端口名、传输协议与 `slave_id`）；默认找到首个可用设备即止，设置 `scan_all=True` 扫描全量设备。
  - `connect_auto()`：发现并连接一只匹配设备，适合 quickstart 和单手默认场景；可传入 `port`、`slave_id`、`protocol` 或 `model` 缩小范围。
  - `connect(detected, model=None)`：连接一个已知 `DetectedDevice`，适合应用先 `discover()` 展示设备列表，再由用户选择目标设备。
  - `connect_all(devices)`：批量连接多个已知设备，返回 `list[Hand]`；适合同一总线多手或多个 Modbus 端口的启动流程。
- **总线共享与生命周期规则**：
  - **端口独占与复用**：同一物理总线端口（如 RS485 / CANFD）仅打开一次 Transport 连接，供挂载于该总线上的多只 `Hand`（不同 `slave_id`）共享通信通信。
  - **CANFD 会话限制**：当前进程同一时刻只允许一个 CANFD Transport session；同一 CANFD 总线上的多个 `slave_id` 共享该 session。连接另一 CANFD 适配器或重新执行 CANFD discovery 前，必须先关闭现有 CANFD session；CANFD discovery 运行期间也不能建立 session。Modbus 不受此限制。
  - **句柄独立关闭**：关闭单个 `Hand` 仅释放该设备的业务句柄与引用；最后一只 `Hand` 关闭后，SDK 才真正释放端口总线连接。
  - **全局释放管理**：关闭 `Manager` 时，将原子化关闭其管理的所有 `Hand` 句柄与底层物理总线连接。
  - **异常失效机制**：发生断线与重连恢复后，旧 Hand 句柄、数据订阅与内部缓存自动失效，应用需重新获取句柄。

### 2.2 Hand

`Hand` 是连接建立后单只物理灵巧手的核心控制句柄，聚合设备元数据只读快照与功能控制子模块：

```text
Hand / revo3::Hand
├── device_info / device_info()       --> 设备基本信息 (型号/SN/左右手类型/硬件版本)
├── firmware_info / firmware_info()   --> 固件版本 (主控/驱动板/触觉)
├── joint_layout / joint_layout()     --> 关节映射布局 (13/16/21 DOF)
├── slave_id / slave_id()             --> 设备 Modbus 从机 ID
├── motion / motion()                 --> 运动控制 API (move_to, move_joint, 示教)
├── state / state()                   --> 状态读取 API (snapshot 状态快照)
├── touch / touch()                   --> 触觉传感器 API (布局、数据流与维护)
├── health / health()                 --> 健康与安全诊断 API
├── experimental_collision / experimental_collision() --> 实验性碰撞检测 API
├── config / config()                 --> 设备参数配置 API
├── calibration / calibration()       --> 关节零位与标定 API
├── maintenance / maintenance()       --> 固件升级与 DFU 维护 API
└── close()                           --> 关闭句柄并释放连接资源
```

- **资源释放责任**：支持调用 `close()` 手动关闭当前句柄；同一串口上的多设备共享总线连接，关闭单只 Hand 不会影响同端口上的其他设备。

### 2.3 基础用法示例 (Basic Usage)

Revo3 SDK 在 Python 和 C++ 中均提供一致的基础调用范式：

#### Python 基础用法

```python
import asyncio
from bc_revo3_sdk import main_mod as sdk


async def main():
    manager = sdk.Manager()
    hand = None
    try:
        hand = await manager.connect_auto()

        # 1. 读取设备元数据与布局
        info = hand.device_info
        layout = hand.joint_layout
        if layout is None:
            raise RuntimeError("Joint layout is unavailable")
        print(f"Hand Model: {info.model}, SN: {info.serial_number}")

        # 2. 从当前状态快照构造运动目标
        state = await hand.state.snapshot()
        target = list(state.positions_deg)
        target[0] = 45.0  # 调整 J0 关节目标角度 (degree)

        # 3. 发送一条运动指令并等待到位
        handle = await hand.motion.move_to(target, duration=0.8)
        result = await handle.wait(timeout=2.0)
        print(f"Motion result: {result}")
    finally:
        if hand is not None:
            await hand.close()
        await manager.close()


asyncio.run(main())
```

#### C++ 基础用法

```cpp
#include <iostream>
#include <revo3/revo3.hpp>
#include <stdexcept>
#include <vector>

using namespace std::chrono_literals;

int main() {
    revo3::Manager manager;
    auto hand = manager.connect_auto();

    // 1. 读取设备元数据
    const auto info = hand.device_info();
    std::cout << "Hand Model: " << static_cast<int>(info.model)
              << ", SN: " << info.serial_number << "\n";

    // 2. 从当前状态快照构造安全运动目标
    auto state = hand.state().snapshot();
    const auto layout = hand.joint_layout();
    if (!layout) {
        throw std::runtime_error("Joint layout is unavailable");
    }
    std::vector<float> target(
        state.motors.positions_deg,
        state.motors.positions_deg + layout->joint_count);
    target[0] = 45.0f;  // 调整 J0 关节目标角度 (degree)

    // 3. 发送运动指令并等待到位
    auto handle = hand.motion().move_to(target, 800ms);
    const auto result = handle.wait(2s);
    std::cout << "Motion result status: " << static_cast<int>(result) << "\n";

    // 4. 关闭句柄释放连接
    hand.close();
    return 0;
}
```

## 3. 设备信息与元数据

设备信息与元数据按生命周期分为**设备发现**与**设备连接**两个阶段：

- **设备发现阶段**：由 `Manager.discover()` 扫描返回 [`DetectedDevice`](#31-扫描设备-detecteddevice)，包含通信端点与基础硬件描述，作为连接输入；
- **设备连接阶段**：通过 `connect()` 或 `connect_auto()` 建立连接后，通过 [`Hand`](#22-hand) 句柄访问。

### 3.1 扫描设备 (DetectedDevice)

```text
DetectedDevice / revo3::DetectedDevice
├── protocol_type                      --> 通信协议类型 (ModbusRTU / CANFD)
├── port_name                          --> 设备串口或端口名称 (如 /dev/ttyUSB0, can0)
├── slave_id                           --> 设备 Modbus 从机 ID
├── nominal_baudrate_bps              --> RS485 波特率或 CAN 仲裁段波特率 (如 115200, 1000000)
├── data_baudrate_bps                 --> CANFD 数据段波特率 (如 5000000)；Modbus 下固定为 0
├── model                              --> 识别到的设备型号 (如 UltraTouch)
├── hand_side                          --> 识别到的左右手类型 (Left / Right)
├── serial_number                      --> 设备唯一序列号 (如 BCUTL40124000001)
├── firmware_version                   --> 主控固件版本号
└── hardware_revision                   --> 硬件修订版本号
```

### 3.2 设备信息 (DeviceInfo)

```text
DeviceInfo
├── model                              --> 产品型号 (如 UltraTouch)
├── serial_number                      --> 设备唯一序列号 (如 BCUTL40124000001)
├── hand_side                          --> 左右手类型 (Left / Right)
├── hardware_revision                   --> 硬件修订版本标识
├── motor_serial_numbers               --> 电机物理 SN 列表
└── touch_serial_numbers               --> 触觉模组物理 SN 列表
```

`DeviceInfo` 描述当前连接设备的基本信息与硬件元数据快照，用于设备识别、日志追溯和兼容性诊断。该快照在连接建立时自动获取并缓存；仅在产线测试、售后维护或显式强制同步时调用 `await hand.refresh_device_info()` 主动刷新。

若设备序列号或硬件版本缺失，`hand.device_info` 返回 `None`（不使用空字符串伪造信息）。电机与触觉部件 SN 若尚未读取或当前型号不支持，对应字段呈现为空列表 `[]`，不影响 `DeviceInfo` 本身的返回。

#### 字段说明

- **`model`**：产品型号（类型为 [`Revo3Model`](#35-产品型号枚举-revo3model)），用于决定产品系列、自由度数量与触觉模块配置。
- **`serial_number`**：设备唯一序列号（如 `"BCUTL40124000001"`），用于具体设备识别、多手日志追溯与资产管理。
- **`hand_side`**：左右手类型（`Left` / `Right`），用于运动学镜像解算、位姿变换与控制映射。
- **`hardware_revision`**：硬件修订版本标识，用于生产追溯和兼容性诊断。应用应通过具体对象 API 和结构化错误判断运行时可用性。
- **`motor_serial_numbers`**：按逻辑关节顺序排列的已知电机物理 SN 列表。
- **`touch_serial_numbers`**：已知触觉模组物理 SN 列表（无触觉型号或不支持 SN 读取时为空列表）。

#### 型号识别与显式覆盖

当前设备固件未存储独立的产品型号字段，SDK 默认根据序列号前缀自动推断 `model`：

- **常规连接**：`DetectedDevice.model` 已自动识别型号，正常调用 `connect(detected)` 或 `connect_auto()` 即可。
- **显式型号覆盖**：若旧固件序列号缺失、不正确或扫描信息不完整，可在连接时显式指定 `model`。显式覆盖优先于序列号识别，仅作用于当前连接上下文，不会写入设备固件。

::: code-group
```python [Python]
# 示例：Python 显式指定型号建立连接
hand = await manager.connect_auto(model=sdk.Revo3Model.UltraTouch)
```

```cpp [C++]
// 示例：C++ 显式指定型号建立连接
auto devices = manager.discover();
auto detected = devices.front();
detected.model = REVO3_MODEL_ULTRA_TOUCH;
auto hand = manager.connect(detected);
```
:::

触觉模组的底层协议解析状态仅用于 SDK 内部选择解析器并生成 `TouchLayout`，不包含在 `DeviceInfo` 中。应用应通过 [`hand.touch.layout`](#54-statetouch-与-health) 判断触觉布局和触觉数据形态。

```python
# 示例：读取设备基本信息与型号
info = hand.device_info
if info is not None:
    print(f"SN: {info.serial_number}, Model: {info.model}, Hand side: {info.hand_side}")
    print(f"Motor SN count: {len(info.motor_serial_numbers)}, Touch SN count: {len(info.touch_serial_numbers)}")
```

### 3.3 固件信息 (FirmwareInfo)

```text
FirmwareInfo
├── controller_firmware_version
├── motor_firmware_versions
└── touch_firmware_versions
```

固件信息与设备基本信息及硬件元数据分开，在升级或重新连接后必须重新读取。主控固件属于设备本体，但它仍是软件版本，因此保留在 `FirmwareInfo`。各字段含义如下：

- **`controller_firmware_version`**：主控板固件版本，决定系统级协议、总线调度与主控通信能力。
- **`motor_firmware_versions`**：当前已知的各电机驱动板固件版本，按逻辑关节顺序排列。
- **`touch_firmware_versions`**：当前已知的触觉模组固件版本；非 Touch SKU 该列表为空。

空列表表示当前快照中没有已知版本，可能是设备没有对应模组，也可能是尚未读取到版本；当前 API 不提供固件清单完整性字段。需要刷新组件版本时调用 `await hand.refresh_firmware_info()`。

```python
# 示例：读取主控与电机/触觉板固件版本列表
fw = hand.firmware_info
print(f"Controller FW: {fw.controller_firmware_version}, Motor FW count: {len(fw.motor_firmware_versions)}")
```

### 3.4 关节布局模型 (JointLayout)

Python 和 C++ 的 `hand.joint_layout` 用于确认当前布局和数组长度。该属性包含 `layout_id`、`version` 和 `joint_count`：

```text
JointLayout
├── layout_id                          --> 运动学关节拓扑标识 (如 Revo3Ultra21 / Revo3Pro16 / Revo3Basic13，多款触觉型号共享)
├── version                            --> 布局协议规范的版本号 (当前为 1)
└── joint_count                        --> 逻辑关节总数 (21 / 16 / 13)
```

21 DOF Ultra 布局使用下面的固定逻辑顺序。读取 Pro 和 Basic 元数据的工具应根据 `JointLayout.joint_count` 解释 16/13 DOF 布局，不能按 21 个有效关节处理；这不表示 Motion、State、Touch、Health、Config、Calibration 或 Maintenance 已对这些型号开放。Ultra 运行时的位置和速度限制从 `DeviceConfig` 读取；控制器通道由 SDK 在协议层完成映射，不进入 Python/C++ API。

Python 在布局尚不可用时返回 `None`；C++ 返回 `std::optional<JointLayout>`，调用者应先检查是否有值。两种语言中的 `layout_id` 均为稳定字符串 schema ID，不使用关节数量代替布局标识。

`JointLayout` 是由当前连接上下文中已识别的产品型号派生的只读元数据。SDK 不提供 `set_joint_layout()` 或关节布局 override；旧固件序列号缺失、不正确或扫描信息不完整时，应在连接阶段通过 `model` 参数显式修正型号。该修正仅作用于当前连接上下文，不写入设备固件，也不会绕过对应型号的 runtime 能力检查。

```python
# 示例：获取关节布局 ID 与关节数
layout = hand.joint_layout
print(f"Layout: {layout.layout_id}, Joint Count: {layout.joint_count}")
```

当前 21 DOF 逻辑分组为：

| 分组 | 逻辑索引 | 关节数 |
| --- | --- | ---: |
| Pinky | 0..3 | 4 |
| Ring | 4..7 | 4 |
| Middle | 8..11 | 4 |
| Index | 12..15 | 4 |
| Thumb | 16..20 | 5 |

Thumb 公共逻辑顺序为 Rotation、MCP、IP、Abd、Flex。协议适配层负责转换控制器通道顺序。

### 3.5 产品型号枚举 (Revo3Model)

`Revo3Model` 定义 SDK 可识别的 Revo3 型号值。枚举存在不等于该型号已进入 SDK runtime 支持范围；产品生命周期与 runtime 状态分别列出。

| 枚举名称 (Revo3Model) | C/C++ 标识 | 自由度 (DoF) | 触觉类型 (Touch) | 序列号前缀 | 产品状态 | SDK runtime 状态 |
| :--- | :--- | :---: | :--- | :--- | :--- | :--- |
| `Ultra` | `REVO3_MODEL_ULTRA` | 21 | 无触觉 | `UBL` / `UBR` | 已发布 | 已开放；Modbus/CANFD |
| `UltraTouch` | `REVO3_MODEL_ULTRA_TOUCH` | 21 | 集成触觉 | `UTL` / `UTR` / `UFL` / `UFR` | 已发布 | 已开放；精确产品代码优先确定触觉拓扑，旧版 SN 回退到只读寄存器探测 |
| `UltraVisionTouch` | `REVO3_MODEL_ULTRA_VISION_TOUCH` | 21 | 视触觉 + 可选主链路阵列 | `UVL` / `UVR` | Hardware Pilot | 整手功能已开放；指尖视触觉使用独立 SDK；探测到的 `mt_*`/`mx_*` 指腹和手掌通过 Touch API 读取 |
| `Pro` | `REVO3_MODEL_PRO` | 16 | 无触觉 | `PBL` / `PBR` | 已发布 | 仅设备识别与 `JointLayout`；运行时功能域未开放 |
| `ProTouch` | `REVO3_MODEL_PRO_TOUCH` | 16 | 点阵触觉 (Array Touch) | `PTL` / `PTR` | 已发布 | 仅设备识别与 `JointLayout`；运行时功能域未开放 |
| `Basic` | `REVO3_MODEL_BASIC` | 13 | 无触觉 | `DBL` / `DBR` | Hardware Pilot | 仅设备识别与 `JointLayout`；运行时功能域未开放 |
| `BasicTouch` | `REVO3_MODEL_BASIC_TOUCH` | 13 | 点阵触觉 (Array Touch) | `DTL` / `DTR` | Hardware Pilot | 仅设备识别与 `JointLayout`；运行时功能域未开放 |

去除可选的 `BC` 前缀后，Ultra 系列 SN 的前 4 个字符可进一步确定触觉配置：

| 产品代码 | 主链路触觉配置 |
| --- | --- |
| `UTL1` / `UTR1` | `mt_*` 全手阵列 |
| `UTL2` / `UTR2` | `mx_*` 全手阵列 |
| `UFL1` / `UFR1` | 仅 5 个 `hp_fingertip_ft` 指尖模组 |
| `UFL2` / `UFR2` | `hp_fingertip_ft` 指尖 + `mt_*` 指腹/手掌 |
| `UFL3` / `UFR3` | `hp_fingertip_48` 指尖 + `mt_*` 指腹/手掌 |
| `UVL1` / `UVR1`、`UVL2` / `UVR2` | 独立视触觉指尖 + 主链路 `mt_*` 指腹/手掌 |
| `UVL3` / `UVR3`、`UVL4` / `UVR4` | 独立视触觉指尖 + 主链路 `mx_*` 指腹/手掌 |

SDK 将已知的 4 字符产品代码作为触觉配置依据，不再用可能未同步的寄存器 135/136
覆盖它。没有末位型号或末位型号未知时，仍使用原有寄存器和只读元数据探测。

### 3.6 连接、日志与升级目标枚举

Python 公开整数枚举提供只读 `int_value` 属性，用于取得与 C ABI/协议值一致的整数表示；业务逻辑仍应优先比较枚举成员，不直接写死整数。

#### ProtocolType (枚举)

`ProtocolType` 用于扫描和连接参数。`Auto` 只表示由 SDK 选择已支持的传输，不是独立的设备协议。

| 枚举项 | 数值 | 描述说明 |
| --- | ---: | --- |
| `Auto` | `0` | 自动探测 Modbus RTU 或 CANFD |
| `Modbus` | `1` | 通过 RS485 使用 Modbus RTU |
| `CanFd` | `3` | 使用 CANFD |

#### Rs485Baudrate (枚举)

Python 连接 API 使用该强类型枚举。C++ `DiscoveryOptions.modbus_baudrate` 当前使用 bps 整数值。

| 枚举项 | 数值 | 线路速率 |
| --- | ---: | ---: |
| `Baud1Mbps` | `1` | 1,000,000 bps |
| `Baud2Mbps` | `2` | 2,000,000 bps |
| `Baud3Mbps` | `3` | 3,000,000 bps |
| `Baud5Mbps` | `5` | 5,000,000 bps |

#### CanFdBaudrate (枚举)

Python 连接 API 使用该强类型枚举；C++ `DiscoveryOptions.canfd_data_baudrate` 当前使用 bps 整数值。该枚举表示 CANFD 数据域速率；仲裁域速率由适配器和传输实现确定，不通过此枚举配置。

| 枚举项 | 数值 | 数据域速率 |
| --- | ---: | ---: |
| `Baud1Mbps` | `1` | 1,000,000 bps |
| `Baud2Mbps` | `2` | 2,000,000 bps |
| `Baud4Mbps` | `4` | 4,000,000 bps |
| `Baud5Mbps` | `5` | 5,000,000 bps |

#### LogLevel (枚举)

该枚举用于 Python `init_logging()`、C ABI `revo3_init_logging()` 和 C++ `revo3::init_logging()`。

| 枚举项 | 数值 | 描述说明 |
| --- | ---: | --- |
| `Error` | `0` | 仅错误日志 |
| `Warn` | `1` | 警告和错误日志 |
| `Info` | `2` | 常规运行信息，默认级别 |
| `Debug` | `3` | 调试信息 |
| `Trace` | `4` | 最详细的跟踪信息 |

#### FirmwareTarget (枚举)

Python 类型名为 `FirmwareTarget`，C++ 类型名为 `FirmwareTarget`。

| Python 枚举项 | C++ 枚举项 | 数值 | 描述说明 |
| --- | --- | ---: | --- |
| `MainFirmware` | `MainFirmware` | `0` | 主控制器固件 |
| `Image` | `Image` | `1` | 设备镜像目标；仅在对应固件明确支持时可用 |
| `MotorFirmware` | `MotorFirmware` | `2` | 电机模组固件 |

枚举成员只标识升级目标，不代表当前设备、固件或传输支持该目标。非主控制器目标还要求固件支持目标寄存器的写入与回读确认；确认失败时升级操作失败，不得自动改写为其他目标。

## 4. Hand 功能域 API

Hand 的能力按用户职责组织如下：

| 职责分组 | API 章节 | 主要用途 |
| --- | --- | --- |
| 运动控制 | [4.1 Motion 运动控制 API](#41-motion-运动控制-api) | 轨迹运动、关节/手指/拇指控制、实时 Servo、拖拽、示教与回放 |
| 状态读取 | [4.2 State 状态读取 API](#42-state-状态读取-api) | 读取关节位置、速度、电流、故障码和状态订阅 |
| 触觉数据 | [4.3 Touch 触觉数据 API](#43-touch-触觉数据-api) | 触觉布局、快照、订阅、模组配置、校准和维护 |
| 健康与安全 | [4.4 Health 系统诊断与安全状态 API](#44-health-系统诊断与安全状态-api) | 系统状态、电源/温度、电机诊断、安全状态和故障清除 |
| 碰撞保护 | [4.5 ExperimentalCollision 实验性碰撞保护 API](#45-experimentalcollision-实验性碰撞保护-api) | 软件碰撞检测配置、锁存状态读取和复位 |
| 运行配置 | [4.6 Config 配置 API](#46-config-配置-api) | 蜂鸣器、振动、触屏、广播 ID、保护电流和运行参数 |
| 标定 | [4.7 Calibration 标定 API](#47-calibration-标定-api) | 关节零点、软限位、力控相关标定流程 |
| 设备维护 | [4.8 Maintenance 维护 API](#48-maintenance-维护-api) | 重启、固件升级、升级中止、状态恢复和恢复出厂设置 |

### 4.1 Motion 运动控制 API

Motion 按职责分为：

- **目标轨迹运动**：`move_to()`、`move_joint()`、`move_finger()`、`flex_finger()`、`move_thumb()`。
- **实时流式控制**：`open_servo()` 与 `ServoSession.send_*()`。
- **托管拖拽控制**：`start_servo_drag()`、`update_servo_drag()`、`stop_servo_drag()`、`cancel_servo_drag()`。
- **示教与回放**：`teach_joint()`、`teach_hand()`、`replay_joint()`、`replay_hand()`。

#### 4.1.1 轨迹运动 API：move_to、move_joint、move_finger 与 move_thumb

> [!NOTE]
> **底层轨迹与下发机制**：`move_to()`、`move_joint()`、`move_finger()` 和 `move_thumb()` 在 SDK 底层均基于**五次平滑多项式 (Quintic Polynomial Trajectory)** 进行连续轨迹插值，确保起点与终点的速度和加速度连续光滑。插值过程中，SDK 内部以高频插值周期将当前位置与速度序列转化为 **五项 MIT 混合控制指令 (Kp, Kd, Pos, Vel, Feedforward Current)** 实时下发至灵巧手驱动器。公共 API 的反馈与前馈量保持命名为 `current` / `current_ma`；设备不提供已标定的关节力矩反馈，因此不把电流错误标注为 `torque`。

整手按指定时长运动使用 `move_to()`：

```python
# 示例：整手按指定时长运动至目标姿态
target_positions = [0.0] * 21  # 21 个关节的目标位置，单位为 degree
handle = await hand.motion.move_to(target_positions, duration=2.0)
await handle.wait(timeout=3.0)
```

```cpp
// 示例：C++ 整手按指定时长运动
std::vector<float> target_positions(21, 0.0f);
auto handle = hand.motion().move_to(target_positions, std::chrono::seconds(2));
handle.wait(std::chrono::seconds(3));
```

单关节按指定时长运动使用 `move_joint()`：

```python
handle = await hand.motion.move_joint(joint_index=0, target_position=15.0, duration=1.0)
```

单手指按指定时长运动使用 `move_finger()` 和 `flex_finger()`：

```python
# move_finger: 传入 4 个关节目标位置 [Abd, MCP, PIP, DIP]
handle = await hand.motion.move_finger(finger_index=1, target_positions=[0.0, 30.0, 45.0, 20.0], duration=1.0)

# flex_finger: 简易弯曲控制
handle = await hand.motion.flex_finger(finger_index=1, flexion_position=60.0, duration=1.0)
```

拇指按指定时长运动使用 `move_thumb()`：

```python
# move_thumb: 传入 5 个关节目标位置 [Rotation, MCP, IP, Abd, Flex]
handle = await hand.motion.move_thumb(target_positions=[10.0, 20.0, 30.0, 0.0, 40.0], duration=1.0)
```

`move_to()`、`move_joint()`、`move_finger()` 与 `move_thumb()` 的动作对应表：

| 方法名称 | 目标数组长度 (21-DOF 手型) | 对应含义 |
| :--- | :---: | :--- |
| `move_to()` | 21 | 控制全手 21 个关节的目标位置 |
| `move_joint()` | 1 | 控制索引为 `joint_index` (0..20) 的单个关节 |
| `move_finger()` | 4 | `finger_index` 为 `1=Index`, `2=Middle`, `3=Ring`, `4=Pinky`；21-DOF 手型上传入 4 个角度，按 Abd, MCP, PIP, DIP 顺序解算 |
| `flex_finger()` | 1 | 与 `move_finger()` 相同的 `finger_index`；`flexion_position` 作用于 MCP、PIP、DIP 关节，Abd 关节维持当前反馈位置 |
| `move_thumb()` | 5 | 21-DOF 手型上传入 5 个角度，按 Rotation, MCP, IP, Abd, Flex 顺序解算 |

`move_joint()` 支持与 `move_to()` 相同的 `duration`/`speed`、统一 `kp/kd` 和 `dt` 参数。`move_finger()`、`flex_finger()` 和 `move_thumb()` 均按时长控制，并支持可选的统一或逐关节 `kp/kd`。`move_finger()` 为全姿态控制（包含侧摆 Abd）；`flex_finger()` 为语义弯曲控制，适合快速上手、抓握动作或 GUI 控制。四者均返回 `OperationHandle`，低频重规划时可以互相替换或替换 `move_to()`（旧句柄变为 `Preempted`）；四者均与 `open_servo()` 冲突。

#### 4.1.2 实时流式控制 (open_servo)

调用 `hand.motion.open_servo()` 可建立 `ServoSession`。调用者可通过 `send_position()`、`send_velocity()`、`send_current()`、`send_impedance()` 或 `send_mit()` 发送目标。

```python
# 示例：打开高频实时流式控制会话
session = hand.motion.open_servo()
try:
    for _ in range(100):
        await session.send_position([0.0] * 21)
        await asyncio.sleep(0.01)
finally:
    session.close()
```

```cpp
// 示例：C++ 实时流式控制会话
auto session = hand.motion().open_servo();
std::vector<float> targets(21, 0.0f);
for (int i = 0; i < 100; ++i) {
    session.send_position(targets);
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
}
session.close();
```

#### 4.1.3 托管拖拽控制 (start_servo_drag)

对于仅在目标变化时产生事件的控制源（如 GUI Slider），使用 `Motion.start_servo_drag(joint_index, target_position)` 启动拖拽，通过 `update_servo_drag(joint_index, target_position)` 传入最新目标。松开滑条时调用 `stop_servo_drag(joint_index, final_position)` 发送保持帧；主动取消或断线清理时调用 `cancel_servo_drag(joint_index)` 停止写控制帧。`filter_mode` 使用 [`ServoFilterMode`](#servofiltermode-枚举)，不接受无类型的整数模式值。

#### 4.1.4 实时控制入口对比：open_servo 与 start_servo_drag

针对实时发包和连续运动场景，SDK 提供了两类不同层级的控制入口：

- **`open_servo()`**（用户循环托管）：打开一个 `ServoSession`，把高频实时控制权移交给调用方自建的循环。适合 VR 手套、遥操作、外部策略或强化学习（RL）按 5–20ms 周期自主发包。
- **`start_servo_drag(...)`**（SDK 后台托管）：在 SDK 内部启动一个单关节后台发包 Worker。适合 GUI 滑条拖动、鼠标滑动控制，调用方只需在目标变化时轻量调用 `update_servo_drag()`，SDK 自动按固定周期维持下发，并提供平滑滤波、限速与碰撞保护。

**核心特性对比表**：

| 对比维度 | `open_servo()`（流式会话） | `start_servo_drag()`（托管拖拽） |
| :--- | :--- | :--- |
| **一句话定位** | **“把实时控制权交给用户循环”** | **“SDK 帮你托管一个单关节拖动循环”** |
| **适用场景** | 遥操作、VR 手套、算法/RL 每 5-20ms 连续更新多关节 | GUI Slider 拖动、面板交互、鼠标滑动控制 |
| **控制权托管** | **用户循环**（用户负责外层 loop 和发包频率） | **SDK 后台**（SDK Worker 自动按固定周期连续发包） |
| **控制粒度** | 整手命令帧，数组长度必须等于当前 `joint_count` | 单关节 (Joint) |
| **方法列表** | `send_position()`, `send_velocity()`, `send_mit()` 等 | `start_servo_drag()`, `update_servo_drag()`, `stop_servo_drag()` |
| **生命周期管理** | 需显式 `session.close()` 释放，支持 `command_timeout_ms` 自动超时 Expire | 释放滑条用 `stop_servo_drag()`（发送保持帧）；收尾或中断用 `cancel_servo_drag()` |
| **高级保护** | 需算法层控制轨迹平滑 | 包含滤波、速度限制、碰撞保护与空闲保持 (Idle Hold) |

**1. `open_servo()` 会话说明**：
调用 `hand.motion.open_servo()` 会打开一个 `ServoSession`。用户按自己的控制流程调用 `send_position()`、`send_velocity()`、`send_current()`、`send_impedance()` 或 `send_mit()` 提供新目标。`command_timeout_ms` 表示相邻两次命令允许的最长间隔；超时后 `ServoSession.state` 变为 `Expired`，SDK 释放软件控制权，并拒绝该会话继续发送命令。

当前所有 `ServoSession.send_*()` 方法都接收完整整手命令帧，各数组长度必须等于当前设备的 `joint_count`。调用者可以只改变目标数组中的部分关节值，但仍须为其他关节提供明确目标；SDK 不公开隐式沿用上一帧或自动读取反馈值的单关节、手指、拇指流控方法。

**2. `start_servo_drag()` 拖拽说明**：
对于仅在目标变化时产生事件的控制源（如 GUI Slider），使用 `Motion.start_servo_drag(joint_index, target_position)` 启动拖拽，通过 `update_servo_drag(joint_index, target_position)` 传入最新目标。松开滑条时调用 `stop_servo_drag(joint_index, final_position)` 发送保持帧；主动取消或断线清理时调用 `cancel_servo_drag(joint_index)` 停止写控制帧。C ABI 对应 `revo3_device_*_servo_drag`。

#### 4.1.5 示教与回放 API

`teach_joint()` 和 `teach_hand()` 在指定时间内采集关节反馈位置，返回可用于后续回放的轨迹数组。`replay_joint()` 和 `replay_hand()` 按给定 `dt`、`kp` 和 `kd` 回放轨迹。它们属于 Motion 域 API，执行时会占用运动控制权，并与 `move_to()`、局部轨迹运动、`open_servo()` 和 拖拽控制互斥。

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

### 4.2 State 状态读取 API

`HandState` 包含每个电机的 `operating_states`、position、velocity 和 current。高频状态读取覆盖输入寄存器 2000..2110，不读取低频诊断区。位置单位为 deg，速度单位为 rpm，电流单位为 mA。逐电机故障码、系统状态和全局错误码从 `HealthSnapshot` 读取。读取失败时调用返回 `SdkError`。

State 还包含一个接收 `timestamp`。Linux SocketCAN 使用最后一个状态响应的 `SO_TIMESTAMPNS` 内核软件时间，其他 CANFD 和 Modbus 路径记录 SDK 完成读取的时间。只有 `clock` 相同的 timestamp 才能比较。它不是固件采样时间，也不能用于跨设备同步。

```python
# 示例：读取电机控制反馈状态快照或开启 50Hz 异步订阅
snapshot = await hand.state.snapshot()
print(f"Current positions (deg): {snapshot.positions_deg}")

# 异步订阅
sub = hand.state.subscribe(period=0.02)
try:
    frame = await sub.next()
finally:
    sub.close()
```

### 4.3 Touch 触觉数据 API

SDK 公开原始触觉数据，并使用 `TouchLayout` 和统一 `TouchFrame` 表达。用户可以读取：

- `mt_*`：包含 11 个手掌/手指模块，支持 `PointArray` 点阵模式与少量已发货设备使用的 42 值二次标定兼容模式 `LegacyForceSummary`；后者后续将删除。
- `mx_*`：包含 11 个手掌/手指模块，点数从设备只读寄存器动态读取。
- `hp_*`：包含 5 个指尖模块。`hp_fingertip_48` 提供 48 点点阵、三轴力、二轴力矩和模块区域合力；`hp_fingertip_ft` 不带点阵，仅提供后三类信号。
- `hp_* + mt_*`：组合触觉，11 个公开 module 采用与协议物理 ID 对齐的稀疏编号：module 0 为 `mt_*` 手掌，module 1/3/5/7/9 为 `hp_*` 指尖，module 2/4/6/8/10 为 `mt_*` 指腹。指尖与指腹各自的序号按拇指、食指、中指、无名指、小指递增（1/3/5/7/9 与 2/4/6/8/10 分别对应拇指至小指）；不公开组合硬件中未纳入布局的 `mt_*` 指尖通道。
- `hp_* + mx_*`：组合触觉，稀疏编号同上：module 0 为 `mx_*` 手掌，module 1/3/5/7/9 为 `hp_*` 指尖，module 2/4/6/8/10 为 `mx_*` 指腹。
- `hp_* + mx_* + mt_*`：分区组合触觉，module 0 为 `mt_*` 手掌，module 1/3/5/7/9 为 `hp_*` 指尖，module 2/4/6/8/10 为 `mx_*` 指腹。
- Ultra VisionTouch 主链路阵列：只读元数据明确识别 `mt_*` 或 `mx_*` 后，公开 6 个 module；module 0 为手掌，module 2/4/6/8/10 为拇指至小指的指腹。独立视触觉指尖不出现在该布局或快照中。

触觉 API 的基础能力范围如下。组合触觉布局按其包含的模组类型路由操作；不支持的操作返回 `UnsupportedCapability`，且不会向设备发送命令。

| 能力 | `mt_*` | `mx_*` | `hp_*` |
|------|:------:|:------:|:------:|
| `snapshot()` / `subscribe()` | ✓ | ✓ | ✓ |
| 模组 enable/mask | ✓ | ✓ | ✓ |
| `read_mode()` / `set_read_mode()` | ✓ | — | — |
| `value_mode()` / `set_value_mode()` | ✓ | ✓ | — |
| `tare()` | ✓ | ✓ | ✓ |
| `cancel_tare()` / `tare_status()` | — | ✓ | — |
| `point_counts()` / `restart()` | — | ✓ | — |

`value_mode()` / `set_value_mode()` 对外仅提供 `Adc` (0) 与 `Force` (2)。`mt_*` 寄存器 `4024` 的值 `1` 未使用，不属于公开枚举。表格用于快速判断基础能力，具体参数、返回值和组合布局行为以本节后续契约为准。

以上均指通过灵巧手主通信链路读取的集成触觉模组。Ultra VisionTouch 的 5 个指尖视触觉模组通过独立 SDK 和 USB/serial 通道读取，不进入 `hand.touch`、`TouchLayout`、`TouchFrame` 或 `TouchSubscription`；部分整手还组合 `mt_*` 或 `mx_*` 指腹/手掌模组。设备发现会通过只读元数据识别这类主链路阵列模组，并显示为 `vision_tips+mt_pads+mt_palm` 或 `vision_tips+mx_pads+mx_palm`。识别成功时，公共 Touch API 返回 module 0/2/4/6/8/10 对应的手掌和 5 个指腹；不会创建缺失的指尖 module，也不会拼接独立通道数据。两类元数据同时有效或都无有效证据时保持未解析，Touch 能力 fail-closed。

当前声明的组合触觉布局包括 `hp_*` 指尖 + `mt_*` 指腹/手掌、`hp_*` 指尖 + `mx_*` 指腹/手掌，以及 `hp_*` 指尖 + `mx_*` 指腹 + `mt_*` 手掌。三种布局均使用 11 个稳定公开 module ID。其他未确认逐模块寄存器映射的组合拓扑保持 fail-closed，不会伪造或拼接不完整的触觉帧。

1. `TouchLayout`：按 `TouchRegion` 提供区域分组，并按 module 提供点阵 layout 与 `TouchSignal` 数据形态。
2. `TouchFrame`：包含接收 timestamp、序列号和统一的 `TouchModuleData` 数组；区域合力按模块写入 `TouchModuleData.regional_forces_mn`。
3. `TouchModuleData`：每个模块都包含区域、区域内序号、稳定 module ID、layout ID 和统一采样状态；点阵 `points` 及 `force3d`、`torque2d`、`resultant_force_mn` 按帧模式和模块能力选择性返回。原始协议状态仅通过可选的 `diagnostics` 提供。所有公开力值统一使用 mN。

`TouchLayout.regions` 只保存区域与 `module_ids` 分组；`TouchLayout.modules` 保存完整 module 级布局，包括 `module_id`、`region`、`region_index`、`signals`、`point_count` 和 `layout_id`。其中 `layout_id` 是公开的 schema key，用来描述模块布局和能力。`TouchSignal` 包含 `TouchPoint`、`Force3D`、`Torque2D` 和 `ResultantForce`。模组状态由每帧必有的 `sample_state` 统一表达，不作为可选信号。`LegacyForceSummary` 是读取模式，不属于单模组信号，因此不加入 `TouchSignal`。`TouchFrame` 和 `TouchLayout` 不暴露 `TouchPayloadType`。`TouchReadMode`（`4023`）仅用于 `mt_*` 模组：`PointArray` (0) 返回点阵数据，点值类型由 `4024` 的 `Adc` (0) / `Force` (2) 决定；`LegacyForceSummary` (1) 返回二次标定区域合力值，仅兼容少量已发货设备，后续将删除。新应用不应形成依赖；`mx_*` 使用自己的 `output_mode`。该寄存器不是 layout 标识。其他触觉协议不保证存在该寄存器或该语义。无法识别触觉寄存器映射时，`snapshot()` 返回不支持错误。

`mt_*` 固件可能在写 ACK 后延迟应用 `read_mode` 或 `value_mode`。对应 setter 在返回成功前会回读目标寄存器，最长等待 5 秒；因此成功返回后的下一帧可以按新模式解释。设备明确拒绝写入时返回 `NotApplied`，超时或回读失败时不假定模式已经切换。

公开操作参数统一使用 `module_index`，取值为目标模块的公开 `module_id`。Revo3 SDK 2.0 将 `module_id` 定义为本次布局内稳定的逻辑模组 ID。纯 `mt_*` / `mx_*` 布局下 `module_id` 为 0~10 密集编号，且与 `TouchLayout.modules`、`TouchFrame.modules` 的数组下标一致；组合拓扑下 `module_id` 采用与协议物理 ID 对齐的稀疏编号（手掌 0、`hp_*` 指尖奇数 1/3/5/7/9、指腹偶数 2/4/6/8/10），而 `TouchLayout.modules` 和 `TouchFrame.modules` 数组按指尖、指腹、手掌顺序紧凑排列，数组下标与 `module_id` 不再一致，应用必须按 `module_id` 匹配模块，不得用数组位置代替。该规则适用于 `TouchLayout`、`TouchFrame` 和区域分组。底层寄存器的其他私有编号只存在于 SDK 私有路由层，不接受应用直接传入，也不写入公开帧。新增硬件拓扑必须先在私有路由层完成映射，不得改变既有 2.0 公开 module ID。自定义布局必须与 SDK 支持的规范布局逐字段一致（包括 `modules` 顺序与 `module_id`），否则在设备请求前返回参数错误。

`mx_*` 的点位数量寄存器不随 `output_mode` 改变。ADC 和力值模式均将每个输入寄存器按高字节、低字节解包为两个 `uint8` 点位。手掌/指尖/指腹的最大容量分别为 `200/80/120` 个点，实际有效点数以输入寄存器 `5191~5201` 为准。ADC 模式的取值范围为 `0~255`；力值模式的协议分辨率为 `10 mN`，SDK 在解码边界完成换算，`TouchFrame.modules[*].points` 直接返回 mN。`TouchLayout.point_count` 与 `TouchFrame.modules[*].points` 的实际长度一致。

当前固件将 SN、点位数量和点阵数据映射到 Modbus 输入寄存器，使用功能码 `0x04` 读取。兼容期内，SDK 在每次建立连接后通过 `5191~5201` 探测一次寄存器映射：优先使用输入寄存器，仅当保持寄存器返回唯一有效点数时回退到旧版 `0x03` 映射。探测结果在当前连接会话内缓存；若两种映射均有效但内容冲突，操作失败，不静默选择其中一种。

`LegacyForceSummary` 与 `ResultantForce` 不是同一层级的概念：前者是 `mt_*` 的二次标定兼容读取模式，其 42 个值按布局切片写入对应的 `TouchModuleData.regional_forces_mn`；后者是单个 `hp_*` 模块提供的合力信号，对应 `TouchModuleData.resultant_force_mn`。`resultant_force_mn` 是整个模块触觉区域的标量合力，单位 mN，不是局部 Z 轴上的 `Fz` 分量；`force3d` 的三个分量也统一使用 mN。

组合触觉的 `snapshot()` 在同一次 SDK 操作中依次读取 `hp_*` 指尖、当前布局声明的指腹模组和手掌模组。`snapshot(module_indices=[...])` 只读取指定的已启用模块，并按请求中的 module ID 顺序返回；`module_snapshot(module_index)` 返回单个模块。选择式读取不改变设备的 `enabled_mask`。空列表、重复 module ID 或当前布局不存在的 module ID 会在触觉数据请求前返回参数错误。任一已选择分支读取失败时，整个操作失败，不发布部分拼接帧。`mt_*` 区域处于 `PointArray` 时，每个已选择且已启用的点阵模块产生一次数据读取，因此原本 6 个 `mt_*` 指腹/手掌模块的数据读取可按需降为 1~6 次；启用状态读取以及首次未缓存的模式读取属于额外控制 RTT。`LegacyForceSummary` 读取共享的 42 寄存器摘要，选择一个或多个 `mt_*` 模块均为一次摘要数据读取。`mx_*` 区域仍按其运行时 `point_count` 和 `output_mode` 返回模块数据。

`PointArray` 与 `LegacyForceSummary` 是互斥读取模式。兼容模式帧中的 `points = None` 只表示该帧模式不返回点阵，不表示模组未采样或不可用。两种模式可能使用不同的采样流程、滤波或标定算法；切换模式前后的二次标定区域合力与 points 不保证来自同一次物理采样，SDK 不将相邻的两类帧拼接为原子样本。

`hp_*` 模组的 `force3d.x/y/z` 分别表示模组局部坐标系下的 `Fx/Fy/Fz`，单位 mN；`torque2d.x/y` 分别表示绕局部 X/Y 轴的 `Mx/My`，单位 Nm。正方向遵循模组坐标图中的箭头，力矩方向遵循图示的右手定则。SDK 根据设备触觉类型选择布局：`hp_fingertip_48` 的 `point_count` 为 48，`signals` 包含 `TouchPoint`，有效帧返回 48 个 `points`；`hp_fingertip_ft` 的 `point_count` 为 0，`signals` 不包含 `TouchPoint`，所有帧的 `points` 均为 `None`。两种布局均提供 `Force3D`、`Torque2D` 和 `ResultantForce`。当 SN 不包含已知的 4 字符产品代码且旧固件未提供明确触觉类型时，SDK 在连接阶段探测第一个 `hp_*` 模组：先读取 38 个输入寄存器，仅当设备明确返回 `Illegal Data Address` 时才尝试 14 个寄存器并识别为 `hp_fingertip_ft`；超时或其他通信错误不会触发布局降级。五个模组始终使用 38 个寄存器的固定地址步长。

Python 的 `hand.touch.layout` 返回 `TouchLayout | None`。C++ 的 `hand.touch().layout()` 返回 `TouchLayout`，触觉布局不可用时抛出 `SdkError`，不会返回空布局。

当 Revo3 Ultra Touch 或 Ultra VisionTouch 的 SN 不包含已知的 4 字符产品代码，且寄存器 135 无效或当前固件尚未提供可识别 topology 时，SDK 不按产品大类猜测布局。若 SN 也无法识别产品型号，连接时必须先通过 Python `Manager.connect(..., model=Revo3Model.UltraVisionTouch)` / `connect_auto(..., model=...)` 或 C/C++ `DetectedDevice.model` 显式覆盖型号。应用在依据实物 BOM、受控生产记录或真机对照确认布局后，可调用 `await hand.touch.set_layout(layout)` 主动配置当前连接会话。该方法只更新 SDK 的解析路由和 layout 缓存，不写设备寄存器；设备重连后必须重新确认并设置。输入必须完整匹配 SDK 支持的 `mt_*`、`mx_*`、`hp_*` 或已批准组合布局，包括 module ID、region、region index、signals、point count 和 `layout_id`，否则在发送任何设备请求前返回参数错误。Ultra VisionTouch 只接受由 module 0/2/4/6/8/10 组成的主链路 `mt_*` 或 `mx_*` 指腹/手掌布局；独立视触觉指尖不得写入该布局，也不进入公共 Touch API。其他型号不支持此 override。

部分早期组合硬件的寄存器 135 仍返回纯 `hp_*` 兼容值。对于没有已知 4 字符产品代码的 SN，SDK 会在发现阶段执行无重试、只读的模组元数据探测：有效的 `mt_*` enable 元数据可将会话布局细化为 `hp_* + mt_*`，有效的 `mx_*` SN 元数据可细化为 `hp_* + mx_*`。读取成功但内容全零不构成硬件存在证据；两类元数据同时有效时保持纯 `hp_*` 并记录歧义，不猜测分区组合。`mt_*` 模组全部关闭时，enable 元数据无法提供肯定证据，应用仍需依据已确认的实物布局调用 `set_layout()`。探测只影响当前连接会话，不写回寄存器 135。

对于包含 `mx_*` 的布局，自动识别路径在成功读取设备点数寄存器前不发布推测的 `TouchLayout`。主动设置路径将调用方提供的 point count 作为本次会话的受信布局输入；应用必须使用目标手实际点数，不得填入容量上限代替实测值。

```text
Hand
└── Touch
    ├── layout -> TouchLayout | None
    ├── set_layout(layout)
    ├── snapshot(module_indices=None) -> TouchFrame
    ├── module_snapshot(module_index) -> TouchModuleData
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
# 示例：寄存器 topology 不可用时，使用已确认的规范布局恢复当前会话
modules = [
    TouchModuleLayout(
        layout_id="mt_palm_36",
        module_id=0,
        region=TouchRegion.Palm,
        region_index=0,
        signals=[TouchSignal.TouchPoint],
        point_count=36,
    ),
    # 其余 module 必须按目标手的完整规范布局提供，此处省略。
]
layout_override = TouchLayout(modules)
await hand.touch.set_layout(layout_override)

# 示例：读取触觉布局与触觉数据快照
layout = hand.touch.layout
if layout:
    for region in layout.regions:
        print(region.region, region.module_ids)
    for module in layout.modules:
        print(module.module_id, module.layout_id, module.point_count, module.signals)
    frame = await hand.touch.snapshot()
    selected = await hand.touch.snapshot(module_indices=[0, 2, 4])
    palm = await hand.touch.module_snapshot(0)
    print(f"Touch modules: {len(frame.modules)}")
    for module in frame.modules:
        if module.regional_forces_mn is not None:
            print(module.region, module.region_index, module.regional_forces_mn)
    print(f"First module: state={frame.modules[0].sample_state}, points={frame.modules[0].points}")
```

连续读取使用订阅对象。`period` 是 SDK 拉取间隔，不是固件采样周期承诺。`TouchSubscription.next()` 返回下一帧 `TouchFrame`，`close()` 释放订阅。

```python
sub = hand.touch.subscribe(period=0.02)
try:
    frame = await sub.next()
finally:
    sub.close()
```

触觉模块“启停”是指是否启用某个物理触觉传感器进行采样。启用后模块采集并返回触觉数据；停用后模块不再采样，其 `sample_state` 通常为 `Disabled`。

`enabled_mask` 是同时表示多个模块启停状态的位掩码（bitmask）：每一位对应一个模块，bit 0 对应 module 0，bit 1 对应 module 1，依次类推；位值为 `1` 表示启用，为 `0` 表示停用。标准 11 模块触觉（如 `mt_*` / `mx_*`）全部启用时为 `0x07FF`；5 模块指尖触觉（如 `hp_*`）全部启用时为 `0x001F`；上述三种组合触觉均有 11 个公开模块，全部启用时为 `0x07FF`。

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

只修改一个模块时，优先使用 `module_enabled()` 和 `set_module_enabled()`，避免手动位运算覆盖其他模块的状态。`tare()` 不传参数时对全部支持的触觉模块执行校准零漂。

触觉配置和维护操作统一由 `hand.touch` 提供，不暴露 vendor 专属子对象或命令枚举：

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

这些方法按当前布局能力路由，不代表所有触觉型号都支持同一组操作。不支持的操作返回 `UnsupportedCapability`，不会发送设备命令。其中：

- `read_mode` / `set_read_mode`：适用于包含 `mt_*` 的布局。
- `value_mode` / `set_value_mode`：适用于包含 `mt_*` 或 `mx_*` 的布局，对外仅提供 `Adc` (0) 与 `Force` (2)。
- `tare`：按当前布局路由到支持的模组；`cancel_tare` 和 `tare_status` 仅在底层协议提供对应状态机时可用。
- `point_counts` / `restart`：当前仅包含 `mx_*` 的布局可用。传入 `module_index` 时使用公开 module ID。

`point_counts()` 当前依赖 `mx_*` 元数据寄存器；布局不包含 `mx_*` 时返回 `UnsupportedCapability`。C ABI 的 `revo3_device_touch_get_layout()` 在布局包含 `mx_*` 模组时主动刷新运行时点数，并通过 `CRevo3TouchLayout.modules[*].point_count` 返回；其他触觉模组直接返回已知布局点数。触觉模组序列号统一从 `hand.device_info.touch_serial_numbers` 或 C ABI 的 `CRevo3DeviceInfo.touch_serial_numbers` 读取；未提供序列号寄存器的协议返回空列表，不使用占位值。

触觉模组 SN 从 `hand.device_info.touch_serial_numbers` 读取。

### 4.4 Health 系统诊断与安全状态 API

Health 按职责分为：

- **系统健康快照**：`hand.health.snapshot()`，读取逐电机故障码、系统状态、电流、电压、功率、温度和安全状态。
- **电机诊断**：`motor_module_temperatures_c()`、`motor_online_mask()`，读取逐模组温度和在线状态。
- **故障处理**：`clear_motor_faults()`，清除设备当前可清除的电机故障。

`HealthSnapshot` 是只读诊断信息，包含系统状态、全局错误码、电流、电压、功率、系统温度、21 个电机的原始故障码、故障电机数量和 `safety_state`。逐电机故障码来自输入寄存器 2120..2140，与高频 `HandState` 分开采集。逐电机模组温度和在线 bitmask 属于健康诊断查询，通过 `hand.health.motor_module_temperatures_c()` 和 `hand.health.motor_online_mask()` 读取。这些值当前不重复内嵌到 `HealthSnapshot`。完整保护状态及其 `SafetyState` 映射仍需固件语义和真机异常测试确认。

`HealthSnapshot` 和 `SafetyState` 均为通过普通 Modbus RTU / CANFD 链路采集、聚合的软件级诊断，不是功能安全状态，不得直接作为 ISO 13849 PL、IEC 61508 SIL、安全 PLC、Emergency Stop（紧急停止）回路或 STO 的判定证据。有明确错误时，`SafetyState` 返回 `Faulted`；信息不足时返回 `Unknown`。Software Stop（软件停止）和 Servo 超时仅提供软件层级的控制降级，不具备硬件级功能安全承诺。现场安全保护必须由系统风险评估确定的独立安全链路承担。

```python
# 示例：读取系统只读健康诊断与安全置信度
health = await hand.health.snapshot()
print(f"Safety State: {health.safety_state}, Faulted Motors: {health.faulted_motor_count}")
print(f"Motor Fault Codes: {health.motor_fault_codes}")

temperatures = await hand.health.motor_module_temperatures_c()
online_mask = await hand.health.motor_online_mask()
motor_0_online = bool(online_mask & (1 << 0))
```

C++ 可通过 `hand.health().motor_module_diagnostics()` 一次读取逐电机模组温度数组和在线 bitmask。

### 4.5 ExperimentalCollision 实验性碰撞保护 API

碰撞检测保留为明确的实验性功能域，不属于 `Health`。Python 通过 `hand.experimental_collision`，C++ 通过 `hand.experimental_collision()`，C 通过 `revo3_experimental_collision_*` 使用。

该能力默认关闭，目前主要依赖 SDK 侧读取的位置误差、电流和缓存状态判断，并在命中阈值后执行软件停止、零力或保持当前反馈位置等策略。它不属于功能安全机制，不保证固定检测延迟，也不承诺无漏检或无误检；通信周期、缓存状态年龄、阈值和固件反馈及时性都会影响效果。不能用它替代急停、硬件限位或经过安全认证的控制器互锁。实验性 API 可能在后续 2.x minor 版本根据真机验证调整配置字段和判定语义。

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

#### CollisionDetectionSource (枚举)

| 枚举项 | 数值 | 描述说明 |
| --- | ---: | --- |
| `HardwareOnly` | `0` | 仅使用设备上报的硬件碰撞状态 |
| `SoftwareOnly` | `1` | 仅使用 SDK 侧位置误差和电流阈值判断 |
| `Hybrid` | `2` | 同时使用硬件状态和 SDK 侧阈值判断 |

#### CollisionProtectionStrategy (枚举)

| 枚举项 | 数值 | 描述说明 |
| --- | ---: | --- |
| `SoftStop` | `0` | 触发 SDK 软件停止 |
| `ZeroForce` | `1` | 下发零力控制命令 |
| `HoldActualPosition` | `2` | 以触发时的实际反馈位置作为保持目标 |

Python 和 C++ 调用方必须传入已定义的枚举成员。未知整数值属于 `InvalidArgument`，不得回退为默认检测源或保护策略。该输入合同不改变本节开头声明的实验性边界和非功能安全定位。

### 4.6 Config 配置 API

Config 按职责分为：

- **配置读取**：`hand.config.snapshot()`，读取设备配置快照。
- **SDK 运行参数**：`runtime_options`、`set_runtime_options(...)`，分别设置 State/Touch/Health 默认订阅间隔和 Servo 命令超时。
- **设备开关**：蜂鸣器、振动、触屏、广播 ID、上电自动标定和自动清除电机故障。
- **保护参数**：最大连续电流、全局保护电流、逐关节保护电流，以及位置/速度限制。

`Config` 管理设备配置快照和 SDK 运行参数。设备配置由固件持久化；运行参数只影响当前 SDK 进程。

- `hand.config.snapshot()` 返回 `DeviceConfig`，包含 `slave_id`、RS485 波特率、设备开关、保护电流、位置与速度限制以及 `persistence_scope`。`hand.config` 还提供逐项命名的 setter，不提供会同时覆盖无关字段的批量更新。固件是配置持久化的唯一事实来源。
- `hand.config.runtime_options` 返回 `RuntimeOptions`，包含 `state_subscription_period_ms`（默认 20）、`touch_subscription_period_ms`（默认 20）、`health_subscription_period_ms`（默认 1000）和 `servo_command_timeout_ms`（默认 100）。这些参数只更新当前进程，不写入设备。调用者也可以在创建订阅或流式控制会话时按场景指定参数；拉取间隔不是设备采样周期或固定频率承诺。
- 通信参数使用 `Rs485Baudrate` / `CanFdBaudrate` 枚举设置。C ABI 对应符号为 `revo3_device_set_rs485_baudrate()` / `revo3_device_set_canfd_baudrate()`。
- SDK 不提供 `SafetyConfig`。固件已有的限制不在 SDK 中重复定义。

```python
config = await hand.config.snapshot()
print(f"Slave ID: {config.slave_id}, Baudrate: {config.rs485_baudrate}")
runtime = hand.config.runtime_options
```

### 4.7 Calibration 标定 API

Calibration 按职责分为：

- **关节标定**：`calibrate_joints()`，执行关节标定流程。
- **标定电流**：`set_current(current_ma)`，设置标定过程使用的电流。
- **零位设置**：`set_current_position_as_zero()`，将当前反馈位置记录为零位。

`Calibration` 提供关节标定、标定电流和零位操作。标定前自动校验 Motion 空闲；固件没有进度或取消结果，响应丢失时不自动重发。

```python
await hand.calibration.calibrate_joints()  # 关节标定
await hand.calibration.set_current(120.0)
await hand.calibration.set_current_position_as_zero()
```

### 4.8 Maintenance 维护 API

Maintenance 按职责分为：

- **设备重启**：`reboot()`，返回可等待的 `OperationHandle`。
- **固件升级**：`update_firmware(file_path, target=None, wait_secs=10)`，执行控制器、电机或触觉目标的 OTA/DFU。
- **升级中止与恢复**：`abort_firmware_update()`、`reset_firmware_update_state()`。
- **恢复出厂**：`factory_reset()`，恢复设备出厂配置。

`Maintenance` 提供恢复出厂、重启和固件升级。`update_firmware(file_path, target=None, wait_secs=10)` 是唯一的对象层升级入口；当前内部通过设备 DFU/OTA 流程完成。重启与固件更新返回可查询的 `OperationHandle`。

```python
reboot_handle = hand.maintenance.reboot()  # 重启设备
ota_handle = hand.maintenance.update_firmware("revo3_controller.bin")
```

## 5. Public API Reference

本章列出 Python 与 C++ 对象层 public API。Python 中会发起 I/O 的方法通常返回 awaitable；表格中写 `await ...` 表示推荐调用方式。C++ 同名能力位于 `revo3` 命名空间。

### 5.1 Manager / Manager

| Python 写法 | C++ 写法 | 返回值 | 行为说明 |
| --- | --- | --- | --- |
| `sdk.Manager()` | `revo3::Manager manager;` | manager | 创建设备管理器 |
| `manager.list_ports()` | - | `list[SerialPortInfo]` | 列出本机端口/适配器，不访问设备 |
| `await manager.discover(...)` | `manager.discover(options)` | `list[DetectedDevice]` | 扫描设备 |
| `await manager.connect_auto(...)` | `manager.connect_auto(options)` | `Hand` | 自动扫描并连接首个设备 |
| `await manager.connect(detected, model=None)` | `manager.connect(detected)` | `Hand` | 连接扫描阶段选择的设备 |
| `await manager.connect_all(devices)` | `manager.connect_all(devices)` | `list[Hand]` / `std::vector<Hand>` | 批量连接 |
| `await manager.close()` | `manager.close()` | `None` | 关闭管理器和其持有连接 |

Python 返回标准 `list[Hand]`，支持迭代、切片和按零基索引访问；按序列号选择设备时，应用可根据 `hand.device_info.serial_number` 过滤列表。C++ 的批量连接结果使用 `std::vector<Hand>`。

Python `SerialPortInfo` 提供以下只读字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `port_name` | `str` | 操作系统端口名 |
| `manufacturer` | `str \| None` | USB 厂商字符串（系统未提供时为 `None`） |
| `product_name` | `str \| None` | USB 产品字符串（系统未提供时为 `None`） |
| `serial_number` | `str \| None` | 适配器序列号（系统未提供时为 `None`） |
| `vid` / `pid` | `int \| None` | USB VID/PID（非 USB 端口或系统未提供时为 `None`） |

#### discover(...) 流式回调 (Streaming Callback)

- **Python 签名**: `await manager.discover(scan_all=False, port=None, protocol=None, slave_id=None, modbus_baudrate=None, canfd_data_baudrate=None, broadcast=True, on_found=None)`
  - `on_found`: 可选回调 `Callable[[DetectedDevice], bool | None]`。每发现一台设备时触发，返回 `False` 可提前终止扫描。
- **C++ 签名**: `std::vector<DetectedDevice> manager.discover(const DiscoveryOptions &options)`
  - `DiscoveryOptions.on_found`: 可选回调 `std::function<bool(const DetectedDevice &device)>`。返回 `false` 可提前终止扫描。

回调抛出异常时，扫描会停止，并在扫描线程完成清理后把原异常重新抛给 `discover()` 调用者；不会返回静默截断的设备列表，也不会让 C++ 异常穿过 C ABI。

### 5.2 Hand 与元数据

`Hand` 对象能力树：

```text
Hand
├── motion
├── state
├── touch
├── health
├── experimental_collision
├── config
├── calibration
├── maintenance
└── statistics
```

Hand 本体还提供 `device_info`、`firmware_info`、`joint_layout`、`slave_id` 属性，以及 `refresh_device_info()`、`refresh_firmware_info()` 和 `close()` 生命周期方法。

| Python 写法 | C++ 写法 | 返回值 | 行为说明 |
| --- | --- | --- | --- |
| `hand.device_info` | `hand.device_info()` | [`DeviceInfo`](#deviceinfo) / `None` | 设备和部件物理身份 |
| `hand.firmware_info` | `hand.firmware_info()` | [`FirmwareInfo`](#firmwareinfo) | 主控、电机、触觉固件版本 |
| `hand.joint_layout` | `hand.joint_layout()` | [`JointLayout`](#jointlayout) / `None` | 关节数量和布局 |
| `await hand.refresh_device_info()` | `hand.refresh_device_info()` | [`DeviceInfo`](#deviceinfo) | 重新读取设备身份 |
| `await hand.refresh_firmware_info()` | `hand.refresh_firmware_info()` | [`FirmwareInfo`](#firmwareinfo) | 重新读取固件版本 |
| `hand.motion` | `hand.motion()` | [`Motion`](#53-motion-与-servosession) | 运动控制域 |
| `hand.state` | `hand.state()` | [`State`](#54-statetouch-与-health) | 电机反馈域 |
| `hand.touch` | `hand.touch()` | [`Touch`](#54-statetouch-与-health) | 触觉域 |
| `hand.health` | `hand.health()` | [`Health`](#54-statetouch-与-health) | 健康诊断域 |
| `hand.experimental_collision` | `hand.experimental_collision()` | [`ExperimentalCollision`](#55-experimentalcollision-实验性碰撞保护) | 实验性软件碰撞检测与响应 |
| `hand.config` | `hand.config()` | [`Config`](#56-touchconfigcalibration-与-maintenance) | 配置域 |
| `hand.calibration` | `hand.calibration()` | [`Calibration`](#56-touchconfigcalibration-与-maintenance) | 标定域 |
| `hand.maintenance` | `hand.maintenance()` | [`Maintenance`](#56-touchconfigcalibration-与-maintenance) | 维护域 |
| `hand.statistics` | `hand.statistics()` | [`RuntimeStatistics`](#runtimestatistics) | 运行读写和失败计数 |
| `await hand.close()` | `hand.close()` | `None` | 关闭当前手句柄 |

### 5.3 Motion 与 ServoSession

除目标运动、Servo、拖拽和示教回放外，Motion 还提供 `set_zero_force_enabled()`、`software_stop()` 和 `recover_software_stop()`。目标运动返回 `OperationHandle`，可通过 `id`、`state`、`error`、`wait(timeout)` 和 `cancel()` 管理。

| Python 写法 | C++ 写法 | 返回值 | 行为说明 |
| --- | --- | --- | --- |
| `await hand.motion.move_to(...)` | `hand.motion().move_to(...)` | [`OperationHandle`](#7-等待取消和运动冲突) | 整手目标运动 |
| `await hand.motion.move_joint(...)` | `hand.motion().move_joint(...)` | [`OperationHandle`](#7-等待取消和运动冲突) | 单关节目标运动 |
| `await hand.motion.move_finger(...)` | `hand.motion().move_finger(...)` | [`OperationHandle`](#7-等待取消和运动冲突) | 手指全姿态运动，包含 Abd |
| `await hand.motion.flex_finger(...)` | `hand.motion().flex_finger(...)` | [`OperationHandle`](#7-等待取消和运动冲突) | 手指语义弯曲，Abd 保持当前值 |
| `await hand.motion.move_thumb(...)` | `hand.motion().move_thumb(...)` | [`OperationHandle`](#7-等待取消和运动冲突) | 拇指目标运动 |
| `hand.motion.open_servo(...)` | `hand.motion().open_servo(...)` | [`ServoSession`](#servosessionstate-枚举) | 同步创建实时流控会话；后续 `send_*()` 为异步 I/O |
| `await session.send_position(...)` | `session.send_position(...)` | `None` | 发送位置流控帧 |
| `await session.send_velocity(...)` | `session.send_velocity(...)` | `None` | 发送速度流控帧 |
| `await session.send_current(...)` | `session.send_current(...)` | `None` | 发送电流流控帧 |
| `await session.send_impedance(...)` | `session.send_impedance(...)` | `None` | 发送阻抗流控帧 |
| `await session.send_mit(...)` | `session.send_mit(...)` | `None` | 发送 MIT 流控帧 |
| `session.state` | `session.state()` | [`ServoSessionState`](#servosessionstate-枚举) | 读取会话状态 |
| `session.close()` | `session.close()` | `None` | 关闭流控会话 |
| `await hand.motion.start_servo_drag(...)` | `hand.motion().start_servo_drag(...)` | `None` | 启动托管拖拽 |
| `hand.motion.update_servo_drag(...)` | `hand.motion().update_servo_drag(...)` | `None` | 更新拖拽目标 |
| `await hand.motion.stop_servo_drag(...)` | `hand.motion().stop_servo_drag(...)` | `None` | 正常停止拖拽 |
| `await hand.motion.cancel_servo_drag(...)` | `hand.motion().cancel_servo_drag(...)` | `None` | 取消拖拽发包 |
| `await hand.motion.teach_joint(...)` | `hand.motion().teach_joint(...)` | `list[float]` | 记录单关节轨迹 |
| `await hand.motion.teach_hand(...)` | `hand.motion().teach_hand(...)` | `list[list[float]]` | 记录整手轨迹 |
| `await hand.motion.replay_joint(...)` | `hand.motion().replay_joint(...)` | `None` | 回放单关节轨迹 |
| `await hand.motion.replay_hand(...)` | `hand.motion().replay_hand(...)` | `None` | 回放整手轨迹 |
| `await hand.motion.set_zero_force_enabled(enabled)` | `hand.motion().set_zero_force_enabled(enabled)` | `None` | 零力矩/示教模式开关 |
| `await hand.motion.software_stop()` | `hand.motion().software_stop()` | `None` | 发送软件停止指令并等待本次设备 I/O 完成 |
| `await hand.motion.recover_software_stop()` | `hand.motion().recover_software_stop()` | `None` | 发送软件停止恢复指令并等待本次设备 I/O 完成 |

### 5.4 State、Touch 与 Health

`StateSubscription`、`TouchSubscription` 和 `HealthSubscription` 都使用同一生命周期约定：调用 `next()` 拉取下一帧，调用 `close()` 取消订阅并释放后台拉取任务。`period` 是 SDK 拉取间隔，不是固件采样频率承诺。

| Python 写法 | C++ 写法 | 返回值 | 行为说明 |
| --- | --- | --- | --- |
| `await hand.state.snapshot()` | `hand.state().snapshot()` | [`HandState`](#handstate) | 读取电机反馈快照 |
| `hand.state.subscribe(period)` | `hand.state().subscribe(period)` | [`StateSubscription`](#statesubscription-touchsubscription-healthsubscription) | 创建状态拉取订阅 |
| `await sub.next()` | `sub.next()` | [`HandState`](#handstate) | 读取下一帧状态 |
| `hand.touch.layout` | `hand.touch().layout()` | [`TouchLayout`](#touchlayout) `| None` / [`TouchLayout`](#touchlayout) | 读取触觉区域分组和 module 布局；C++ 在不可用时抛出异常 |
| `await hand.touch.set_layout(layout)` | `hand.touch().set_layout(layout)`；C ABI：`revo3_device_touch_set_layout(...)` | `None` | 为当前连接会话设置经确认的完整触觉布局；不写设备寄存器，未知或不完整布局失败 |
| `await hand.touch.snapshot()` | `hand.touch().snapshot()` | [`TouchFrame`](#touchframe) | 读取触觉快照 |
| `await hand.touch.snapshot(module_indices=[...])` | `hand.touch().snapshot({...})` | [`TouchFrame`](#touchframe) | 按请求顺序读取指定模块；C ABI：`revo3_device_touch_get_snapshot_modules(...)` |
| `await hand.touch.module_snapshot(i)` | `hand.touch().module_snapshot(i)` | [`TouchModuleData`](#touchmoduledata) | 读取单个模块 |
| `hand.touch.subscribe(period)` | `hand.touch().subscribe(period)` | [`TouchSubscription`](#statesubscription-touchsubscription-healthsubscription) | 创建触觉订阅 |
| `await hand.touch.enabled_mask()` | `hand.touch().enabled_mask()` | `int` | 读取触觉使能 bitmask |
| `await hand.touch.set_enabled_mask(mask)` | `hand.touch().set_enabled_mask(mask)` | `None` | 设置触觉使能 bitmask |
| `await hand.touch.module_enabled(i)` | `hand.touch().module_enabled(i)` | `bool` | 读取单模块使能 |
| `await hand.touch.set_module_enabled(i, enabled)` | `hand.touch().set_module_enabled(i, enabled)` | `None` | 设置单模块使能 |
| `await hand.touch.tare(module_index=None)` | `hand.touch().tare()` / `hand.touch().tare(module_index)` | `None` | 通用触觉零漂校准入口；不传 `module_index` 时表示全部清零，传入时表示单模块清零（自动按当前代码路由到 `mt_*` / `mx_*` / `hp_*` 模组） |
| `await hand.health.snapshot()` | `hand.health().snapshot()` | [`HealthSnapshot`](#healthsnapshot) | 系统健康快照 |
| `await hand.health.motor_module_temperatures_c()` | `hand.health().motor_module_diagnostics()` | `list[float]` / [`MotorModuleDiagnostics`](#motormodulediagnostics) | 逐电机模组温度 |
| `await hand.health.motor_online_mask()` | `hand.health().motor_module_diagnostics()` | `int` / [`MotorModuleDiagnostics`](#motormodulediagnostics) | 电机在线 bitmask |
| `await hand.health.clear_motor_faults()` | `hand.health().clear_motor_faults()` | `None` | 清除电机故障 |

### 5.5 ExperimentalCollision 实验性碰撞保护

| Python 写法 | C++ 写法 | C 写法 | 返回值 | 行为说明 |
| --- | --- | --- | --- | --- |
| `await hand.experimental_collision.configure(config)` | `hand.experimental_collision().configure(config)` | `revo3_experimental_collision_configure(...)` | `None` | 配置或关闭实验性软件碰撞检测；默认关闭 |
| `await hand.experimental_collision.active_joints()` | `hand.experimental_collision().active_joints()` | `revo3_experimental_collision_get_active(...)` | 21 个 `bool` | 查询当前锁存的碰撞关节状态 |
| `await hand.experimental_collision.reset()` | `hand.experimental_collision().reset()` | `revo3_experimental_collision_reset(...)` | `None` | 重置锁存状态 |

`ExperimentalCollisionConfig` / `revo3::ExperimentalCollisionConfig` / `CRevo3ExperimentalCollisionConfig` 包含开关、检测来源、位置误差阈值、电流阈值、去抖时间、可复用状态最大年龄、响应策略和自动清除时间。其风险边界见 [4.5](#45-experimentalcollision-实验性碰撞保护-api)。

Python 配置字段和构造默认值如下；字段均可在调用 `configure()` 前修改：

| 字段 | 默认值 | 单位或语义 |
| --- | --- | --- |
| `enable` | `False` | 总开关 |
| `source` | `HardwareOnly` | 检测来源 |
| `position_error_threshold_deg` | `15.0` | degree |
| `current_threshold_ma` | `800.0` | mA |
| `debounce_time_ms` | `100` | ms |
| `max_cached_status_age_ms` | `50` | ms |
| `strategy` | `SoftStop` | 保护策略 |
| `auto_clear_time_ms` | `1000` | ms |

### 5.6 Touch、Config、Calibration 与 Maintenance

`Touch` 统一承载触觉读取、配置和维护操作。具体能力由当前 `TouchLayout` 与设备协议决定；不支持的操作返回 `UnsupportedCapability`。

Config、Calibration 和 Maintenance 也按以下职责归类：

- **Config 通信参数**：`set_rs485_baudrate()`、`set_canfd_baudrate()`。
- **Config 位置/速度限制**：`set_joint_position_limits()`、`set_joint_speed_limits()`。
- **Calibration 零位与默认参数**：`zero_positions()`、`set_zero_positions()`、`reset_finger_defaults()`。
- **Maintenance 升级生命周期**：`abort_firmware_update()`、`reset_firmware_update_state()`；`reboot()` 和 `update_firmware()` 返回 `OperationHandle`，其他维护操作返回 awaitable。

Touch API 按职责分为：读取与订阅、布局配置、模组启停、读取模式、数值模式、零点与力校准、模组信息与维护。下表保留跨语言签名对照，详细语义按上述职责阅读。

#### 读取与订阅

- `hand.touch.layout`：读取当前 `TouchLayout`。
- `await hand.touch.snapshot()`：读取单帧 `TouchFrame`。
- `await hand.touch.snapshot(module_indices=[...])`：只读取指定模块，并按传入的 module ID 顺序返回。
- `await hand.touch.module_snapshot(module_index)`：读取并直接返回单个 `TouchModuleData`。
- `hand.touch.subscribe(period)`：创建 `TouchSubscription`，通过 `next()` 拉取下一帧，通过 `close()` 取消。

#### 布局配置

- `await hand.touch.set_layout(layout)`：为当前连接会话设置经确认的完整布局；不写设备寄存器，仅更新 SDK 解析路由。
- 支持 Revo3 Ultra Touch 的完整集成布局，以及 Ultra VisionTouch 的主链路指腹/手掌布局；未知、不完整或包含独立视触觉指尖的 Ultra VisionTouch 布局在发送设备请求前失败。

#### 模组启停

- `set_module_enabled(module_index, enabled)` / `module_enabled(module_index)`：操作单个逻辑模组。
- `set_enabled_mask(enabled_mask)` / `enabled_mask()`：操作或读取逻辑模组 bitmask。
- `module_index` 取值为公开 `module_id`：纯 `mt_*` / `mx_*` 布局下等于 `TouchLayout.modules` 的数组下标（0~10 密集编号）；组合拓扑下为稀疏编号，与数组下标不再一致。

#### 读取模式

- `set_read_mode(mode)` / `read_mode()`：切换或读取 `mt_*` 的 `PointArray` / `LegacyForceSummary` 模式。
- `LegacyForceSummary` 仅兼容少量已发货设备，后续将删除；该模式下点阵字段为 `None`，二次标定区域合力写入 `regional_forces_mn`。新应用不应形成依赖。

#### 数值模式

- `set_value_mode(mode, module_index=None)` / `value_mode(module_index=None)`：读取或设置 `mt_*` / `mx_*` 的 ADC 或压力值模式。
- 公开枚举仅包含 `Adc` (0) 与 `Force` (2)；`mt_*` 寄存器值 `1` 未使用，不接受该输入。

#### 零点校准

- `tare(module_index=None)`：统一零漂校准入口，支持 `mt_*`、`mx_*`、`hp_*`。
- `cancel_tare(module_index=None)`：仅 `mx_*` 支持，写入取消命令以恢复默认/出厂零点基线；它不表示必须存在一个正在进行的异步流程。
- `tare_status(module_index=None)`：仅 `mx_*` 支持，读取协议定义的清零状态；`hp_*` 没有对应状态寄存器。

#### 模组信息与维护

- `point_counts()`：读取 `mx_*` 运行时点数。
- `restart(module_index=None)`：重启 `mx_*` 模组。
- `hand.device_info.touch_serial_numbers`：读取已发现的触觉模组序列号；C ABI 从 `CRevo3DeviceInfo.touch_serial_numbers` 读取。

| Python 写法 | C++ 写法 | 返回值 | 行为说明 |
| --- | --- | --- | --- |
| `await hand.touch.read_mode()` | `hand.touch().read_mode()` | [`TouchReadMode`](#touchreadmode-枚举) / `TouchReadMode` | 读取触觉数据布局模式 |
| `await hand.touch.set_read_mode(mode)` | `hand.touch().set_read_mode(mode)` | `None` | 设置触觉数据布局模式 |
| `await hand.touch.value_mode(module_index=None)` | `hand.touch().value_mode(module_index)` | [`TouchValueMode`](#touchvaluemode-枚举) / `TouchValueMode` | 读取触觉值模式 |
| `await hand.touch.set_value_mode(mode, module_index=None)` | `hand.touch().set_value_mode(mode, module_index)` | `None` | 设置触觉值模式 |
| `await hand.touch.tare(module_index=None)` | `hand.touch().tare(module_index)` | `None` | 执行零漂校准 |
| `await hand.touch.cancel_tare(module_index=None)` | `hand.touch().cancel_tare(module_index)` | `None` | `mx_*` 恢复默认/出厂零点基线 |
| `await hand.touch.tare_status(module_index=None)` | `hand.touch().tare_status(module_index)` | `TouchTareStatus` | `mx_*` 查询协议定义的清零状态 |
| `await hand.touch.point_counts()` | `hand.touch().point_counts()` | `list[int]` / `std::vector<uint16_t>` | 读取触觉模组点数 |
| `await hand.touch.restart(module_index=None)` | `hand.touch().restart(module_index)` | `None` | 重启触觉模组 |

Touch 操作按当前协议能力路由；不支持的组合在发送请求前返回 `UnsupportedCapability`：

| 操作 | `mt_*` | `mx_*` | `hp_*` |
| --- | :---: | :---: | :---: |
| `snapshot()` | 支持 | 支持 | 支持 |
| `set_read_mode()` / `read_mode()` | 支持 | 不支持 | 不支持 |
| `set_value_mode()` / `value_mode()` | 支持 | 支持 | 不支持 |
| `tare()` | 支持 | 支持 | 支持 |
| `cancel_tare()` / `tare_status()` | 不支持 | 支持 | 不支持（协议未提供对应寄存器） |
| `point_counts()` / `restart()` | 不支持 | 支持 | 不支持 |

C ABI 对应的 Touch 符号为：

```c
revo3_device_touch_get_layout
revo3_device_touch_set_layout
revo3_device_touch_get_snapshot
revo3_device_touch_get_snapshot_modules
revo3_device_touch_set_module_enabled
revo3_device_touch_get_module_enabled
revo3_device_touch_set_enabled_mask
revo3_device_touch_get_enabled_mask
revo3_device_touch_set_read_mode
revo3_device_touch_get_read_mode
revo3_device_touch_set_value_mode
revo3_device_touch_get_value_mode
revo3_device_touch_tare
revo3_device_touch_cancel_tare
revo3_device_touch_get_tare_status
revo3_device_touch_restart
```

C ABI 的 `module_index` 使用负数表示全部模组；非负值表示公开 module ID（纯 `mt_*` / `mx_*` 布局下等于 `TouchLayout.modules` 数组下标；组合拓扑下为与协议物理编号对齐的稀疏编号，不等于数组下标）。

#### Config、Calibration 与 Maintenance

| Python 写法 | C++ 写法 | 返回值 | 行为说明 |
| --- | --- | --- | --- |
| `await hand.config.snapshot()` | `hand.config().snapshot()` | [`DeviceConfig`](#deviceconfig) | 读取设备配置 |
| `hand.config.runtime_options` | `hand.config().runtime_options()` | [`RuntimeOptions`](#runtimeoptions) | 读取 SDK 运行参数 |
| `hand.config.set_runtime_options(options)` | `hand.config().set_runtime_options(options)` | `None` | 设置 SDK 运行参数 |
| `await hand.config.set_buzzer(enabled)` | `hand.config().set_buzzer(enabled)` | `None` | 设置蜂鸣器 |
| `await hand.config.set_vibration(enabled)` | `hand.config().set_vibration(enabled)` | `None` | 设置振动 |
| `await hand.config.set_touch_screen(enabled)` | `hand.config().set_touch_screen(enabled)` | `None` | 设置触屏 |
| `await hand.config.set_use_broadcast_id(enabled)` | `hand.config().set_use_broadcast_id(enabled)` | `None` | 设置广播 ID 使用 |
| `await hand.config.set_power_on_auto_calibration(enabled)` | `hand.config().set_power_on_auto_calibration(enabled)` | `None` | 设置上电自动标定开关 |
| `await hand.config.set_auto_clear_motor_faults(enabled)` | `hand.config().set_auto_clear_motor_faults(enabled)` | `None` | 设置自动清除电机故障 |
| `await hand.config.set_max_continuous_current(ma)` | `hand.config().set_max_continuous_current(ma)` | `None` | 设置最大连续电流 |
| `await hand.config.set_global_protect_current(ma)` | `hand.config().set_global_protect_current(ma)` | `None` | 设置全局保护电流 |
| `await hand.config.set_joint_protect_current(i, ma)` | `hand.config().set_joint_protect_current(i, ma)` | `None` | 设置单关节保护电流 |
| `await hand.config.set_joint_position_limits(i, min, max)` | `hand.config().set_joint_position_limits(i, min, max)` | `None` | 设置单关节位置限制 |
| `await hand.config.set_joint_speed_limits(i, min, max)` | `hand.config().set_joint_speed_limits(i, min, max)` | `None` | 设置单关节速度限制 |
| `await hand.config.set_rs485_baudrate(baudrate)` | `hand.config().set_rs485_baudrate(baudrate)` | `None` / `void` | 设置 RS485 波特率 |
| `await hand.config.set_canfd_baudrate(baudrate)` | `hand.config().set_canfd_baudrate(baudrate)` | `None` / `void` | 设置 CANFD 波特率 |
| `await hand.calibration.calibrate_joints()` | `hand.calibration().calibrate_joints()` | `None` | 关节标定 |
| `await hand.calibration.set_current(ma)` | `hand.calibration().set_current(ma)` | `None` | 设置标定电流 |
| `await hand.calibration.zero_positions()` | `hand.calibration().zero_positions()` | `list[float]` | 读取零位 |
| `await hand.calibration.set_zero_positions(values)` | `hand.calibration().set_zero_positions(values)` | `None` | 设置零位 |
| `await hand.calibration.set_current_position_as_zero()` | `hand.calibration().set_current_position_as_zero()` | `None` | 当前姿态设为零位 |
| `await hand.calibration.reset_finger_defaults()` | `hand.calibration().reset_finger_defaults()` | `None` | 恢复手指默认参数 |
| `hand.maintenance.reboot()` | `hand.maintenance().reboot()` | [`OperationHandle`](#7-等待取消和运动冲突) | 重启设备 |
| `hand.maintenance.update_firmware(path, target=None, wait_secs=10)` | `hand.maintenance().update_firmware(path, target)` | [`OperationHandle`](#7-等待取消和运动冲突) | 固件升级 |
| `await hand.maintenance.factory_reset()` | `hand.maintenance().factory_reset()` | `None` | 恢复出厂 |
| `await hand.maintenance.abort_firmware_update()` | `hand.maintenance().abort_firmware_update()` | `None` | 中止固件升级 |
| `await hand.maintenance.reset_firmware_update_state()` | `hand.maintenance().reset_firmware_update_state()` | `None` | 重置升级状态 |

## 6. 数据结构与类型参考 (Data Structures & Types)

本章详述 SDK 2.0 返回的核心数据结构、状态枚举及详细属性字段说明。

### 6.1 诊断与健康数据结构 (Health & Diagnostics)

#### HealthSnapshot
包含系统主控板只读健康诊断与安全状态信息：

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `system_state` | `int` | 系统全局状态 (`0=Normal`, `1=Fault`) |
| `error_code` | `int` | 系统全局错误码 (`0=Normal`, `1=CommError`, `2=NoCalibration`, `3=TempAbnormal`) |
| `current_ma` | `int` | 系统总电流 (mA) |
| `voltage_v` | `int` | 系统母线电压 (V) |
| `power_w` | `int` | 系统总功率 (W) |
| `temperature_c` | `int` | 主控芯片/板级温度 (°C) |
| `motor_fault_codes` | `list[int]` / `std::array<int, 21>` | 21 个电机的原始故障码，来自输入寄存器 2120..2140 |
| `faulted_motor_count` | `int` | 当前存在故障码的电机总数 |
| `safety_state` | [`SafetyState`](#safetystate-枚举) | 系统安全诊断状态 (`Normal` / `RecoveryRequired` / `Faulted` / `Unknown`) |
| `observed_at` | [`Timestamp`](#timestamp) | 观察与采样时刻时间戳 |

#### RuntimeStatistics
包含 SDK 传输层运行与通信质量统计信息：

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `state_reads` | `int` | 电机状态反馈读取成功帧数 |
| `touch_reads` | `int` | 触觉传感帧读取成功次数 |
| `commands_sent` | `int` | 下发的写命令总数 |
| `failed_operations` | `int` | 操作失败与通信异常总次数 |
| `servo_command_timeouts` | `int` | 实时流控心跳超时断开次数 |
| `servo_commands` | `int` | 实时伺服控制帧成功下发累计数 |
| `state_read_fps` | `float` | 电机状态反馈读取频率，单位为帧/秒；按设备生命周期累计平均值计算 |
| `servo_command_fps` | `float` | 实时伺服控制帧下发频率，单位为帧/秒；按设备生命周期累计平均值计算 |
| `touch_read_fps` | `float` | 触觉传感帧读取频率，单位为帧/秒；按设备生命周期累计平均值计算 |

#### MotorModuleDiagnostics
包含 21 电机驱动层诊断详细信息：

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `temperatures_c` | `list[float]` / `std::array<float, 21>` | 21 个电机的实时摄氏温度 (°C) |
| `online_mask` | `int` / `uint32_t` | 21-bit 电机在线掩码 (Bit 0~20 分别代表电机 0~20 的在线状态) |
| `serial_numbers` | `list[str]` / `std::vector<std::string>` | 21 个电机的出厂序列号 |

#### SafetyState (枚举)
- `Operational (0)`: 系统运行正常，元数据与诊断信息可靠。
- `RecoveryRequired (1)`: 存在可恢复错误，需要进行重启或故障恢复。
- `Faulted (2)`: 严重故障状态，停止下发运动命令。
- `Unknown (3)`: 状态未知。

### 6.2 实时流控会话与数据订阅 (ServoSession & Subscriptions)

#### HandState
整手 21 个电机的实时状态与反馈数据快照：

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `operating_states` | `list[int]` / `std::array<int, 21>` | 21 个电机的原始运行状态 bitmask，来自输入寄存器 2000..2020 |
| `positions_deg` | `list[float]` / `std::array<float, 21>` | 21 个电机的实时位置 (deg) |
| `velocities_rpm` | `list[float]` / `std::array<float, 21>` | 21 个电机的实时速度 (rpm) |
| `currents_ma` | `list[float]` / `std::array<float, 21>` | 21 个电机的实时电流 (mA) |
| `timestamp` | [`Timestamp`](#timestamp) | 数据帧接收时刻时间戳 |
| `positions_rad` (Python) | `list[float]` | 21 个电机的实时位置 (rad)，按 ROS REP 103 标准转换的只读属性 |
| `velocities_rad_s` (Python) | `list[float]` | 21 个电机的实时速度 (rad/s)，按 ROS REP 103 标准转换的只读属性 |
| `currents_a` (Python) | `list[float]` | 21 个电机的实时电流 (A)，国际单位制只读属性 |

SDK 当前不公开 `MotorOperatingState` 或 `MotorFaultCode` 枚举。`HandState.operating_states` 与 `HealthSnapshot.motor_fault_codes` 均保留固件原始整数语义，来自相互独立的寄存器数据源；应用不得在两者之间推导、回填或替代。在 Python 中，`HandState` 额外提供只读属性 `positions_rad`、`velocities_rad_s` 与 `currents_a`，方便 ROS 开发者直接接入 `sensor_msgs/JointState`。

#### ServoSessionState (枚举)
- `Active (0)`: 实时流控会话处于活动中，允许持续下发高频控制帧（如位置/速度/MIT）。
- `Expired (1)`: 控制心跳超时（默认 >100ms 无新帧下发），流控已自动失效。
- `Closed (2)`: 会话已被显式调用 `close()` 关闭，或相关资源已被回收。

`ServoSession.state` 仅用于观测、诊断和区分超时失效与显式关闭。状态可能在读取后立即变化，应用不得将“先判断 `Active`、再发送命令”视为并发安全保证；每次发送仍以该调用的成功结果或结构化错误为准。`Expired` 和 `Closed` 均为终止状态，必须重新打开 Servo 会话才能继续发送。

#### ServoFilterMode (枚举)

| 枚举项 | 数值 | 描述说明 |
| --- | ---: | --- |
| `Disabled` | `0` | 不启用平滑滤波，目标值直接进入拖拽控制循环 |
| `FirstOrderLpf` | `1` | 使用一阶低通滤波平滑目标位置 |
| `SecondOrderCriticallyDamped` | `2` | 使用二阶临界阻尼滤波平滑目标位置 |

#### StateSubscription / TouchSubscription / HealthSubscription
数据订阅流对象，用于按周期拉取采样：

| 方法 | 返回值 | 描述说明 |
| --- | --- | --- |
| `await sub.next()` / `sub.next()` | [`HandState`](#handstate) / [`TouchFrame`](#touchframe) / [`HealthSnapshot`](#healthsnapshot) | 异步/阻塞等待并读取下一帧订阅数据 |
| `sub.close()` | `None` | 显式关闭并释放订阅句柄 |

`close()` 可从另一线程或任务调用，并会唤醒正在等待下一个采样周期的 `next()`。为保证协议事务完整性，已经进入底层设备 I/O 的单次读取不会被强制中断；关闭状态会阻止后续读取。

`next()` 返回一次 SDK 拉取获得的快照；订阅对象不是固件逐帧队列，不保存两次调用之间产生的全部物理采样，也不承诺无丢帧。`period` 是 SDK 的最小拉取间隔，不是设备采样周期、固定频率或端到端交付保证。当前公共 API 不提供 DataCollector、共享 Buffer 或连续帧流；需要逐帧记录的场景必须经过单独的能力与契约评审。

### 6.3 触觉传感器数据结构 (Touch)

#### TouchLayout
触觉传感器阵列与区域布局定义，用于描述设备接入的触觉硬件拓扑（包括纯 `mt_*`、`mx_*`、`hp_*`，`hp_* + mt_*`、`hp_* + mx_*`、`hp_* + mx_* + mt_*` 组合拓扑，以及 Ultra VisionTouch 上自动探测到的稀疏 `mt_*`/`mx_*` 指腹与手掌布局）：

应用通过 `TouchLayout` 动态识别当前手爪的触觉分布，以 `regions` 获取解剖学区域分组（手掌/指尖/指腹），以 `modules` 获取各模块的 `layout_id`、`point_count` 及 `signals` 数据形态。`LegacyForceSummary` 兼容模式的二次标定区域合力直接从对应 `TouchModuleData.regional_forces_mn` 读取。

> [!NOTE]
> Ultra VisionTouch 的独立视触觉指尖采用专用数据链路，不并入主链路 `TouchLayout` 与 `TouchFrame`。同一设备上自动探测到的 `mt_*`/`mx_*` 指腹和手掌属于主链路，可以出现在上述结构中。

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `regions` | list[[`TouchRegionLayout`](#touchregionlayout)] | 按区域分组的触觉模块布局 |
| `modules` | list[[`TouchModuleLayout`](#touchmodulelayout)] | 触觉模块分布列表 |

#### TouchRegionLayout
按解剖学区域分组的触觉拓扑：

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `region` | [`TouchRegion`](#touchregion-枚举) | 触觉区域枚举 |
| `module_ids` | `list[int]` | 属于该区域的稳定模组 ID 列表 |

#### TouchModuleLayout
单个触觉模组的拓扑与通道定义：

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `module_id` | `int` | 稳定模组 ID (0~10) |
| `region` | [`TouchRegion`](#touchregion-枚举) | 触觉区域枚举 |
| `region_index` | `int` | 区域内部序号 |
| `layout_id` | `str` | 触觉阵列拓扑布局 ID（如 `mt_palm_36`, `hp_fingertip_48`, `hp_fingertip_ft`） |
| `point_count` | `int` | 触觉点阵总点数 |
| `signals` | list[[`TouchSignal`](#touchsignal-枚举)] | 该模组支持的触觉信号形态列表 |

#### TouchFrame
单帧触觉传感数据快照：

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `sequence` | `int` | 数据帧序号 |
| `timestamp` | [`Timestamp`](#timestamp) | 数据包接收时间戳 |
| `modules` | list[[`TouchModuleData`](#touchmoduledata)] | 逐模组触觉传感数据列表 |

`TouchFrame` 不使用单一 mode 概括整帧，因为组合拓扑的一帧可以同时包含点阵、模块级 summary 和力/力矩数据。应用应检查各 module 的 `sample_state`、`points`、`regional_forces_mn`、`force3d`、`torque2d` 和 `resultant_force_mn`。设备读取配置由独立的 `TouchReadMode` 表示。

#### TouchModuleData
单个触觉模块的多通道传感器数据：

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `region` | [`TouchRegion`](#touchregion-枚举) | 触觉区域 |
| `region_index` | `int` | 区域内序号 |
| `module_id` | `int` | 稳定模组 ID |
| `layout_id` | `str` | 触觉阵列拓扑布局 ID（使用统一短码，如 `mt_*` / `mx_*` / `hp_*`，用于 GUI 热力图渲染与仿真建模） |
| `sample_state` | [`TouchSampleState`](#touchsamplestate-枚举) | 当前模块在本帧中的采样状态 |
| `points` | `list[int] \| None` | 点阵数据；模块未采样、禁用或当前模式不返回点阵时为 `None` |
| `regional_forces_mn` | `list[int] \| None` | `mt_*` 的 `LegacyForceSummary` 兼容模式下，该模组对应的一个或多个二次标定区域合力值，单位 mN；其他模式为 `None` |
| `force3d` | [`TouchForce3D`](#touchforce3d-touchtorque2d) \| None | `hp_*` 模组局部坐标系的 `Fx/Fy/Fz`，单位 mN |
| `torque2d` | [`TouchTorque2D`](#touchforce3d-touchtorque2d) \| None | `hp_*` 模组绕局部 X/Y 轴的 `Mx/My`，单位 Nm |
| `resultant_force_mn` | `float \| None` | `hp_*` 模组触觉区域的标量合力 `Fn`，单位 mN；不是 `Fz` |
| `diagnostics` | [`TouchModuleDiagnostics`](#touchmodulediagnostics) \| None | 可选的协议级原始诊断值；仅用于故障排查，不作为业务状态判断依据 |

#### TouchModuleDiagnostics

`TouchModuleDiagnostics` 保留设备上报的原始状态，供日志记录和协议故障排查使用。应用应使用 `TouchModuleData.sample_state` 判断数据是否有效。

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `module_status_raw` | `int` | 模组原始状态：`0` 表示预热中，`1` 表示已就绪，`2` 或未知值表示不可用 |
| `sensor_fault_code_raw` | `int` | 传感器原始故障码：`0` 表示正常，非零值表示异常 |

#### TouchForce3D / TouchTorque2D
三维力与二维力矩向量：

| 类型 | 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- | --- |
| `TouchForce3D` | `x`, `y`, `z` | `float` | 三维力向量 `Fx`, `Fy`, `Fz` (mN) |
| `TouchTorque2D` | `x`, `y` | `float` | 二维力矩向量 `Mx`, `My` (Nm) |

#### TouchSampleState (枚举)

| 枚举项 | 数值 | 描述说明 |
| --- | ---: | --- |
| `Valid` | `1` | 模块数据在本帧有效 |
| `Disabled` | `2` | 模块已禁用 |
| `NotSampled` | `3` | 本帧未轮询该模组，且该模组没有为当前帧贡献任何数据 |
| `ReadFailed` | `4` | 模块读取失败 |
| `Unavailable` | `5` | 模块数据不可用 |
| `WarmingUp` | `6` | `hp_*` 模块预热尚未完成 |
| `SensorFault` | `7` | `hp_*` 模块已就绪，但传感器状态异常 |

快照读取采用请求范围内的一致性策略：完整 `snapshot()` 的任何已启用模块读取失败时整帧失败；选择式 `snapshot(module_indices=[...])` 的任何已选择且已启用模块读取失败时，本次选择读取整体失败。返回值不会用零值补齐失败模块；未选择模块直接不出现在返回帧中。因此 `NotSampled` 和 `ReadFailed` 仍为保留状态，正常快照中不会产生。

##### 触觉模组 layout_id 示例说明

`layout_id` 基础格式为 `<prefix>_<region>_<actual_point_count>`：

- `mt_*`：如 `mt_palm_36`, `mt_thumbtip_31`, `mt_fingertip_21`, `mt_thumbpad_57`, `mt_fingerpad_52`
- `mx_*`：根据设备运行时上报的实际点数生成；近期真机记录示例为 `mx_palm_53`、`mx_fingertip_56`、`mx_fingerpad_22`、`mx_fingertip_21` 和 `mx_fingerpad_27`。协议容量 `200/80/120` 不是实际点数，不得用于构造 layout ID
- `hp_*`：`hp_fingertip_48` 表示带 48 点点阵的指尖模组；`hp_fingertip_ft` 表示不带点阵、仅提供力/力矩及合力信号的指尖模组

基础 ID 只区分区域和实际点数。同点数模组的点序或空间几何不同时，必须由受控硬件 revision 或模组身份映射提供 `_v2`、`_v3` 等版本后缀；SDK 不根据点数猜测布局版本。当前自动识别只生成基础 ID，版本后缀必须先纳入 SDK 的受控 layout mapping 后才能作为公共 ID 发布。应用遇到未知 ID 时应停止套用已有坐标映射，但仍可按 `point_count` 读取一维数据。

#### TouchRegion (枚举)

| 枚举项 | Python 数值 | C/C++ 数值 | 描述说明 |
| --- | ---: | ---: | --- |
| `Fingertip` | `0` | `1` | 指尖区域；具体手指由 `region_index` 表示 |
| `FingerPad` | `1` | `2` | 指腹区域；具体手指由 `region_index` 表示 |
| `Palm` | `2` | `3` | 手掌区域，`region_index` 为 `0` |

`region_index` 在 `Fingertip` 和 `FingerPad` 区域内按 `Thumb/Index/Middle/Ring/Pinky = 0/1/2/3/4` 编号。应用不得使用不存在的 `ThumbTip`、`IndexPad` 等枚举项。

C ABI 额外定义 `C_REVO3_TOUCH_REGION_UNKNOWN = 0`，用于保证零初始化 `CRevo3TouchLayout` 的未使用区域槽位具有合法表示。`CRevo3TouchLayout` 不包含显式 module 计数；有效 module 必须从 `modules[0]` 开始连续排列，第一个 `layout_id[0] == '\0'` 的槽位结束有效列表，后续槽位必须保持未使用。有效 module 使用 `Unknown` region、或在结束槽位之后再次出现非空 `layout_id` 时，`revo3_device_touch_set_layout()` 返回参数错误。Python 和 C++ 对象 API 不公开该哨兵成员。

#### TouchSignal (枚举)

| 枚举项 | 描述说明 |
| --- | --- |
| `TouchPoint` | 触觉阵列压力点阵采样 |
| `Force3D` | 三维接触力 (`Fx`, `Fy`, `Fz`) |
| `Torque2D` | 二维接触力矩 (`Mx`, `My`) |
| `ResultantForce` | 接触法向标量合力 (`Fn`) |

C ABI 额外定义 `C_REVO3_TOUCH_SIGNAL_UNKNOWN = 0`，用途同上。它只能出现在 `signal_count` 范围外的未使用槽位；有效信号列表包含该值时，布局设置失败。Python 和 C++ 对象 API 不公开该哨兵成员。

#### TouchReadMode (枚举)
触觉数据模式：

| 枚举项 | 数值 | 描述说明 |
| --- | --- | --- |
| `PointArray` | `0` | **点阵模式**：输出点阵数据，点值类型由 `TouchValueMode` 决定。 |
| `LegacyForceSummary` | `1` | **二次标定区域合力兼容模式**：仅用于少量已发货设备，后续将删除；新应用不应形成依赖。 |

> **适用范围**：仅适用于 `mt_*` 模组。

#### TouchValueMode (枚举)
触觉值模式：

| 枚举项 | 数值 | 描述说明 |
| --- | --- | --- |
| `Adc` | `0` | **ADC 读数**：电路原始采样值（调试用）。 |
| `Force` | `2` | **压力值**：设备输出的压力值。 |

> **支持模式**：
> - `mt_*` 模组：支持 `Adc` (0) 与 `Force` (2)；寄存器 `4024` 的值 `1` 未使用，SDK 不对外暴露。
> - `mx_*` 模组：支持 `Adc` (0) 与 `Force` (2)；SDK 将公开值 `2` 映射为 `mx_*` 底层寄存器值 `1`。

#### TouchTareStatus (枚举)

| 枚举项 | 数值 | 描述 |
| --- | ---: | --- |
| `NotTared` | `0` | 尚未完成零漂校准 |
| `Tared` | `1` | 零漂校准已完成 |
| `BusyOrFailed` | `2` | 操作进行中或失败；设备协议未提供更细粒度状态 |

### 6.4 设备元数据结构 (Device Metadata)

#### DeviceInfo
设备基本信息与硬件标识：

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `model` | [`Revo3Model`](#35-产品型号枚举-revo3model) | 设备型号 (如 `Ultra`, `Pro`, `Basic`) |
| `serial_number` | `str` | 整手出厂序列号 (如 `BCUBR40124000001`) |
| `hand_side` | [`HandSide`](#handside-枚举) | 左右手类型 (`Left` / `Right`) |
| `hardware_revision` | `str` | 硬件版本号 (如 `v1.0.0`) |
| `motor_serial_numbers` | `list[str]` | 按当前逻辑关节顺序排列的已知电机出厂序列号列表 |
| `touch_serial_numbers` | `list[str]` | 触觉模块序列号列表 |

#### FirmwareInfo
模块固件版本信息：

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `controller_firmware_version` | `str \| None` | 当前已知的主控板固件版本；未知时为 `None` |
| `motor_firmware_versions` | `list[str]` | 按逻辑关节顺序排列的已知电机驱动板固件版本 |
| `touch_firmware_versions` | `list[str]` | 当前已知的触觉模组固件版本；无已知版本时为空列表 |

#### JointLayout
逻辑关节拓扑与数量定义：

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `layout_id` | `str` | 运动学关节拓扑标识符 (如 `Revo3Ultra21`, `Revo3Pro16`, `Revo3Basic13`，同系列不同触觉型号共享) |
| `version` | `int` | 布局定义规范的版本号 (如 `1`) |
| `joint_count` | `int` | 逻辑关节总数 (如 `21`, `16`, `13`) |

#### DeviceConfig
设备硬件与控制参数配置快照：

| 属性字段 | Python / C++ 类型 | 描述说明 |
| --- | --- | --- |
| `slave_id` | `int` | 当前设备从站 ID |
| `rs485_baudrate` | `int` | 当前 RS485 波特率 (bps) |
| `canfd_baudrate` | `int` | 当前 CANFD 数据域波特率 (bps) |
| `buzzer_enabled` | `bool` | 蜂鸣器状态 |
| `vibration_enabled` | `bool` | 振动马达状态 |
| `touch_screen_enabled` | `bool` | 触摸屏状态 |
| `teaching_mode_enabled` | `bool` | 零力/示教模式状态 |
| `software_stop_enabled` | `bool` | 软件停止状态 |
| `use_broadcast_id` | `bool` | 广播 ID 使用状态 |
| `power_on_auto_calibration_enabled` | `bool` | 上电自动标定使能 |
| `auto_clear_motor_faults_enabled` | `bool` | 自动清除电机故障使能 |
| `max_continuous_current_ma` | `float` | 最大连续电流 (mA) |
| `global_protect_current_ma` | `float` | 全局保护电流 (mA) |
| `joint_protect_current_ma` | `list[float]` / `std::array<float, 21>` | 各逻辑关节保护电流 (mA)；有效长度由 `JointLayout.joint_count` 决定 |
| `joint_min_position_deg` | `list[float]` / `std::array<float, 21>` | 各逻辑关节最小位置限制 (deg)；有效长度由 `JointLayout.joint_count` 决定 |
| `joint_max_position_deg` | `list[float]` / `std::array<float, 21>` | 各逻辑关节最大位置限制 (deg)；有效长度由 `JointLayout.joint_count` 决定 |
| `joint_min_speed_rpm` | `list[float]` / `std::array<float, 21>` | 各逻辑关节最小速度限制 (rpm)；有效长度由 `JointLayout.joint_count` 决定 |
| `joint_max_speed_rpm` | `list[float]` / `std::array<float, 21>` | 各逻辑关节最大速度限制 (rpm)；有效长度由 `JointLayout.joint_count` 决定 |
| `persistence_scope` | `str` / - | Python 快照提供的持久化范围说明；当前值为 `firmware-defined` |

#### RuntimeOptions
SDK 运行客户端参数配置（进程内默认值，不写入设备）：

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `state_subscription_period_ms` | `int` | State 订阅默认拉取间隔 (ms)，默认 20 |
| `touch_subscription_period_ms` | `int` | Touch 订阅默认拉取间隔 (ms)，默认 20 |
| `health_subscription_period_ms` | `int` | Health 订阅默认拉取间隔 (ms)，默认 1000 |
| `servo_command_timeout_ms` | `int` | Servo 会话相邻两次流式命令的默认超时 (ms)，默认 100 |

#### Timestamp
数据帧接收与系统时间戳：

| 属性字段 | 数据类型 | 描述说明 |
| --- | --- | --- |
| `sec` | `int` | 秒数 |
| `nsec` | `int` | 纳秒数 (0~999,999,999) |
| `clock` | `TimestampClock` | 时钟源类型 (`ProcessMonotonic`, `UnixRealtime`) |

#### TimestampClock (枚举)

| 枚举项 | 数值 | 描述说明 |
| --- | ---: | --- |
| `ProcessMonotonic` | `0` | 进程内单调递增时钟 (SDK 内部时钟，不受系统时间调整影响) |
| `UnixRealtime` | `1` | 协调世界时 Unix 纪元时间戳 (UTC epoch realtime clock) |

#### HandSide (枚举)

| 枚举项 | 数值 | 描述说明 |
| --- | ---: | --- |
| `Left` | `0` | 左手 |
| `Right` | `1` | 右手 |

## 7. 等待、取消和运动冲突

目标运动、设备重启和固件升级返回 Handle。程序可以通过 Handle 查看状态、等待完成或请求取消。`OperationHandle` 是面向调用方的运动/维护操作句柄名称，其生命周期统一使用 `OperationState`；SDK 不定义重复的 `MotionState`。关节标定、软件停止和软件停止恢复是直接等待设备 I/O 的单次命令，不返回 Handle。设备重启一旦进入设备 I/O 就不能撤回，对其 Handle 调用 `cancel()` 会保持当前状态。

```text
OperationHandle
├── id
├── state
└── error
```

Handle 状态包括 `Pending`、`Running`、`Succeeded`、`Cancelled`、`Preempted`、`Failed` 和 `Indeterminate`。注：在当前硬件通信模型下，主动调用 `cancel()` 的协作式取消终态为 `Indeterminate`（结果不确定，需先读实际状态，不能直接重试）；`Cancelled` 作为保留枚举成员供未来支持确定性硬件取消确认的协议扩展使用。当前固件没有提供统一的进度和设备端开始、完成时间，因此 Handle 不提供这些字段。Indeterminate 表示 SDK 不知道设备最终执行到了哪一步，调用者不能直接重试。

### 7.1 OperationState (枚举)

| 枚举项 | 数值 | 是否终态 | 描述说明 |
| --- | ---: | :---: | --- |
| `Pending` | `0` | 否 | 已创建，尚未开始执行 |
| `Running` | `1` | 否 | 正在执行 |
| `Succeeded` | `2` | 是 | 操作成功完成 |
| `Cancelled` | `3` | 是 | 设备端已确定取消；当前协议通常不能提供该确认 |
| `Preempted` | `4` | 是 | 被同类新操作替换 |
| `Failed` | `5` | 是 | 操作失败且错误对象可读 |
| `Indeterminate` | `6` | 是 | 最终设备效果无法确认，必须先读取实际状态 |

目标运动使用协作式取消：SDK 会等待当前寄存器请求完整结束，在下一个控制周期边界停止发送轨迹点并释放软件控制权，不会中途丢弃串口请求。固件升级取消会在下一个 DFU 轮询或数据包边界发送设备端 abort 命令。取消请求已经发出但设备最终位置或写入结果无法确认时，Handle 状态为 `Indeterminate`。

Python 的 `handle.error` 和 C++ 的 `handle.error()` 返回与该 Handle 绑定的 `SdkError`；没有错误时分别返回 `None` 和 `std::nullopt`。终态与错误作为同一个结果发布，因此观察到 `Failed` 或带错误的 `Indeterminate` 时，对应错误已经可读，不依赖线程局部的最近一次 API 错误。

同一只 Hand 不能同时执行 `move_to()` 和 `ServoSession`，冲突时返回 `ControlConflict`。`move_to()` 由 SDK 生成并发送轨迹；`ServoSession` 由用户持续发送新目标。

正在执行 `move_to()` 时再次调用 `move_to()`，新目标会替换旧目标。SDK 从当前反馈位置和速度重新规划，旧 `OperationHandle` 进入 `Preempted`。该行为只适合低频重新规划，不适合频繁更新目标；频繁发送目标应使用 `open_servo()`。

关节标定使用单命令方式。发送前检查当前没有运动；Touch 读取和 Touch 标定不影响运动。固件没有提供标定进度或完成状态，写响应只表示命令已经发出，不能证明设备内部标定已经结束。

## 8. 错误、超时和重试

```text
SdkError
├── code
├── message
├── retryable
├── operation_effect
├── recovery_requirement
└── low_level_cause
```

`SdkError` 是所有 API 失败时返回的结构化错误对象，各字段描述不同维度：`code` 表示失败原因；`operation_effect` 表示命令对设备的影响；`recovery_requirement` 表示再次操作前必须完成的恢复步骤；`retryable` 表示完成该恢复步骤后是否允许重试同一操作；`message` 是稳定的用户可读说明，`low_level_cause` 仅用于底层诊断。写命令失败且 `operation_effect` 为 `Indeterminate`（结果不确定）时，命令可能已在设备生效但响应丢失，程序应先读取设备状态，不能直接重试。C ABI 的 `CRevo3ErrorInfo` 使用定长字符串保存 `message` 和 `low_level_cause`，C++ `SdkError::low_level_cause()` 返回 `std::optional<std::string>`。

Python 中 `code`、`operation_effect` 和 `recovery_requirement` 分别使用 `SdkErrorCode`、`OperationEffect` 和 `RecoveryRequirement` 枚举；C++ 使用同名强类型枚举，不公开无类型的整数错误字段。

### 8.1 错误枚举

`SdkErrorCode` 是可供程序分支判断的唯一错误标识。C++ 额外保留 `Unknown = 0`，用于转换无法识别的 C ABI 值；Python 不导出该成员。

| 数值 | `SdkErrorCode` | 典型含义 |
| ---: | --- | --- |
| `1` | `ConnectionFailed` | 建立连接或传输失败 |
| `2` | `InvalidArgument` | 参数不满足公开合同 |
| `3` | `InvalidState` | 当前生命周期或设备状态不允许该操作 |
| `4` | `Timeout` | 有界等待或通信超时 |
| `5` | `UnsupportedCapability` | 当前型号、固件、布局或传输不支持该能力 |
| `6` | `DeviceFault` | 设备明确报告故障 |
| `7` | `Internal` | SDK 内部错误 |
| `8` | `ControlConflict` | 与当前运动或流式控制所有权冲突 |

#### OperationEffect (枚举)

| 枚举项 | 数值 | 描述说明 |
| --- | ---: | --- |
| `NotApplied` | `1` | 已确认操作未应用到设备 |
| `PartiallyApplied` | `2` | 操作仅部分生效，需读取状态并按具体 API 恢复 |
| `Indeterminate` | `3` | 无法确认是否生效，不得直接重试写命令 |

#### RecoveryRequirement (枚举)

| Python 枚举项 | C++ 枚举项 | 数值 | 描述说明 |
| --- | --- | ---: | --- |
| `None_` | `None` | `0` | 不要求额外恢复动作；Python 使用 `None_` 避免与关键字混淆 |
| `Retry` | `Retry` | `1` | 无需重连或人工处置；`retryable=true` 时可直接重试 |
| `Reconnect` | `Reconnect` | `2` | 需要重新建立连接并重新获取会话状态 |
| `OperatorAction` | `OperatorAction` | `3` | 设备明确报告故障，需要操作人员检查或干预 |

SDK 只返回当前有明确判定依据的恢复动作。安全保护恢复和整机断电重启尚无统一的固件语义与自动判定路径，因此不作为 `RecoveryRequirement` 枚举项对外暴露。

`retryable=true` 不等于 `recovery_requirement=Retry`。例如只读操作因连接失败时返回 `Reconnect` 和 `retryable=true`，表示必须先重连，之后才允许重试原读取；`Retry` 表示不需要重连即可重试。任何 `Indeterminate` 写操作都不会标记为可重试。

重试规则：

- 以下规则适用于 Hand API 发起的设备请求。Manager 的设备扫描、连接和重连按各自流程处理，不属于命令重试。
- 只读请求只有在连接未发生重建且策略允许时才能自动重试。
- 会改变设备状态的请求在响应丢失后必须返回“结果未知”：命令可能已执行，也可能未执行，SDK 不能自动再发一次。
- 断联、重连、安全恢复和重新发送命令是不同动作。
- `wait(timeout)` 超时只结束本次等待，不自动取消设备操作。
- Python 和 C++ 必须保留相同的错误码和处理方式。

```python
# 示例：捕获结构化 SDK 异常与 Indeterminate 结果判断
try:
    await hand.motion.move_to(targets, duration=1.0)
except sdk.SdkError as error:
    print(f"Code: {error.code}")
    if error.operation_effect == sdk.OperationEffect.Indeterminate:
        # 响应丢失：先读状态确认是否已生效，不可盲目重复发送
        state = await hand.state.snapshot()
```

## 9. 数据、时间与物理单位规范

### 9.1 物理单位

- **控制与反馈单位**：SDK 公共 API 统一使用角度 `degree` (°)、旋转角速度 `rpm` 与电流 `mA`；底层驱动负责必要的进制或物理量转换。
- **电流不是已标定关节力矩**：电机反馈和 MIT 前馈字段都是 mA 电流。设备未提供 Nm 单位的已标定关节力矩，因此公共字段保持 `current` / `current_ma`，不改名为 `torque`。

### 9.2 时间戳与接收保证

- **接收时间戳**：`State` 与 `Touch` 快照中的 `timestamp` 表示 SDK 接收到数据包的时间。Linux SocketCAN 优先使用内核接收时间戳，其他传输层使用进程单调时钟。
- **定位与限制**：`timestamp` 不是固件物理采样时刻，不可用于多设备间的硬件时钟同步。多帧拼接的快照可能存在微小传输时差，`timestamp` 表示整组数据接收完成的时间，不保证各字段同一时刻采样。

### 9.3 物理单位转换 (Physical Unit Conversion)

为方便 ROS / ROS 2 机器人算法与国际单位制 (SI Units) 场景对接，SDK 在各语言层提供显式物理量换算基准与转换工具函数：

#### 物理量换算基准
- **角度 (Angle)**: `1 degree = (π / 180) rad` (约 `0.0174533 rad`), `1 rad = (180 / π) degree` (约 `57.2958 degree`)
- **角速度 (Angular Velocity)**: `1 rpm = (π / 30) rad/s` (约 `0.10472 rad/s`), `1 rad/s = (30 / π) rpm` (约 `9.5493 rpm`)
- **电流 (Current)**: `1 mA = 0.001 A`, `1 A = 1000 mA`

#### C ABI 与 C++ 单位工具
- **C ABI (`revo3-sdk.h`)**：
  - 标量转换：`revo3_deg_to_rad(float)`, `revo3_rad_to_deg(float)`, `revo3_rpm_to_rad_s(float)`, `revo3_rad_s_to_rpm(float)`, `revo3_ma_to_a(float)`, `revo3_a_to_ma(float)`
  - 批量数组转换：`revo3_deg_to_rad_array(const float* in, float* out, size_t count)`, `revo3_rad_to_deg_array(...)`, `revo3_rpm_to_rad_s_array(...)`, `revo3_rad_s_to_rpm_array(...)`, `revo3_ma_to_a_array(...)`, `revo3_a_to_ma_array(...)`
- **C++ 命名空间 (`revo3::units`)**：
  - 提供 `revo3::units::deg_to_rad(...)` 等重载，支持 `float`、`std::vector<float>` 与 `std::array<float, N>`。

#### Python 单位转换
- `main_mod.deg_to_rad(value)`：支持传入单数值或浮点数列表/元组，返回对应的弧度值或列表。
- `main_mod.rad_to_deg(value)`：将弧度转为角度。
- `main_mod.rpm_to_rad_s(value)`：将转速 rpm 转为角速度 rad/s。
- `main_mod.rad_s_to_rpm(value)`：将角速度 rad/s 转为转速 rpm。
- `main_mod.ma_to_a(value)`：将电流 mA 转为安培 A。
- `main_mod.a_to_ma(value)`：将安培 A 转为电流 mA。

```python
# 示例：Python 批量与单值单位转换
from bc_revo3_sdk import main_mod as sdk

rad_positions = sdk.deg_to_rad(state.positions_deg)  # list[float] 批量转为 rad
target_deg = sdk.rad_to_deg(ros_command_rad)      # 将 ROS rad 指令转为 deg
```

### 9.4 基础运行时与模块级工具 (Runtime Utilities & Logging)

SDK 提供跨语言的基础环境配置、日志管理、版本查询及端口探测工具：

#### 日志系统初始化与契约
- **C ABI (`revo3-sdk.h`)**：`revo3_init_logging(level, enable_file_logging)`；`enable_file_logging=true` 时同时写入 `logs/revo3_<timestamp>.log`。
- **C++ (`revo3::init_logging`)**：`revo3::init_logging(level=LOG_LEVEL_INFO, enable_file_logging=true)`。建议在进程启动时初始化一次；后续调用可更新日志级别，但输出目标由首次调用确定。
- **Python (`main_mod.init_logging`)**：`main_mod.init_logging(level=LogLevel.Info, enable_file_logging=True)`。设置 SDK 日志级别；启用文件日志时添加 SDK 专用的 Python `logging.FileHandler`，写入 `logs/revo3_<timestamp>.log`。重复调用会替换该专用文件 handler，不影响应用自行配置的其他 handler。

#### 版本与硬件工具
- **版本查询**：
  - Python：`main_mod.get_sdk_version()` 返回包含预发布后缀的精确 SDK 版本字符串。
  - C++：`revo3::api_version()` 返回编码版本号与语义版本字符串。
- **端口枚举与白名单配置**：
  - `main_mod.list_available_ports()`：返回 `list[SerialPortInfo]`，只枚举本机候选端口，不主动探测设备。
  - `main_mod.configure_usb_vid_pid_allowlist(custom_ids=[], include_defaults=True)`：配置 USB 适配器 VID/PID 白名单；`include_defaults=False` 时只使用调用方提供的条目。

## 10. 语言与适配规范

### 10.1 C/C++ API

- **命名空间与类型**：最低编译器标准为 C++17，公共类型位于 `revo3` 命名空间（如 `revo3::Manager`、`revo3::Hand`、`revo3::OperationHandle`），类名与方法名不重复添加 `revo3_` 前缀。
- **版本查询**：`revo3::api_version()` 返回编码版本、major/minor/patch 和包含预发布后缀的精确字符串（例如 `2.0.0-rc.3`）。
- **C ABI**：`revo3-sdk.h` 可由 C11 和 C++17 编译器直接包含；C 符号统一使用 `revo3_` 前缀。SDK 2.0 不导出 1.x 的 `DeviceHandler`、手动 transport 初始化、全局 callback setter 或无前缀 `stark_*` 兼容入口。
- **对象层**：C++17 对象 API 基于公开 C ABI 实现，提供 RAII、强类型参数和异常转换，不额外形成第二套底层协议实现。
- **资源管理与生命周期**：`Manager` 与 `Hand` 仅支持移动构造与赋值，禁止拷贝。对象离开作用域时自动释放资源；亦可显式调用 `close()`，重复调用不会报错。
- **异步句柄与等待**：目标运动、重启与固件升级等长耗时操作立即返回 Handle 对象，支持调用 `wait(std::chrono::milliseconds)` 阻塞等待完成。
- **异常与状态表达**：运行时错误抛出 `revo3::SdkError`，运动与操作状态通过 `OperationState` 返回。

### 10.2 Python API

- **模块设计与类型**：只导出本规范定义的类、枚举与数据结构，不提供 1.x module-level 或 `DeviceContext` 兼容入口；最低支持 Python 3.10，并使用 `T | None`、`Sequence[T]` 和精确的 `Awaitable[T]` stub 类型。
- **资源管理与生命周期**：支持显式调用 `close()`，也支持 `async with` 上下文管理器，确保退出时自动关闭端口与连接。
- **异步句柄与等待**：目标运动、重启与固件升级等长耗时操作返回 Handle 对象，调用 `await handle.wait(timeout)` 等待完成（Handle 本身不可直接 `await`）。
- **异常与状态表达**：与 C++ 共享相同的 `SdkError` 异常结构与 `OperationState` 状态表达。
