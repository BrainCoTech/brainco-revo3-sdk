import cv2
import time
import argparse


def main():
    parser = argparse.ArgumentParser(description="OpenCV USB摄像头读取")
    parser.add_argument('--device', type=int, default=0, help='摄像头设备ID，默认0')
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.device)
    if not cap.isOpened():
        print(f"无法打开摄像头 device {args.device}")
        return

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
    cap.set(cv2.CAP_PROP_FPS, 120)
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    cap_fps = cap.get(cv2.CAP_PROP_FPS)
    print("按 q 或 ESC 退出")
    while True:
        t1 = time.time()
        ret, frame = cap.read()
        t2 = time.time()
        elapsed = t2 - t1
        if elapsed < 1 / 125:
            time.sleep((1 / 125) - elapsed)
        t3 = time.time()
        fps = 1.0 / (t3 - t1)
        print(f"实时帧率: {fps:.2f} FPS, {int(width)}x{int(height)} @ {cap_fps} FPS")
        if not ret:
            print("无法读取视频帧")
            break

        cv2.imshow(f"USB Camera {args.device}", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q') or key == 27:
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()