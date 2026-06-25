# 视触觉传感器 SDK 力估计使用说明

本说明针对使用视触觉传感器 SDK 时加载力估计权重。  
SDK 其他使用说明见：
- https://github.com/ViTai-Tech/ViTai-SDK-Release
- https://docs.vitai.site/docs/sdk-usage/intro

---

## 安装 VTS SDK (pyvitaisdk4bc)

由于 BrainCo 版本的视触觉传感器 SDK (`pyvitaisdk4bc`) 进行了定制，我们提供了一个一键安装脚本，可以自动根据操作系统和架构（Linux x86_64、Linux aarch64 或 Windows amd64）下载安装对应的 `.whl` 依赖包：

```bash
# 在项目根目录下运行：
bash python/install_vts_whl.sh
```

如果您需要手动安装，也可以根据当前系统平台直接通过以下链接进行安装：
*   **Linux x86_64 平台**：
    ```bash
    pip install https://focus-resource.oss-cn-beijing.aliyuncs.com/universal/bc-stark-sdk/libs/vts/pyvitaisdk4bc-1.0.10-py3-none-linux_x86_64.whl
    ```
*   **Linux aarch64 (ARM64) 平台**：
    ```bash
    pip install https://focus-resource.oss-cn-beijing.aliyuncs.com/universal/bc-stark-sdk/libs/vts/pyvitaisdk4bc-1.0.10-py3-none-linux_aarch64.whl
    ```
*   **Windows amd64 平台**：
    ```bash
    pip install https://focus-resource.oss-cn-beijing.aliyuncs.com/universal/bc-stark-sdk/libs/vts/pyvitaisdk4bc-1.0.10-py3-none-win_amd64.whl
    ```

---

## 力估计模型权重准备

1. **从提供的百度网盘链接下载力估计权重文件**，并保存到本地目录。  
   例如：

   ```
   ./checkpoints/
   ```

2. **目录结构要求**：

   使用 SDK 时，需要通过 `force_model_path` 指定**力估计模型的父目录**，而不是单个 `.onnx.enc` 文件。示例结构如下：

   ```
   ./checkpoints/
   ├── {SN_1}/
   │   ├── {SN_1}.onnx.enc
   │   ├── {SN_1}.trt.enc
   │   └── {SN_1}.rknn.enc
   ├── {SN_2}/
   │   ├── {SN_2}.onnx.enc
   │   ├── {SN_2}.trt.enc
   │   └── {SN_2}.rknn.enc
   └── ...
   ```

   其中 `{SN_1}`、`{SN_2}` 等为传感器的产品序列号（SN），可通过 SDK 查询产品序列号。  
   根据 SDK 运行平台选择对应的权重：
   - Jetson 平台：加载 `.trt.enc`
   - RK3588 平台：加载 `.rknn.enc`
   - 其他平台：使用 `.onnx.enc`

3. **自动匹配加载**：

   示例脚本会根据当前连接传感器的产品 SN，自动在 `--force-model-dir` 指定的父目录下查找对应子目录中的权重文件并完成加载。

   例如传感器 SN 为 `VTSensorI123456`，则脚本会自动寻找：

   ```
   ./checkpoints/VTSensorI123456/VTSensorI123456.onnx.enc
   ```

---

## 数据采集脚本

`python/vts/vts_collect_sensor_data.py` 是在线数据采集可视化示例脚本，主要功能：

- 自动发现已连接的视触觉传感器
- 根据传感器 SN 自动匹配并加载力估计模型权重
- 实时显示力曲线、差分图、深度图、标记点图
- 支持同时显示多个传感器数据


### 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--sn` | 指定传感器 SN，多个用英文逗号分隔 | 自动发现所有设备 |
| `--force-model-dir` | 力估计模型权重的父目录 | `./checkpoints` |

### 常用命令示例

```bash
# 自动检测并显示所有传感器
python python/vts/vts_collect_sensor_data.py

# 指定力估计模型父目录
python python/vts/vts_collect_sensor_data.py --force-model-dir ./checkpoints

# 指定一个传感器 SN
python python/vts/vts_collect_sensor_data.py --sn VTSensorI123456

# 指定多个传感器 SN（逗号分隔）
python python/vts/vts_collect_sensor_data.py --sn VTSensorI123456,VTSensorI654321
```

### 操作说明

- 按 `q` 或 `ESC`：退出程序
- 按 `e`：重新校准所有传感器

---

## 注意事项

1. **模型路径**：请确保从百度网盘下载的力估计权重按照 `{父目录}/{SN}/{SN}.onnx.enc` 的结构存放，并通过 `--force-model-dir` 指定父目录。

2. **SN 自动匹配**：示例脚本会读取当前连接设备的产品 SN，并自动在模型父目录下查找同名子目录中的权重文件，无需手动指定单个模型文件。

3. **平台选择**：根据运行平台选择 `.trt.enc`、`.rknn.enc` 或 `.onnx.enc`。
