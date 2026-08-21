#!/usr/bin/env python3
# coding=utf-8
"""
VTSensor 在线数据采集示例脚本

主要功能：
- 自动发现并连接视触觉传感器
- 根据传感器 SN 自动加载对应的力估计模型权重
- 实时显示力曲线、差分图、深度图、标记点图
- 支持同时显示多个传感器数据

使用前提：
1. 从百度网盘下载力估计权重并保存到本地
2. 权重目录结构为：{force_model_dir}/{SN}/{SN}.onnx.enc
3. 通过 --force-model-dir 指定模型权重的父目录
"""

from datetime import datetime
from collections import deque
import math
import os
import time
import cv2
import numpy as np
import argparse
from pyvitaisdk import VTSensor, VTSDeviceFinder, VTSDataType, VTSError


def extract_force6d_mean(force6d_vector: np.ndarray) -> np.ndarray:
    """将 force6d 数据统一为长度为 6 的均值向量。"""
    arr = np.asarray(force6d_vector)
    if arr.ndim == 1:
        if arr.shape[0] >= 6:
            return arr[:6].astype(np.float32)
        out = np.zeros(6, dtype=np.float32)
        out[:arr.shape[0]] = arr.astype(np.float32)
        return out

    # 兼容 (N,M,6) 或其他带末维 6 的形状：对前面维度求均值
    if arr.shape[-1] >= 6:
        mean6 = arr[..., :6].reshape(-1, 6).mean(axis=0)
        return mean6.astype(np.float32)

    flat = arr.reshape(-1)
    out = np.zeros(6, dtype=np.float32)
    take = min(6, flat.shape[0])
    out[:take] = flat[:take].astype(np.float32)
    return out


def render_force_curve_panel(
        force_history,
        latest_force6d: np.ndarray,
        panel_height: int,
        panel_width: int,
) -> np.ndarray:
    """渲染左侧实时力值曲线面板（显示合力范数）。"""
    min_plot_y_max = 1.0
    panel = np.full((panel_height, panel_width, 3), 20, dtype=np.uint8)

    # 预留顶部信息区，避免 Current 与其他文本重叠
    top_margin = 110
    bottom_margin = 50
    left_margin = 60
    right_margin = 20
    plot_h = max(1, panel_height - top_margin - bottom_margin)
    plot_w = max(1, panel_width - left_margin - right_margin)

    # 坐标轴
    cv2.rectangle(panel, (left_margin, top_margin), (left_margin + plot_w, top_margin + plot_h), (80, 80, 80), 1)

    if len(force_history) > 1:
        hist = np.asarray(force_history, dtype=np.float32)
        y_max = float(np.max(hist))
        plot_y_max = max(min_plot_y_max, y_max)

        points = []
        for i, val in enumerate(hist):
            x = left_margin + int(i * (plot_w - 1) / max(1, len(hist) - 1))
            y = top_margin + plot_h - int((val / plot_y_max) * (plot_h - 1))
            points.append([x, y])

        cv2.polylines(panel, [np.asarray(points, dtype=np.int32)], False, (80, 220, 80), 2)
        cv2.putText(panel, f"max {y_max:.3f}", (left_margin + 4, top_margin + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (220, 220, 220), 1)

    current_norm = float(np.linalg.norm(latest_force6d[:3]))
    cv2.putText(panel, "Realtime Force Curve (||Fx,Fy,Fz||)", (20, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (235, 235, 235),
                2)
    cv2.putText(panel, f"Current: {current_norm:.3f}", (20, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (180, 230, 255), 2)
    cv2.putText(
        panel,
        f"Fx={latest_force6d[0]:.3f}, Fy={latest_force6d[1]:.3f}, Fz={latest_force6d[2]:.3f}",
        (20, 88),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (200, 200, 200),
        1,
    )

    return panel


def build_sensor_panel(data, force_history, left_panel_width_ratio: float, sn: str) -> np.ndarray:
    """构建单个传感器的两列面板（左力曲线 + 右四图）。"""
    warped_img = data[VTSDataType.WARPED_IMG]
    diff_img = data[VTSDataType.DIFF_IMG]
    depth_map = data[VTSDataType.DEPTH_MAP]
    marker_img = data[VTSDataType.MARKER_IMG]
    force6d_vector = data[VTSDataType.FORCE6D_VECTOR]

    force6d_mean = extract_force6d_mean(force6d_vector)
    force_norm = float(np.linalg.norm(force6d_mean[:3]))
    force_history.append(force_norm)

    depth_max = max(1, np.max(depth_map))
    tmp_depth_map = (depth_map / depth_max * 255).astype(np.uint8)
    depth_map_display = np.stack([tmp_depth_map] * 3, axis=-1)

    right_column = np.vstack([warped_img, diff_img, marker_img, depth_map_display])
    left_panel_width = int(right_column.shape[1] * left_panel_width_ratio)
    force_curve_panel = render_force_curve_panel(
        force_history=force_history,
        latest_force6d=force6d_mean,
        panel_height=right_column.shape[0],
        panel_width=left_panel_width,
    )
    combined = np.hstack([force_curve_panel, right_column])
    return combined


def compose_adaptive_grid(panels, max_canvas_w: int = 1920, max_canvas_h: int = 1080) -> np.ndarray:
    """将多个传感器面板按数量自适应拼接为网格。"""
    if len(panels) == 0:
        return np.full((240, 480, 3), 20, dtype=np.uint8)

    count = len(panels)
    cols = int(math.ceil(math.sqrt(count)))
    rows = int(math.ceil(count / cols))

    cell_h = max(panel.shape[0] for panel in panels)
    cell_w = max(panel.shape[1] for panel in panels)
    canvas = np.full((rows * cell_h, cols * cell_w, 3), 20, dtype=np.uint8)

    for idx, panel in enumerate(panels):
        r = idx // cols
        c = idx % cols
        y = r * cell_h
        x = c * cell_w
        h, w = panel.shape[:2]
        canvas[y:y + h, x:x + w] = panel

    scale = min(max_canvas_w / canvas.shape[1], max_canvas_h / canvas.shape[0], 1.0)
    if scale < 1.0:
        new_w = max(1, int(canvas.shape[1] * scale))
        new_h = max(1, int(canvas.shape[0] * scale))
        canvas = cv2.resize(canvas, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return canvas


def render_status_panel(title: str, lines, panel_height: int, panel_width: int) -> np.ndarray:
    """渲染状态/错误占位面板。"""
    panel = np.full((panel_height, panel_width, 3), 25, dtype=np.uint8)
    cv2.rectangle(panel, (0, 0), (panel_width - 1, panel_height - 1), (80, 80, 80), 1)
    cv2.putText(panel, title, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
    y = 62
    for line in lines:
        cv2.putText(panel, str(line), (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (220, 220, 220), 1)
        y += 28
    return panel



def infer_panel_size(sensor_panels) -> tuple:
    """推断面板大小，供错误占位图使用。"""
    if len(sensor_panels) > 0:
        return sensor_panels[0].shape[:2]
    return 900, 1200


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='VTSensor 在线数据采集示例脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 自动检测并同时显示所有传感器
  python script/vts_collect_sensor_data.py

  # 指定力估计模型父目录
  python script/vts_collect_sensor_data.py --force-model-dir ./checkpoints

  # 指定一个传感器 SN
  python script/vts_collect_sensor_data.py --sn VTSensorI123456

  # 指定多个传感器 SN（逗号分隔）
  python script/vts_collect_sensor_data.py --sn VTSensorI123456,VTSensorI654321
        """)

    parser.add_argument('--sn', type=str, default=None,
                        help='传感器 SN；多个 SN 用英文逗号分隔；不填则显示全部设备')
    parser.add_argument('--force-model-dir', type=str, default='./checkpoints',
                        help='力估计模型权重的父目录路径，脚本会根据传感器 SN 自动加载 '
                             '{path}/{SN}/{SN}.onnx.enc（默认: ./checkpoints')

    return parser.parse_args()


def initialize_sensors(args):
    """发现设备并根据 SN 自动加载力估计模型。"""
    sensors = {}
    force_histories = {}

    print("=== 在线处理模式 ===")

    finder = VTSDeviceFinder()
    sns = finder.get_sns()

    if len(sns) == 0:
        print("错误: 未找到任何设备")
        print("提示: 请检查设备连接与驱动")
        return sensors, force_histories, []

    # 选择传感器：默认全部；可通过 --sn 指定一个或多个
    if args.sn:
        requested_sns = [item.strip() for item in args.sn.split(',') if item.strip()]
        invalid_sns = [item for item in requested_sns if item not in sns]
        if invalid_sns:
            print(f"错误: 以下传感器未找到: {', '.join(invalid_sns)}")
            print(f"可用的传感器: {', '.join(sns)}")
            return sensors, force_histories, []
        selected_sns = requested_sns
    else:
        selected_sns = list(sns)

    print(f"使用传感器: {', '.join(selected_sns)}")

    # 检查力估计模型父目录是否存在
    if not os.path.isdir(args.force_model_dir):
        print(f"错误: 力估计模型目录不存在: {args.force_model_dir}")
        print("提示: 请从百度网盘下载权重，目录结构应为:")
        print(f"       {args.force_model_dir}/{{SN}}/{{SN}}.onnx.enc")
        return sensors, force_histories, []

    print(f"力估计模型父目录: {args.force_model_dir}")
    print("正在根据传感器 SN 自动匹配并加载对应权重...")

    for sn in selected_sns:
        config = finder.get_device_by_sn(sn)
        # 传入模型父目录，SDK 会根据 SN 自动查找 {force_model_dir}/{SN}/{SN}.onnx.enc
        force_model_path = os.path.join(args.force_model_dir, sn, f"{sn}.onnx.enc")
        if not os.path.isfile(force_model_path):
            print(f"错误: 未找到力估计模型权重文件: {force_model_path}")
            print("提示: 请检查权重文件是否存在，或重新下载")
            continue
        sensor = VTSensor(config=config, force_model_path=force_model_path)
        sensor.calibrate()
        sensors[sn] = sensor
        force_histories[sn] = deque(maxlen=300)
        print(f"{sn} 初始化完成，传感器类型: {sensor.sensor_type.value}")

    if len(sensors) == 0:
        print("错误: 已发现传感器 SN，但没有任何传感器初始化成功。")
        print("提示: 请检查每个 SN 对应的力估计模型权重是否存在:")
        print(f"       {args.force_model_dir}/{{SN}}/{{SN}}.onnx.enc")

    return sensors, force_histories, selected_sns


def main():
    args = parse_args()

    sensors = {}
    force_histories = {}
    selected_sns = []

    try:
        sensors, force_histories, selected_sns = initialize_sensors(args)
        if len(selected_sns) == 0:
            return
        if len(sensors) == 0:
            return
    except VTSError as e:
        print(f"错误: {e}")
        print(f"建议: {e.suggestion}")
        return
    except Exception as e:
        print(f"未预期的错误: {e}")
        return

    try:
        print("\n=== 开始数据采集 ===")
        print("操作说明:")
        print("  - 按 'q' 或 ESC: 退出程序")
        print("  - 按 'e': 重新校准（所有传感器）")
        print("=" * 40 + "\n")

        last_stats_time = time.time()
        left_panel_width_ratio = 2
        window_name = "VTS Multi-Sensor View"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, 960, 960)
        print(f"启动时发现设备数: {len(sensors)} / {len(selected_sns)}")
        print(f"原始发现列表: {selected_sns}")

        while True:
            loop_t1 = time.monotonic()
            sensor_panels = []
            collected = {}

            for sn in list(sensors.keys()):
                sensor = sensors[sn]
                try:
                    data = sensor.collect_sensor_data(
                        VTSDataType.TIME_STAMP,
                        VTSDataType.WARPED_IMG,
                        VTSDataType.DIFF_IMG,
                        VTSDataType.DEPTH_MAP,
                        VTSDataType.MARKER_IMG,
                        VTSDataType.MARKER_ORIGIN_VECTOR,
                        VTSDataType.MARKER_CURRENT_VECTOR,
                        VTSDataType.MARKER_OFFSET_VECTOR,
                        VTSDataType.XYZ_VECTOR,
                        VTSDataType.FORCE6D_VECTOR,
                    )

                    collected[sn] = data
                    panel = build_sensor_panel(data, force_histories[sn], left_panel_width_ratio, sn)
                    sensor_panels.append(panel)
                except VTSError as e:
                    print(f"{sn} 采集失败: {e}, suggestion: {e.suggestion}")
                    h, w = infer_panel_size(sensor_panels)
                    sensor_panels.append(
                        render_status_panel(
                            f"{sn} 采集失败",
                            [f"{e}", f"建议: {e.suggestion}", "程序会继续重试这个传感器"],
                            h,
                            w,
                        )
                    )

            if len(sensor_panels) > 0:
                combined = compose_adaptive_grid(sensor_panels)
                cv2.imshow(window_name, combined)

            t2 = time.time()
            if t2 - last_stats_time >= 1.0:
                last_stats_time = t2
                loop_elapsed = max(1e-6, time.monotonic() - loop_t1)
                print(
                    f"整轮耗时: {loop_elapsed * 1000:.1f} ms, 整轮fps: {1 / loop_elapsed:.1f}, "
                    f"当前设备数: {len(sensors)}, 已成功采集: {len(collected)}"
                )

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord("q"):
                break
            elif key == ord("e"):
                print("重新校准中... (全部传感器)")
                for sn, sensor in sensors.items():
                    try:
                        sensor.calibrate()
                        print(f"{sn} 校准完成")
                    except VTSError as e:
                        print(f"{sn} 校准失败: {e}, suggestion: {e.suggestion}")

    except KeyboardInterrupt:
        print("\n接收到中断信号 (Ctrl+C)，正在安全退出...")
    finally:
        # 清理资源
        for sensor in sensors.values():
            sensor.release()
        cv2.destroyAllWindows()
        print("\n程序已退出")


if __name__ == "__main__":
    main()
