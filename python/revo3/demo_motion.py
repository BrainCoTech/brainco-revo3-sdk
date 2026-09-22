"""Shared offline choreography and bounded Revo3 2.x demo execution."""

import argparse
import asyncio
import json
import math
from pathlib import Path
import sys
import time

JOINT_COUNT = 21
FINGERS = {"pinky": 0, "ring": 4, "middle": 8, "index": 12}
FLEX_JOINTS = tuple(base + offset for base in FINGERS.values() for offset in (1, 2, 3))
MOTOR_FAULT_MASK = 0x0037


def pose(flex=(0.0, 0.0, 0.0), spread=False, thumb=None):
    values = [0.0] * JOINT_COUNT
    for base in FINGERS.values():
        values[base + 1:base + 4] = flex
    if spread:
        for base, angle in zip(FINGERS.values(), (-12.0, -4.0, 4.0, 12.0)):
            values[base] = angle
    values[16:21] = thumb or [0.0] * 5
    return values


def default_profile(kind, side):
    """Create candidate poses, not calibrated fingertip contact coordinates."""
    opened = pose()
    steps = []

    def add(name, positions, duration=0.8, hold=0.08):
        steps.append(dict(name=name, positions_deg=positions, duration=duration, hold=hold))

    add("open", opened)
    if kind == "opposition":
        for name in ("index", "middle", "ring", "pinky"):
            # Candidate approach poses; fingertip contact remains uncalibrated.
            thumb = [73.0, 45.0, 40.0, 10.0, 15.0] if name == "index" else [70.0, 40.0, 35.0, 10.0, 15.0]
            target = pose(thumb=thumb)
            base = FINGERS[name]
            target[base + 1:base + 4] = [75.0, 65.0, 50.0] if name == "index" else [70.0, 60.0, 45.0]
            aligned = pose(thumb=[thumb[0], 0.0, 0.0, thumb[3], thumb[4]])
            add("align_" + name, aligned, 0.6, 0.05)
            near = [a + 0.9 * (b - a) for a, b in zip(aligned, target)]
            add("approach_" + name, near, 1.2, 0.0)
            steps[-1]["finger_delay"] = 0.15
            add("oppose_" + name, target, 0.35, 0.5)
            add("release_" + name, opened, 0.8, 0.05)
    elif kind == "finger":
        for name, base in FINGERS.items():
            target = pose()
            target[base + 1:base + 4] = [30.0, 35.0, 20.0]
            add("flex_" + name, target)
            add("release_" + name, opened)
        add("claw", pose((15.0, 55.0, 45.0)))
        add("open", opened)
        add("grip", pose((60.0, 60.0, 45.0), thumb=[20.0, 15.0, 10.0, 0.0, 10.0]))
        add("open", opened)
        add("spread", pose(spread=True))
        add("close_spread", opened)
        for name, base in FINGERS.items():
            for cycle, angle in enumerate((-12.0, 12.0, -12.0, 12.0)):
                target = pose()
                target[base] = max(-7.0, angle) if base == 12 else min(7.0, angle) if base == 0 else angle
                add(f"sway_{name}_{cycle}", target, 0.35, 0.0)
            add("release_" + name, opened, 0.35, 0.0)
        for cycle, angle in enumerate((-12.0, 12.0, -12.0, 12.0)):
            target = pose()
            for base in FINGERS.values():
                target[base] = max(-7.0, angle) if base == 12 else min(7.0, angle) if base == 0 else angle
            add(f"sway_all_{cycle}", target, 0.35, 0.0)
    elif kind == "dance":
        for cycle in range(2):
            add(f"grip_{cycle}", pose((60.0, 60.0, 45.0)), 0.6, 0.0)
            add(f"claw_{cycle}", pose((15.0, 55.0, 45.0)), 0.6, 0.0)
        add("wave_entry", opened, 0.6, 0.0)
        add("continuous_wave", opened, 6.5, 0.0)
        steps[-1]["motion"] = "wave"
        for cycle in range(2):
            for direction in (-1, 1):
                target = pose()
                for base, angle in zip(FINGERS.values(), (7.0, 12.0, 12.0, 7.0)):
                    target[base] = direction * angle
                add(f"sway_{cycle}_{direction}", target, 0.4, 0.0)
        target = pose(thumb=[45.0, 15.0, 10.0, 0.0, 15.0])
        target[13:16] = [40.0, 35.0, 25.0]
        add("opposition", target, 1.2, 0.3)
        steps[-1]["finger_delay"] = 0.2
        victory = pose((40.0, 40.0, 25.0))
        victory[8:16] = [4.0, 0.0, 0.0, 0.0, 12.0, 0.0, 0.0, 0.0]
        add("victory", victory, 0.8, 1.0)
    else:
        raise ValueError("Unknown choreography")
    add("open", opened)
    return dict(schema_version=1, kind=kind, side=side, calibrated=False,
                streaming=True, steps=steps)


def number(value, name, minimum=0.0, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < minimum or (positive and value == minimum):
        raise ValueError(f"Invalid {name}: {value}")
    return float(value)


def validate_profile(profile, kind, side):
    if profile.get("schema_version") != 1 or profile.get("kind") != kind:
        raise ValueError("Profile schema or demo kind mismatch")
    if profile.get("side") != side:
        raise ValueError("Profile hand side mismatch")
    if not isinstance(profile.get("calibrated"), bool):
        raise ValueError("Profile calibrated must be a boolean")
    steps = profile.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("Profile needs nonempty steps")
    if not isinstance(profile.get("streaming", False), bool):
        raise ValueError("streaming must be a boolean")
    previous = None
    for step in steps:
        if not isinstance(step.get("name"), str) or not step["name"]:
            raise ValueError("Each step needs a name")
        positions = step.get("positions_deg")
        if not isinstance(positions, list) or len(positions) != JOINT_COUNT:
            raise ValueError("Each pose requires 21 logical joint angles")
        for value in positions:
            number(value, "position", -360.0)
        number(step.get("duration"), "duration", positive=True)
        number(step.get("hold"), "hold")
        if step.get("motion", "pose") not in ("pose", "wave"):
            raise ValueError("Unknown step motion")
        delay = number(step.get("finger_delay", 0.0), "finger delay")
        if delay >= step["duration"]:
            raise ValueError("Finger delay must be shorter than the step")
        if step.get("motion") == "wave" and positions != pose():
            raise ValueError("Wave endpoints must be the open pose")
        if (step.get("motion") == "wave" or delay) and not profile.get("streaming"):
            raise ValueError("Wave and delayed steps require streaming")
        if step.get("motion") == "wave" and previous != pose():
            raise ValueError("Wave requires a preceding open pose")
        previous = positions
    return profile


def check_positions(positions, config, tolerance=0.0):
    if len(positions) != JOINT_COUNT:
        raise ValueError("Expected 21 joint positions")
    for joint, position in enumerate(positions):
        lo = config.joint_min_position_deg[joint]
        hi = config.joint_max_position_deg[joint]
        if not all(math.isfinite(v) for v in (lo, hi, position)) or not lo < hi:
            raise ValueError(f"Invalid position or limits for J{joint}")
        if not lo - tolerance <= position <= hi + tolerance:
            raise ValueError(f"J{joint}: {position:g} deg outside [{lo:g}, {hi:g}]")


def speed_limit(config, joint, direction):
    lo, hi = config.joint_min_speed_rpm[joint], config.joint_max_speed_rpm[joint]
    if not all(math.isfinite(v) for v in (lo, hi)) or lo > hi:
        raise ValueError(f"Invalid speed envelope for J{joint}")
    limit = abs(lo) if direction < 0 and lo < 0 else hi
    if limit <= 0:
        raise ValueError(f"Invalid speed limit for J{joint}")
    return limit


async def check_health(hand, sdk):
    health = await hand.health.snapshot()
    faults = {joint: f"0x{code:04X}" for joint, code in enumerate(health.motor_fault_codes)
              if code & MOTOR_FAULT_MASK}
    if (faults or health.faulted_motor_count or health.system_state or health.error_code
            or health.safety_state in (sdk.SafetyState.Faulted, sdk.SafetyState.RecoveryRequired)):
        raise RuntimeError(
            f"Motion health check failed: safety={health.safety_state}, motor_faults={faults}, "
            f"faulted_motor_count={health.faulted_motor_count}, "
            f"system_state={health.system_state}, error_code={health.error_code}"
        )


def segment_duration(start, target, requested, config, tolerance=0.0):
    check_positions(start, config, tolerance)
    check_positions(target, config)
    duration = requested
    for joint, (a, b) in enumerate(zip(start, target)):
        if a != b:
            duration = max(duration, 1.875 * abs(b - a) / (6.0 * speed_limit(config, joint, b - a)))
    return duration


async def move(hand, target, duration, args, config, sdk):
    await check_health(hand, sdk)
    current = list((await hand.state.snapshot()).positions_deg)
    duration = segment_duration(current, target, duration, config, args.feedback_tolerance_deg)
    operation = await hand.motion.move_to(target, duration=duration, kp=args.kp, kd=args.kd)
    try:
        state = await operation.wait(timeout=duration + 3.0)
        if state != sdk.OperationState.Succeeded:
            raise RuntimeError(f"Motion ended with {state}: {operation.error}")
        await asyncio.sleep(0.25)
        await check_health(hand, sdk)
        actual = list((await hand.state.snapshot()).positions_deg)
        check_positions(actual, config, args.feedback_tolerance_deg)
        errors = [abs(observed - expected) for observed, expected in zip(actual, target)]
        if max(errors) > 5.0:
            raise RuntimeError(f"Endpoint tracking error: J{errors.index(max(errors))} differs by {max(errors):.2f} deg (limit 5 deg)")
    except BaseException:
        operation.cancel()
        raise


class DampedFilter:
    """Exact critically damped update for a constant target over one sample."""

    def __init__(self, positions, omega):
        self.positions = list(positions)
        self.velocities = [0.0] * len(positions)
        self.omega = omega

    def update(self, targets, dt):
        decay = math.exp(-self.omega * dt)
        for index, target in enumerate(targets):
            error = self.positions[index] - target
            coefficient = self.velocities[index] + self.omega * error
            self.positions[index] = target + (error + coefficient * dt) * decay
            self.velocities[index] = (self.velocities[index] - self.omega * coefficient * dt) * decay
        return self.positions.copy(), [v / 6.0 for v in self.velocities]


def sine_sample(elapsed, minimum, maximum, frequency):
    amplitude = (maximum - minimum) / 2.0
    phase = 2.0 * math.pi * frequency * elapsed
    return minimum + amplitude * (1.0 - math.cos(phase)), amplitude * 2.0 * math.pi * frequency * math.sin(phase) / 6.0


def classic_targets(initial, config, args):
    start = initial.copy()
    end = initial.copy()
    for joint in args.joints:
        start[joint], end[joint] = args.minimum, args.maximum
        peak = (args.maximum - args.minimum) * math.pi * args.frequency / 6.0
        if peak > min(speed_limit(config, joint, -1), speed_limit(config, joint, 1)):
            raise ValueError(f"Sine peak speed exceeds J{joint} limit; reduce frequency or amplitude")
    check_positions(start, config)
    check_positions(end, config)
    return start


async def classic(hand, initial, config, args, sdk):
    start = classic_targets(initial, config, args)
    await move(hand, start, 2.0 / args.tempo, args, config, sdk)
    session = hand.motion.open_servo(command_timeout_ms=args.command_timeout_ms)
    zeros = [0.0] * JOINT_COUNT
    filter_state = DampedFilter(start, args.omega)
    began = previous = time.monotonic()
    total = args.cycles / args.frequency
    period = 1.0 / args.rate
    try:
        while True:
            now = time.monotonic()
            elapsed = min(now - began, total)
            positions = start.copy()
            velocities = zeros.copy()
            angle, velocity = sine_sample(elapsed, args.minimum, args.maximum, args.frequency)
            for joint in args.joints:
                positions[joint], velocities[joint] = angle, velocity
            if args.omega > 0:
                positions, velocities = filter_state.update(positions, now - previous)
            check_positions(positions, config)
            for joint, velocity in enumerate(velocities):
                if abs(velocity) > speed_limit(config, joint, velocity):
                    raise ValueError(f"Filtered velocity exceeds J{joint} limit")
            await session.send_mit(positions, velocities, [args.kp] * JOINT_COUNT, [args.kd] * JOINT_COUNT, zeros)
            previous = now
            if elapsed >= total:
                break
            # Skip missed ticks; never queue a burst of stale samples.
            next_tick = (math.floor((time.monotonic() - began) / period) + 1) * period
            await asyncio.sleep(max(0.0, began + next_tick - time.monotonic()))
    finally:
        session.close()


async def stream_health(hand, sdk, excluded):
    if not excluded:
        return await check_health(hand, sdk)
    health = await hand.health.snapshot()
    # Stalled is a product status and does not block continued control.
    faults = {j: code for j, code in enumerate(health.motor_fault_codes)
              if code & MOTOR_FAULT_MASK and j not in excluded}
    if (health.system_state or health.error_code or faults or
            health.safety_state in (sdk.SafetyState.Faulted, sdk.SafetyState.RecoveryRequired)
            or health.faulted_motor_count):
        raise RuntimeError(f"Motion health check failed: faults={faults}, system={health.system_state}/{health.error_code}")


def smooth_sample(start, target, elapsed, duration, finger_delay=0.0):
    positions, velocities = [], []
    for j, (a, b) in enumerate(zip(start, target)):
        delay = finger_delay if j in FLEX_JOINTS else 0.0
        span = duration - delay
        r = min(1.0, max(0.0, (elapsed - delay) / span))
        blend = 10*r**3 - 15*r**4 + 6*r**5
        derivative = (30*r**2 - 60*r**3 + 30*r**4) / span
        positions.append(a + (b-a)*blend)
        velocities.append((b-a)*derivative/6.0)
    return positions, velocities


def wave_sample(elapsed, duration):
    """Three overlapping pulses per finger, with zero endpoint derivatives."""
    if elapsed <= 0.0 or elapsed >= duration:
        return pose(), [0.0]*JOINT_COUNT
    scale = duration / 6.5
    width, delay, period = 1.6*scale, 0.3*scale, 2.0*scale
    positions, velocities = pose(), [0.0]*JOINT_COUNT
    for index, name in enumerate(("index", "middle", "ring", "pinky")):
        value = rate = 0.0
        for cycle in range(3):
            u = (elapsed-index*delay-cycle*period)/width
            if 0.0 < u < 1.0:
                sine = math.sin(math.pi*u)
                value += sine**4
                rate += 4*math.pi/width*sine**3*math.cos(math.pi*u)
        for offset, amplitude in enumerate((60.0, 60.0, 45.0), 1):
            joint = FINGERS[name]+offset
            positions[joint] = amplitude*value
            velocities[joint] = amplitude*rate/6.0
    return positions, velocities


async def stream_profile(hand, initial, config, args, sdk, profile, excluded):
    session = hand.motion.open_servo(command_timeout_ms=500)
    kp = [0.0 if j in excluded else args.kp for j in range(JOINT_COUNT)]
    kd = [0.0 if j in excluded else args.kd for j in range(JOINT_COUNT)]
    current = initial.copy()
    last_health = time.monotonic()
    try:
        steps = profile["steps"] * args.repeat + [dict(name="return_initial", positions_deg=initial, duration=1.0, hold=0.0)]
        for step in steps:
            print(f"Step: {step['name']}; excluded={sorted(excluded)}", flush=True)
            await stream_health(hand, sdk, excluded)
            target = step["positions_deg"].copy()
            for joint in excluded:
                target[joint] = initial[joint]
            delay = step.get("finger_delay", 0.0)/args.tempo
            duration = step["duration"]/args.tempo
            is_wave = step.get("motion") == "wave"
            if is_wave:
                for joint in FLEX_JOINTS:
                    if joint not in excluded:
                        amplitude = 45.0 if joint % 4 == 3 else 60.0
                        limit = min(speed_limit(config, joint, -1), speed_limit(config, joint, 1))
                        duration = max(duration, 6.5*4*math.pi*amplitude/(1.6*6*limit))
            else:
                duration = segment_duration(current, target, duration-delay, config) + delay
            began = time.monotonic()
            total = duration + step["hold"]/args.tempo
            while True:
                now = time.monotonic()
                elapsed = min(now-began, duration)
                positions, velocities = (wave_sample(elapsed, duration) if is_wave else
                                         smooth_sample(current, target, elapsed, duration, delay))
                for joint in excluded:
                    positions[joint], velocities[joint] = initial[joint], 0.0
                check_positions(positions, config)
                for joint, velocity in enumerate(velocities):
                    if abs(velocity) > speed_limit(config, joint, velocity) + 1e-8:
                        raise ValueError(f"Velocity exceeds J{joint} limit")
                await session.send_mit(positions, velocities, kp, kd, [0.0]*JOINT_COUNT)
                if now-last_health >= 0.25:
                    await stream_health(hand, sdk, excluded)
                    last_health = time.monotonic()
                if now-began >= total:
                    break
                await asyncio.sleep(0.01)
            current = target
        await stream_health(hand, sdk, excluded)
        actual = list((await hand.state.snapshot()).positions_deg)
        errors = {j: abs(actual[j]-initial[j]) for j in range(JOINT_COUNT) if j not in excluded}
        if errors and max(errors.values()) > 5.0:
            raise RuntimeError(f"Return tracking error: {errors}")
        print(f"Streaming completed; max return error={max(errors.values(), default=0.0):.2f} deg")
    finally:
        session.close()


async def run_connected(args, profile):
    from bc_revo3_sdk import main_mod as sdk

    manager = sdk.Manager()
    hand = None
    motion_started = False
    try:
        hand = await manager.connect_auto(port=args.port, slave_id=args.slave_id)
        if hand.joint_layout is None or hand.joint_layout.joint_count != JOINT_COUNT:
            raise ValueError("These demos require a 21-joint Revo3 hand")
        device_side = hand.device_info.hand_side if hand.device_info is not None else None
        if device_side not in (sdk.HandSide.Left, sdk.HandSide.Right):
            raise ValueError("Connected hand side is unavailable")
        detected_side = "left" if device_side == sdk.HandSide.Left else "right"
        if args.side is not None and args.side != detected_side:
            raise ValueError("Connected hand does not match --side")
        print(f"Connected hand side: {detected_side}")
        if args.kind != "classic":
            profile = profile if profile is not None else default_profile(args.kind, detected_side)
            validate_profile(profile, args.kind, detected_side)
        config = await hand.config.snapshot()
        if config.software_stop_enabled or config.teaching_mode_enabled:
            raise RuntimeError("Resolve software stop or zero-force mode before running motion demos")
        await stream_health(hand, sdk, set(getattr(args, "skip_joints", [])))
        for field in ("joint_min_position_deg", "joint_max_position_deg", "joint_min_speed_rpm", "joint_max_speed_rpm"):
            if len(getattr(config, field)) != JOINT_COUNT:
                raise ValueError(f"Expected 21 entries in {field}")
        for joint in range(JOINT_COUNT):
            speed_limit(config, joint, -1)
            speed_limit(config, joint, 1)
        initial = list((await hand.state.snapshot()).positions_deg)
        excluded = set(getattr(args, "skip_joints", []))
        for joint in excluded:
            initial[joint] = min(max(initial[joint], config.joint_min_position_deg[joint]), config.joint_max_position_deg[joint])
        check_positions(initial, config, args.feedback_tolerance_deg)
        for joint, value in enumerate(initial):
            bounded = min(max(value, config.joint_min_position_deg[joint]), config.joint_max_position_deg[joint])
            if bounded != value:
                print(f"J{joint}: feedback={value:g} deg; bounded return/hold target={bounded:g} deg")
                initial[joint] = bounded
        if profile is not None:
            for step in profile["steps"]:
                check_positions(step["positions_deg"], config)
                if step.get("motion") == "wave":
                    check_positions(pose((60.0, 60.0, 45.0)), config)
        else:
            classic_targets(initial, config, args)
        motion_started = True
        if args.kind == "classic":
            await classic(hand, initial, config, args, sdk)
        elif profile.get("streaming") or excluded:
            await stream_profile(hand, initial, config, args, sdk, profile, excluded)
        else:
            for _ in range(args.repeat):
                for step in profile["steps"]:
                    print(f"Step: {step['name']}", flush=True)
                    await move(hand, step["positions_deg"], step["duration"] / args.tempo, args, config, sdk)
                    await asyncio.sleep(step["hold"] / args.tempo)
        if args.kind == "classic" or not (profile.get("streaming") or excluded):
            await move(hand, initial, 2.0 / args.tempo, args, config, sdk)
        if args.finish == "relax":
            await hand.motion.set_zero_force_enabled(True)
        print(f"Completed; returned to bounded initial pose; finish={args.finish}")
    except BaseException:
        if hand is not None and motion_started:
            try:
                await asyncio.wait_for(hand.motion.software_stop(), timeout=3.0)
            except BaseException as error:
                print(f"Software stop not confirmed: {error}; use the independent stop path", file=sys.stderr)
        raise
    finally:
        try:
            if hand is not None:
                await hand.close()
        finally:
            await manager.close()


def parser_for(kind):
    parser = argparse.ArgumentParser(description=f"Revo3 {kind} demo. Default: offline preview, no SDK import or connection.")
    parser.add_argument("--side", choices=("left", "right"), help="Require this hand side; otherwise detect it when connected")
    parser.add_argument("--port")
    parser.add_argument("--slave-id", type=lambda value: int(value, 0))
    parser.add_argument("--run", action="store_true", help="Connect and execute motion")
    parser.add_argument("--tempo", type=float, default=1.0, help="Choreography speed multiplier; device speed limits still apply")
    parser.add_argument("--kp", type=float, default=1.0)
    parser.add_argument("--kd", type=float, default=0.1)
    parser.add_argument("--feedback-tolerance-deg", type=float, default=0.0,
                        help="Allow measured feedback up to this far outside limits (0..2 deg); all sent targets remain bounded")
    parser.add_argument("--finish", choices=("hold", "relax"), default="hold", help="Return to initial pose, then retain gains or enable zero force")
    if kind == "classic":
        parser.add_argument("--joints", type=int, nargs="+", default=list(FLEX_JOINTS))
        parser.add_argument("--minimum", type=float, default=0.0)
        parser.add_argument("--maximum", type=float, default=60.0)
        parser.add_argument("--frequency", type=float, default=0.75, help="Sine frequency in Hz")
        parser.add_argument("--rate", type=int, default=100, help="Requested send rate in Hz, not a realtime guarantee")
        parser.add_argument("--cycles", type=int, default=3)
        parser.add_argument("--omega", type=float, default=25.0, help="Host critically damped filter rad/s; 0 disables")
        parser.add_argument("--command-timeout-ms", type=int, default=200)
    else:
        parser.add_argument("--repeat", type=int, default=1)
        parser.add_argument("--profile", type=Path, help="Load calibrated or candidate JSON poses")
        parser.add_argument("--export-profile", type=Path, help="Write candidate JSON and exit without connecting")
    if kind != "classic":
        parser.add_argument("--skip-joints", type=int, nargs="+", default=[],
                            help="Explicit test exclusions; send zero gains to these joints using streaming")
    parser.set_defaults(kind=kind)
    return parser


def main(kind, argv=None):
    parser = parser_for(kind)
    args = parser.parse_args(argv)
    try:
        number(args.tempo, "tempo", positive=True)
        if number(args.feedback_tolerance_deg, "feedback tolerance") > 2.0:
            raise ValueError("Feedback tolerance must be <= 2 degrees")
        for key in ("kp", "kd"):
            if number(getattr(args, key), key) > 10:
                raise ValueError(f"{key} must be <= 10")
        if args.slave_id is not None and not 1 <= args.slave_id <= 247:
            raise ValueError("Use a unicast slave ID in 1..247")
        profile = None
        if kind == "classic":
            number(args.minimum, "minimum", -360)
            number(args.maximum, "maximum", -360)
            number(args.frequency, "frequency", positive=True)
            number(args.omega, "omega")
            if not (args.minimum < args.maximum and 1 <= args.rate <= 200 and args.cycles > 0):
                raise ValueError("Invalid sine range, rate (1..200 Hz), or cycles")
            if args.frequency >= args.rate / 2:
                raise ValueError("Sine frequency must be below half the send rate")
            if args.command_timeout_ms < math.ceil(1000 / args.rate):
                raise ValueError("Command timeout is shorter than one send period")
            if len(set(args.joints)) != len(args.joints) or any(j < 0 or j >= JOINT_COUNT for j in args.joints):
                raise ValueError("Joint indices must be unique and in 0..20")
            print(f"Classic sine: joints={args.joints}, range={args.minimum}..{args.maximum} deg, frequency={args.frequency} Hz, rate={args.rate} Hz, cycles={args.cycles}, omega={args.omega}")
        else:
            if len(set(args.skip_joints)) != len(args.skip_joints) or any(j < 0 or j >= JOINT_COUNT for j in args.skip_joints):
                raise ValueError("Skipped joints must be unique and in 0..20")
            if args.repeat < 1:
                raise ValueError("repeat must be positive")
            profile = json.loads(args.profile.read_text()) if args.profile else None
            if not args.run or args.export_profile:
                profile = profile if profile is not None else default_profile(kind, args.side or "right")
                validate_profile(profile, kind, args.side or profile["side"])
            if args.export_profile:
                with args.export_profile.open("x", encoding="utf-8") as output:
                    json.dump(profile, output, indent=2, allow_nan=False)
                    output.write("\n")
                print(f"Exported {args.export_profile}; no connection opened")
                return 0
            if profile is not None:
                print(json.dumps(profile, indent=2, allow_nan=False))
            if profile is None or not profile["calibrated"]:
                print("Candidate poses: fingertip contact and finger clearance require hardware calibration.")
        if not args.run:
            print("Offline preview only. Pass --run to connect and move after checking the work area and independent stop path.")
            return 0
        asyncio.run(run_connected(args, profile))
        return 0
    except KeyboardInterrupt:
        print("Interrupted; no automatic return motion", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Demo failed: {error}", file=sys.stderr)
        return 1
