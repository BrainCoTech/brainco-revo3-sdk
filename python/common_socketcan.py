"""
Common SocketCAN utilities for Linux

Supports Revo3 CANFD mode.
"""

import os
import socket
import struct
import time
from typing import Optional, Tuple

from common_imports import logger

# CAN constants
CAN_EFF_FLAG = 0x80000000
CAN_ERR_FLAG = 0x20000000
CAN_EFF_MASK = 0x1FFFFFFF
CAN_RAW = 1
CAN_RAW_FD_FRAMES = 5

# Frame sizes and formats
CANFD_MTU = 72
CANFD_FRAME_FMT = "=IBBBx64s"

_sock = None


def _get_iface() -> str:
    return os.getenv("STARK_SOCKETCAN_IFACE", "can0")


def socketcan_open(iface: Optional[str] = None, canfd: bool = True) -> None:
    """
    Open SocketCAN interface
    
    Args:
        iface: CAN interface name (default: from STARK_SOCKETCAN_IFACE env or "can0")
        canfd: Kept for compatibility; Revo3 SocketCAN always uses CANFD.
    """
    global _sock
    if _sock is not None:
        return

    if iface is None:
        iface = _get_iface()

    sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, CAN_RAW)
    sock.setsockopt(socket.SOL_CAN_RAW, CAN_RAW_FD_FRAMES, 1)
    sock.bind((iface,))
    sock.settimeout(0.5)
    _sock = sock
    logger.info(f"SocketCAN CANFD opened on {iface}")


def socketcan_close() -> None:
    """Close SocketCAN interface"""
    global _sock
    if _sock is None:
        return
    _sock.close()
    _sock = None
    logger.info("SocketCAN closed")


def socketcan_send_message(can_id: int, data: bytes) -> bool:
    """Send CANFD message"""
    if _sock is None:
        logger.error("SocketCAN not initialized")
        return False

    try:
        payload = data[:64]
        can_id_flag = (can_id & CAN_EFF_MASK) | CAN_EFF_FLAG
        frame = struct.pack(
            CANFD_FRAME_FMT,
            can_id_flag,
            len(payload),
            1,  # CANFD_BRS
            0,
            payload.ljust(64, b"\x00"),
        )
        _sock.send(frame)
        return True
    except OSError as exc:
        logger.error(f"SocketCAN send failed: {exc}")
        return False


def socketcan_receive_message(
    quick_retries: int = 5, dely_retries: int = 2
) -> Optional[Tuple[int, bytes]]:
    """Receive single CANFD message."""
    if _sock is None:
        logger.error("SocketCAN not initialized")
        return None

    for _ in range(quick_retries):
        msg = _socketcan_read_message()
        if msg is not None:
            return msg
        time.sleep(0.01)

    logger.warning("SocketCAN quick receive timeout")

    for _ in range(dely_retries):
        time.sleep(2.0)
        msg = _socketcan_read_message()
        if msg is not None:
            return msg

    if dely_retries > 0:
        logger.error("SocketCAN slow receive timeout")
    return None


def socketcan_receive_filtered(
    expected_can_id: int, expected_frames: int = 1, max_retries: int = 10
) -> Optional[Tuple[int, bytes, int]]:
    """
    Receive CANFD message filtered by expected CAN ID.
    
    Args:
        expected_can_id: Expected CAN ID to filter by
        expected_frames: Expected frame count (hint from SDK)
        max_retries: Maximum retry attempts
        
    Returns:
        (can_id, data, frame_count) tuple or None if timeout
    """
    if _sock is None:
        logger.error("SocketCAN not initialized")
        return None
    
    # Check if this is DFU mode (expected_can_id == 0)
    is_dfu_mode = (expected_can_id == 0)
    
    # Determine retry strategy (aligned with SDK):
    # - DFU mode: 200 attempts (for CRC verification)
    # - Single frame: 2 attempts
    if is_dfu_mode:
        max_retries = 200
    else:
        max_retries = max(max_retries, 2)
    
    all_data = []
    frame_count = 0
    
    for attempt in range(max_retries):
        wait_ms = 0.002 if attempt < 5 else 0.005
        time.sleep(wait_ms)
        
        try:
            msg = _socketcan_read_message()
            if msg is None:
                continue
            
            frame_id, frame_data = msg
            can_dlc = len(frame_data)
            
            # Check if this frame matches expected CAN ID
            if frame_id != expected_can_id:
                logger.debug(f"Skipping frame with different CAN ID: 0x{frame_id:x} (expected 0x{expected_can_id:x})")
                continue
            
            frame_bytes = list(frame_data)
            
            all_data.extend(frame_bytes)
            frame_count += 1
            
            # For single frame request, return immediately
            if expected_frames <= 1:
                return (expected_can_id, bytes(all_data), frame_count)
            
            # Check if we have enough frames (for non-protocol multi-frame)
            if expected_frames > 1 and frame_count >= expected_frames:
                return (expected_can_id, bytes(all_data), frame_count)
                
        except Exception as e:
            logger.error(f"SocketCAN receive filtered exception: {e}")
    
    # Timeout - return whatever we have
    if all_data:
        return (expected_can_id, bytes(all_data), frame_count)
    
    return None


def _socketcan_read_message() -> Optional[Tuple[int, bytes]]:
    """Read single CANFD frame from socket"""
    if _sock is None:
        return None
    try:
        data = _sock.recv(CANFD_MTU)
        if len(data) == CANFD_MTU:
            can_id, length, _flags, _rsvd, payload = struct.unpack(CANFD_FRAME_FMT, data)
            if can_id & CAN_ERR_FLAG:
                return None
            can_id = can_id & CAN_EFF_MASK
            return can_id, payload[:length]
        return None
    except socket.timeout:
        return None
    except OSError as exc:
        logger.error(f"SocketCAN recv failed: {exc}")
        return None


def socketcan_receive_canfd_filtered(
    expected_can_id: int, expected_frames: int = 1, max_retries: int = 2
) -> Optional[Tuple[int, bytes, int]]:
    """
    Receive CANFD message filtered by slave_id and master_id.
    
    CANFD CAN ID format: (slave_id << 16) | (master_id << 8) | payload_len
    
    This function matches the Rust implementation for CANFD receive:
    - Extract expected_slave_id and expected_master_id from expected_can_id
    - Match received frames by slave_id and master_id (not exact CAN ID match)
    
    Args:
        expected_can_id: Expected CAN ID containing slave_id and master_id
        expected_frames: Expected frame count (hint from SDK)
        max_retries: Maximum retry attempts (default: 2, aligned with SDK)
        
    Returns:
        (can_id, data, frame_count) tuple or None if timeout
    """
    if _sock is None:
        logger.error("SocketCAN not initialized")
        return None
    
    # CANFD CAN ID format: (slave_id << 16) | (master_id << 8) | payload_len
    expected_slave_id = (expected_can_id >> 16) & 0xFF
    expected_master_id = (expected_can_id >> 8) & 0xFF
    
    logger.debug(f"CANFD RX: waiting, expected_can_id=0x{expected_can_id:08X}, "
                 f"slave=0x{expected_slave_id:02X}, master=0x{expected_master_id:02X}")
    
    for attempt in range(max_retries):
        wait_ms = 0.002 if attempt < 5 else 0.005
        time.sleep(wait_ms)
        
        try:
            msg = _socketcan_read_message()
            if msg is None:
                continue
            
            can_id, data = msg
            
            # Match slave_id and master_id from CAN ID
            resp_slave_id = (can_id >> 16) & 0xFF
            resp_master_id = (can_id >> 8) & 0xFF
            
            logger.debug(f"CANFD RX: received - can_id=0x{can_id:08X}, "
                         f"slave=0x{resp_slave_id:02X}, master=0x{resp_master_id:02X}")
            
            if resp_slave_id == expected_slave_id and resp_master_id == expected_master_id:
                return (can_id, data, 1)
                
        except Exception as e:
            logger.error(f"SocketCAN CANFD receive exception: {e}")
    
    logger.debug(f"SocketCAN CANFD receive timeout after {max_retries} attempts")
    return None
