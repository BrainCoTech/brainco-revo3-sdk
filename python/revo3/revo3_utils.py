"""
Revo3 Dexterous Hand Utility Functions Module

This module provides common utility functions for Revo3 (21 DoF) dexterous hand, including:
- Automatic detection and establishment of Modbus connection
- Device information retrieval and verification
"""

import sys
import os
from enum import IntEnum

# Import from common_imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common_imports import logger, libstark, int_to_baudrate, modbus_open

libstark.init_logging()

class Revo3Finger(IntEnum):
    INDEX = 1
    MIDDLE = 2
    RING = 3
    PINKY = 4

__all__ = [
    'logger', 'libstark', 'int_to_baudrate', 'modbus_open',
    'open_modbus_revo3', 'open_revo3',
    'REVO3_MOTOR_COUNT', 'REVO3_FINGER_COUNT', 'FINGER_NAMES',
    'Revo3Finger',
]

REVO3_MOTOR_COUNT = 21
REVO3_FINGER_COUNT = 5
FINGER_NAMES = ["Thumb", "Index", "Middle", "Ring", "Pinky"]


async def open_modbus_revo3(port_name=None, baudrate=5000000, slave_id=None):
    """
    Open Modbus connection for Revo3 dexterous hand

    Revo3 uses 5Mbps baudrate by default.

    Args:
        port_name (str, optional): Serial port name, None means auto-detect.
        baudrate (int, optional): Baud rate, default 5000000 (5Mbps).
        slave_id (int, optional): Device slave ID, None means auto-detect (probes 126/127).

    Returns:
        tuple: (client, slave_id) - Modbus client instance and device slave ID
    """
    try:
        if port_name is None or slave_id is None:
            # Auto-detect (if port is specified, it will scan that specific port; if slave_id is None, it probes both 126/127)
            (protocol, detected_port_name, detected_baudrate, detected_slave_id) = (
                await libstark.revo3_auto_detect_modbus(port_name)
            )
            if port_name is None:
                port_name = detected_port_name
                baudrate = detected_baudrate
            slave_id = detected_slave_id
            logger.info(f"Auto-detected: port={port_name}, baudrate={baudrate}, slave_id={slave_id}")
    except Exception as e:
        logger.error(f"Auto-detect failed: {e}")
        if port_name is None or slave_id is None:
            sys.exit(1)

    if slave_id is None:
        slave_id = 126  # Default fallback ID

    # Establish Modbus connection
    client: libstark.DeviceContext = await modbus_open(port_name, baudrate)
    await client.set_hardware_type(slave_id, libstark.StarkHardwareType.Revo3Ultra)
    logger.info(
        f"Preset hardware type to {libstark.StarkHardwareType.Revo3Ultra} for Revo3 Modbus open"
    )

    return (client, slave_id)


async def open_revo3(port_name=None, baudrate=5000000, slave_id=None):
    """
    Open connection for Revo3 dexterous hand, supporting both Modbus and CANFD.

    Args:
        port_name (str, optional): Port name, None means auto-detect.
        baudrate (int, optional): Baud rate for Modbus fallback, default 5000000 (5Mbps).
        slave_id (int, optional): Device slave ID for Modbus fallback, None means auto-detect.

    Returns:
        tuple: (client, slave_id) - DeviceContext client instance and device slave ID
    """
    try:
        if port_name is None:
            # Use general auto_detect to scan for both Modbus and CANFD devices
            devices = await libstark.revo3_auto_detect(slave_id=slave_id)
            if not devices:
                logger.error("No Revo3 devices found during auto-detect")
                sys.exit(1)
            device = devices[0]
            logger.info(f"Auto-detected: protocol={device.protocol_type}, port={device.port_name}, slave_id={device.slave_id}")
            
            # Use init_from_detected to initialize the device context
            client = await libstark.init_from_detected(device)
            slave_id = device.slave_id
            
            # Sync actual device info to load joint limits
            try:
                await client.revo3_get_device_info(slave_id)
            except Exception as e:
                logger.warning(f"Failed to query device info: {e}. Falling back to preset hardware type.")
                await client.set_hardware_type(slave_id, libstark.StarkHardwareType.Revo3Ultra)
            
            return (client, slave_id)
    except Exception as e:
        logger.error(f"Auto-detect / Init failed: {e}")
        if port_name is None:
            sys.exit(1)

    # If port_name is specified, try detecting protocol on that specific port first
    try:
        devices = await libstark.revo3_auto_detect(port=port_name, slave_id=slave_id)
        if devices:
            device = devices[0]
            client = await libstark.init_from_detected(device)
            slave_id = device.slave_id
            try:
                await client.revo3_get_device_info(slave_id)
            except Exception:
                await client.set_hardware_type(slave_id, libstark.StarkHardwareType.Revo3Ultra)
            return (client, slave_id)
    except Exception as e:
        logger.warning(f"Auto-detect on specified port {port_name} failed: {e}. Falling back to default Modbus open.")

    if slave_id is None:
        slave_id = 126  # Default fallback ID

    # Fallback to direct Modbus open
    client: libstark.DeviceContext = await modbus_open(port_name, baudrate)
    await client.set_hardware_type(slave_id, libstark.StarkHardwareType.Revo3Ultra)
    logger.info(
        f"Preset hardware type to {libstark.StarkHardwareType.Revo3Ultra} for Revo3 open"
    )

    return (client, slave_id)
