#include "../common/revo3_common.h"

#include <cstdio>

namespace {

void print_first_values(const char *label, const float *values, int count) {
  std::printf("%s:", label);
  for (int i = 0; i < count; ++i) {
    std::printf(" %.2f", values[i]);
  }
  std::printf("\n");
}

void set_all(float *values, float value) {
  for (int i = 0; i < 21; ++i) {
    values[i] = value;
  }
}


} // namespace

int main(int argc, char **argv) {
  init_logging(LOG_LEVEL_INFO);

  Revo3Context ctx;
  if (!revo3_init_from_args(ctx, argc, argv)) {
    return 1;
  }

  std::printf("=== Revo3 C++ Hand Demo ===\n");
  revo3_print_device_info(ctx.handle, ctx.slave_id);

  CRevo3MotorStatusData *status = revo3_get_motor_status_data(ctx.handle, ctx.slave_id);
  if (status) {
    print_first_values("Initial positions[0..4]", status->positions, 5);
    print_first_values("Initial velocities[0..4]", status->velocities, 5);
    print_first_values("Initial currents[0..4]", status->currents, 5);
    free_revo3_motor_status_data(status);
  }

  uint16_t enabled = revo3_get_all_touch_modules_enabled(ctx.handle, ctx.slave_id);
  if (enabled != 0) {
    uint16_t summary[42] = {0};
    if (revo3_get_touch_summary(ctx.handle, ctx.slave_id, summary) == 0) {
      std::printf("Touch summary[0..7]:");
      for (int i = 0; i < 8; ++i) {
        std::printf(" %u", summary[i]);
      }
      std::printf("\n");
    }
  } else {
    std::printf("Touch modules are not enabled or not available on this device.\n");
  }

  float zeros[21] = {0.0f};
  set_all(zeros, 0.0f);

  // 1. Explicitly switch all 21 joints to MIT/Impedance mode (4)
  std::printf("Switching all joints to Impedance control mode (4) for smooth trajectory planning...\n");
  revo3_multi_joint_control(ctx.handle, ctx.slave_id, 4, zeros);
  revo3_sleep_ms(100);

  float grip_targets[21] = {0.0f};
  set_all(grip_targets, 0.0f);
  for (int joint : {1, 2, 5, 6, 9, 10, 13, 14}) {
    grip_targets[joint] = 60.0f;
  }
  for (int joint : {17, 18, 19, 20}) {
    grip_targets[joint] = 45.0f;
  }

  // =========================================================================
  // Step 1: Initial Stretch (First open all joints to 0 deg with smooth trajectory)
  // =========================================================================
  std::printf("Step 1: Open all fingers to 0 deg (Initial Stretch via revo3_move_hand_wait)...\n");
  revo3_move_hand_wait(ctx.handle, ctx.slave_id, zeros, 21, 0.7f, 0.025f);

  // =========================================================================
  // Step 2: Grip (Move whole hand to 60 deg with smooth trajectory)
  // =========================================================================
  std::printf("Step 2: Close whole hand to 60 deg (Grip via revo3_move_hand_wait)...\n");
  revo3_move_hand_wait(ctx.handle, ctx.slave_id, grip_targets, 21, 0.7f, 0.025f);

  // =========================================================================
  // Step 3: Open again (Return whole hand to 0 deg with smooth trajectory)
  // =========================================================================
  std::printf("Step 3: Open whole hand to 0 deg (Release via revo3_move_hand_wait)...\n");
  revo3_move_hand_wait(ctx.handle, ctx.slave_id, zeros, 21, 0.7f, 0.025f);

  // =========================================================================
  // Step 2: Test fingers one by one (Pinky -> Ring -> Middle -> Index -> Thumb)
  // =========================================================================
  struct FingerTest {
    const char *name;
    uint16_t idx;
    float target[4];
  };

  FingerTest diagnostic_sequence[] = {
    {"Pinky (Little Finger)", 4, {0.0f, 45.0f, 45.0f, 0.0f}},
    {"Ring Finger", 3, {0.0f, 45.0f, 45.0f, 0.0f}},
    {"Middle Finger", 2, {0.0f, 45.0f, 45.0f, 0.0f}},
    {"Index Finger", 1, {0.0f, 45.0f, 45.0f, 0.0f}}
  };

  float finger_zero[4] = {0.0f};

  for (int f = 0; f < 4; ++f) {
    std::printf("Testing: %s (smooth trajectory)...\n", diagnostic_sequence[f].name);
    // Bend finger
    revo3_move_finger_wait(ctx.handle, ctx.slave_id, diagnostic_sequence[f].idx, diagnostic_sequence[f].target, 0.5f, 0.01f);
    // Stretch finger back
    revo3_move_finger_wait(ctx.handle, ctx.slave_id, diagnostic_sequence[f].idx, finger_zero, 0.5f, 0.01f);
  }

  std::printf("Testing: Thumb (smooth trajectory)...\n");
  float t_bend[5] = {0.0f, 30.0f, 30.0f, 30.0f, 30.0f};
  float t_zero[5] = {0.0f};
  revo3_move_thumb_wait(ctx.handle, ctx.slave_id, t_bend, 0.5f, 0.01f);
  revo3_move_thumb_wait(ctx.handle, ctx.slave_id, t_zero, 0.5f, 0.01f);

  std::printf("Restoring all joints back to Position control mode...\n");
  revo3_multi_joint_control(ctx.handle, ctx.slave_id, 0, zeros);
  revo3_sleep_ms(100);

  revo3_close(ctx);
  return 0;
}
