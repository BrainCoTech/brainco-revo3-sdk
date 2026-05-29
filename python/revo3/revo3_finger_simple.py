import asyncio
import logging
from revo3_utils import open_modbus_revo3, libstark

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("revo3_finger_simple")

async def main():
    # 1. 自动搜索机械手并开启 Modbus 连接 (默认 5Mbps)
    logger.info("正在搜索并连接 Revo3 机械手...")
    client, slave_id = await open_modbus_revo3()
    logger.info(f"成功连接！设备 Slave ID: {slave_id}")

    try:
        fmt_angles = lambda angles: "[" + ", ".join(f"{x:.2f}°" for x in angles) + "]"

        # 2. 读取大拇指关节初始角度 (电机 ID: 16~20)
        status = await client.revo3_get_motor_status_data(slave_id)
        init_thumb = status.positions[16:21]
        logger.info(f"大拇指初始角度 [Rot, MCP, IP, Abd, Flex]: {fmt_angles(init_thumb)}")

        # 3. 设定运动目标 (大拇指旋转关节: 30° [安全区内]，其他保持为 0)
        targets = [30.0, 0.0, 0.0, 0.0, 0.0]
        duration = 2.0  # 2秒完成
        dt = 0.01       # 100Hz 插补控制

        # 4. 执行阻塞式大拇指轨迹控制 (等待运动结束)
        logger.info(f"开始大拇指弯曲轨迹运动 -> 目标: {targets} (耗时 {duration}s)...")
        await client.revo3_move_thumb_wait(slave_id, targets, duration, dt)
        
        # 5. 校验运动结果
        await asyncio.sleep(0.1)
        status = await client.revo3_get_motor_status_data(slave_id)
        current_thumb = status.positions[16:21]
        logger.info(f"弯曲后当前大拇指角度: {fmt_angles(current_thumb)}")

        # 6. 回归零位轨迹运动
        logger.info("开始大拇指复位轨迹运动 -> 目标: [0.0, 0.0, 0.0, 0.0, 0.0]...")
        await client.revo3_move_thumb_wait(slave_id, [0.0, 0.0, 0.0, 0.0, 0.0], duration, dt)

        # 7. 校验复位结果
        await asyncio.sleep(0.1)
        status = await client.revo3_get_motor_status_data(slave_id)
        logger.info(f"复位后当前大拇指角度: {fmt_angles(status.positions[16:21])}")

        # 8. 设定四指运动目标：控制食指 (finger_id=1, 对应 [Abd_MCP, MCP, PIP, DIP])
        # 让食指 MCP 大关节和 PIP 中间关节弯曲 45°，其余保持为 0
        finger_id = 1
        finger_targets = [0.0, 45.0, 45.0, 0.0]
        
        logger.info(f"\n开始食指 (F{finger_id}) 弯曲轨迹运动 -> 目标: {finger_targets}...")
        await client.revo3_move_finger_wait(slave_id, finger_id, finger_targets, duration, dt)
        
        # 9. 校验食指运动结果
        await asyncio.sleep(0.1)
        status = await client.revo3_get_motor_status_data(slave_id)
        current_finger = status.positions[12:16]
        logger.info(f"弯曲后当前食指角度 [Abd, MCP, PIP, DIP]: {fmt_angles(current_finger)}")

        # 10. 食指复位运动
        logger.info(f"开始食指 (F{finger_id}) 复位轨迹运动 -> 目标: [0.0, 0.0, 0.0, 0.0]...")
        await client.revo3_move_finger_wait(slave_id, finger_id, [0.0, 0.0, 0.0, 0.0], duration, dt)
        
        # 11. 校验复位结果
        await asyncio.sleep(0.1)
        status = await client.revo3_get_motor_status_data(slave_id)
        logger.info(f"复位后当前食指角度: {fmt_angles(status.positions[12:16])}")

    finally:
        # 关闭连接
        libstark.modbus_close(client)
        logger.info("Modbus 连接已关闭。")

if __name__ == "__main__":
    asyncio.run(main())
