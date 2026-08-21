"""List trusted USB RS485 serial ports and configure custom USB VID/PID allowlist."""

from bc_revo3_sdk import main_mod as sdk


def main() -> None:
    # Extend the trusted USB-to-RS485 adapter list for this process.
    sdk.configure_usb_vid_pid_allowlist(
        custom_ids=[(0x1234, 0x5678)],
        include_defaults=True,
    )

    # List trusted USB-to-RS485 ports currently available to the SDK.
    ports = sdk.list_available_ports()
    print(f"Discovered {len(ports)} trusted 485 serial port(s):")
    for info in ports:
        print(
            f"  - Port: {info.port_name}, "
            f"VID: {hex(info.vid) if info.vid else 'None'}, "
            f"PID: {hex(info.pid) if info.pid else 'None'}, "
            f"SN: {info.serial_number or 'None'}, "
            f"Manufacturer: {info.manufacturer or 'None'}"
        )

    # Manager exposes the same filtered port list.
    manager = sdk.Manager()
    manager_ports = manager.list_ports()
    print(f"Manager ports count: {len(manager_ports)}")


if __name__ == "__main__":
    main()
