# Revo3 C 和 C++ 示例

[English](README.md) | [简体中文](README.zh-CN.md)

公开 C ABI 头文件兼容 C11。C++ 示例要求兼容 C++17 或更新版本的编译器，并使用 `dist/include/revo3/revo3.hpp` 中的 RAII 封装。示例仅适用于 Revo3，覆盖 Modbus 和 CANFD 发现、设备操作、运动、状态及触觉数据。

`platform/linux/revo3_ec` 下的独立 Linux EtherCAT 示例直接使用 IgH `libethercat`，不依赖 Revo3 SDK 主共享库。完整的 EtherCAT 部署和故障排查说明见[英文专项文档](platform/linux/revo3_ec/README.md)。

## 构建

从仓库根目录运行：

```bash
bash download-lib.sh
make -C c
```

纯 C、嵌入式 C 和跨语言绑定使用 `dist/include/revo3-sdk.h`。C++ 应用可包含 `revo3/revo3.hpp`，使用仅可移动的 `revo3::Manager`、`revo3::Hand` 和 `revo3::OperationHandle` API。C++ 对象方法省略冗余的 `revo3_` 前缀；只有 C ABI 符号保留该前缀。

SDK 日志默认同时写入终端和 `logs/` 下带时间戳的文件。请在创建 `revo3::Manager` 前初始化一次日志：

```cpp
revo3::init_logging(LOG_LEVEL_INFO, true);   // Terminal and log file
revo3::init_logging(LOG_LEVEL_DEBUG, false); // Terminal only
```

第一次调用确定进程的输出方式。后续调用可以调整日志级别，但不能替换 logger 输出目标。

最小 C++ 示例：

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

需要缩小运动范围时，使用 `move_joint()`、`flex_finger()` 或 `move_thumb()`。`quickstart` 参数分别演示这些方式，并避免启动相互重叠的运动。`move_to()` 会立即返回 handle，因此核心 C++ 运动路径不需要协程。

Linux 上单独构建并运行纯 C++ EtherCAT 示例：

```bash
make -C c/platform/linux/revo3_ec
./c/platform/linux/revo3_ec/revo3_benchmark \
  --scenario motor --read full-state --duration 10
```

运行前按照专项文档检查 IgH 主站、`/dev/EtherCAT0` 和所选网卡。

## 运行

设备发现和常用示例：

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

`touch_sensor` 只读。对于 Ultra VisionTouch，它仅报告检测到的主链压力阵列或高密度阵列指垫和掌部模块；独立视觉触觉指尖不属于本 SDK snapshot。如果序列号和寄存器 135 无法识别具有压力阵列主链拓扑的设备，请仅在确认硬件布局后应用会话级 override：

```bash
./c/build/demo/touch_sensor --port /dev/ttyUSB0 \
  --model ultra-vision-touch --layout vision-mt
```

确认高密度触觉阵列后，可使用 `--layout vision-mx --mx-point-counts <11 comma-separated counts>`。这些 override 不写入设备寄存器，并且不包含独立视觉触觉指尖。

`firmware_update` 是独立的破坏性维护流程。它支持 `main`、`image` 和 `motor` 目标，默认超时为 600 秒，且没有 `--run` 时拒绝连接。结果为 `Indeterminate` 时不要立即重试；先检查 operation effect 和 recovery requirement，再验证设备状态。

`mit_plan` 与 Python `mit_plan.py` 使用相同默认计划：100 Hz 五次轨迹，从初始反馈位置移动到各目标关节配置范围的 50% 后返回，每段 800 ms，`Kp=3.0`、`Kd=0.3`，前馈电流为零。位置或速度限位无效时，示例会在打开 ServoSession 前停止。

`touch_hybrid` 要求已确认的指尖力/力矩和压力阵列硬件布局。默认只改变当前 SDK 会话的解析布局。仅在确实需要改变触觉校准状态时传入 `--test-tare`。

`discover_devices` 默认找到第一个匹配项后停止。使用 `--scan-all` 扫描所有候选项，或用 `--port`、`--protocol`、`--slave-id`、`--modbus-baudrate`、`--canfd-data-baudrate` 限制扫描范围。CANFD 自动检测默认依次尝试 `5M`、`4M`、`2M`、`1M`；BrainCo USB2CANFD 仅支持 `5M`。

`subscriptions` 执行有限次数的 State、可选 Touch 和 Health pull subscription，显式关闭各 subscription，并打印运行时计数器。请求周期是 SDK pull 的最小间隔，不代表设备采样率。

需要在发现完成前接收 callback 或取消的底层 C 集成，应直接使用异步 C ABI。传给 callback 的 `CRevo3DetectedDevice` 指针仅在 callback 执行期间有效，返回前复制需要的字段。非零 `slave_id`、`modbus_baudrate` 或 `canfd_data_baudrate` 只探测指定值；零值使用默认列表。GUI 或事件循环应用应保留扫描 handle，并在用户选择设备或取消后依次调用 `revo3_auto_detect_stop()`、`revo3_auto_detect_join()` 和 `revo3_auto_detect_free_handle()`。

## 串口故障排查和清理

如果 `connect_auto` 或设备扫描返回 `Failed to open ... at 5000000 bps: Invalid argument` 或 `No Revo3 device detected`，请检查是否有后台进程仍占用物理串口：

```bash
# Find the process holding the serial port
lsof /dev/tty.usbserial*

# Ask the process to terminate cleanly
kill <PID>

# Force termination only if it does not exit
kill -9 <PID>
```

应用退出时始终调用 `hand.close()` 和 `manager.close()`，并正确处理 `SIGINT`（Ctrl+C），确保释放底层操作系统文件描述符。

## 动作演示

四个 C++17 入口分别演示对掌、手指功能、手势舞和经典正弦 servo。默认仅离线预览，只有传入 `--run` 才会连接设备。C++ 可执行文件不调用 Python。

共享动作顺序、安全边界和 Python/C++ 差异见[动作演示指南](../python/revo3/MOTION_DEMOS.zh-CN.md)（[English](../python/revo3/MOTION_DEMOS.md)）。

```bash
./c/build/demo/opposition_demo
./c/build/demo/finger_function_demo
./c/build/demo/gesture_dance_demo
./c/build/demo/servo_classic_demo

# Replace the endpoint and address with the intended device
./c/build/demo/gesture_dance_demo --port brainco:0 --slave-id 127 --side right --run
```

候选姿态与 Python 默认值一致，包括 60/60/45 度波浪幅度、连续重叠手指脉冲和对掌时延迟屈指。它们不是经过标定的指尖接触坐标。示例要求 21 关节布局和匹配的手型；左手机械间隙仍需单独验证。

通用参数包括 `--tempo`、`--repeat`、`--feedback-tolerance-deg`（0 到 2 度）和 `--skip-joints`（逗号分隔的逻辑索引，例如 `2,12,20`）。排除的关节接收零 Kp、Kd、速度和前馈电流，不主动保持位置。仅容忍显式排除关节的堵转故障；新故障会停止序列。运行前需单独处理软件急停和零力模式，示例不会清故障或自动恢复。

四个示例均使用主机 MIT streaming。每个目标都经过设备限位检查，过渡时间会延长以满足速度限位。示例在步骤之间和约每 250 ms 检查 Health。请求发送间隔为 10 ms，命令超时为 500 ms，但不保证实时。正常结束时返回有界的初始姿态，并对未排除关节检查 5 度返回误差。异常或中断会关闭会话并尝试软件急停，不自动执行返回动作。

经典 servo 默认范围为 0 到 60 度、频率 0.75 Hz、3 个周期，并使用 25 rad/s 临界阻尼滤波。它支持 `--minimum`、`--maximum`、`--frequency`、`--cycles` 和 `--omega`；零值关闭滤波。默认控制四指的 12 个屈伸关节，固定使用 Kp=1、Kd=0.1。与 Python 版本不同，C++ 版本不支持自定义关节、发送率、JSON profile 或结束时卸力。`--tempo` 只缩放过渡时间，不改变正弦频率。

独立对掌示例的食指目标为拇指 `[73,45,40,10,15]` 度、食指屈伸 `[75,65,50]` 度；其余手指使用拇指 `[70,40,35,10,15]` 度和目标手指屈伸 `[70,60,45]` 度。这些未标定候选值不保证指尖接触。

默认姿态已在右手设备上完成有限的空载验证，但尚未通过全部 21 关节参与的验收。左手机械间隙、指尖接触、实物抓握和断开连接后的持续保持仍未验证。常规使用前，应降低节奏并针对目标手逐步标定候选姿态。
