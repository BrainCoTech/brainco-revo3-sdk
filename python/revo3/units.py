"""Demonstrate the public Revo3 unit conversion utilities offline."""

from bc_revo3_sdk import main_mod as sdk


def main() -> None:
    positions_deg = [0.0, 45.0, 90.0]
    velocities_rpm = [0.0, 30.0, 60.0]
    currents_ma = [0.0, 500.0, 1000.0]

    positions_rad = sdk.deg_to_rad(positions_deg)
    velocities_rad_s = sdk.rpm_to_rad_s(velocities_rpm)
    currents_a = sdk.ma_to_a(currents_ma)

    print(f"degree -> rad: {positions_deg} -> {positions_rad}")
    print(f"rad -> degree: {positions_rad} -> {sdk.rad_to_deg(positions_rad)}")
    print(f"rpm -> rad/s: {velocities_rpm} -> {velocities_rad_s}")
    print(f"rad/s -> rpm: {velocities_rad_s} -> {sdk.rad_s_to_rpm(velocities_rad_s)}")
    print(f"mA -> A: {currents_ma} -> {currents_a}")
    print(f"A -> mA: {currents_a} -> {sdk.a_to_ma(currents_a)}")


if __name__ == "__main__":
    main()
