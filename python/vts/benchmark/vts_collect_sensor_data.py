#!/usr/bin/env python3
# coding=utf-8
import cv2
import time
from pyvitaisdk import VTSensor, VTSDeviceFinder, VTSDataType, VTSError


def read_image():
    vtsensor = None
    model_dir = f"./checkpoints/BC_20260529"
    try:
        finder = VTSDeviceFinder()
        if len(finder.get_sns()) == 0:
            print("No device found.")
            return
        sn = finder.get_sns()[0]
        print(f"sn: {sn}")
        config = finder.get_device_by_sn(sn)
        vtsensor = VTSensor(config=config, force_model_path=f"{model_dir}/{sn}/{sn}.onnx.enc")
        vtsensor.calibrate()
    except VTSError as e:
        print(f"Error initializing: {e}, suggestion: {e.suggestion}")
        if vtsensor is not None:
            vtsensor.release()
        return

    while True:
        try:
            t1 = time.time()
            data = vtsensor.collect_sensor_data(
                VTSDataType.WARPED_IMG,
                VTSDataType.DEPTH_MAP,
                VTSDataType.FORCE6D_VECTOR,
            )
            t2 = time.time()
            elapsed = t2 - t1
            print(
                f"Collect sensor data elapsed: {elapsed * 1000:.3f} ms, "
                f"fps: {1.0 / elapsed:.2f} FPS"
            )
        except VTSError as e:
            print(f"Error collecting sensor data: {e}, suggestion: {e.suggestion}")
            break

    vtsensor.release()


if __name__ == "__main__":
    read_image()
