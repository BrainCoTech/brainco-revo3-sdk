#include "../common/revo3_common.h"

#include <cstdio>

int main(int argc, char **argv) {
  init_logging(LOG_LEVEL_INFO);

  Revo3Context ctx;
  if (!revo3_init_from_args(ctx, argc, argv)) {
    return 1;
  }

  std::printf("=== Revo3 C++ Motor Demo ===\n");
  revo3_print_device_info(ctx.handle, ctx.slave_id);

  CRevo3MotorStatusData *status = revo3_get_motor_status_data(ctx.handle, ctx.slave_id);
  if (status) {
    std::printf("Positions[0..4]:");
    for (int i = 0; i < 5; ++i) {
      std::printf(" %.2f", status->positions[i]);
    }
    std::printf("\n");
    free_revo3_motor_status_data(status);
  }

  std::printf("Move joint 0 to 10 deg...\n");
  revo3_set_motor_position(ctx.handle, ctx.slave_id, 0, 10.0f);
  revo3_sleep_ms(500);

  float positions[21] = {0.0f};
  for (float &position : positions) {
    position = 5.0f;
  }
  std::printf("Move all joints to 5 deg...\n");
  revo3_set_all_motor_positions(ctx.handle, ctx.slave_id, positions);
  revo3_sleep_ms(500);

  for (float &position : positions) {
    position = 0.0f;
  }
  std::printf("Move all joints back to 0 deg...\n");
  revo3_set_all_motor_positions(ctx.handle, ctx.slave_id, positions);

  // Zero-position setup changes persistent device calibration. Uncomment only
  // when the hand is in the intended reference pose.
  // // Recommended Workflow: 1. Disable motors -> 2. Pose hand -> 3. Enable motors -> 4. Call API
  // revo3_set_current_position_as_zero(ctx.handle, ctx.slave_id);
  // float zero_offsets_deg[21] = {0.0f};
  // revo3_set_zero_position(ctx.handle, ctx.slave_id, zero_offsets_deg);

  float read_offsets_deg[21] = {0.0f};
  if (revo3_get_zero_position(ctx.handle, ctx.slave_id, read_offsets_deg) == 0) {
    std::printf("Current zero position offsets (first 5 joints):");
    for (int i = 0; i < 5; ++i) {
      std::printf(" %.2f", read_offsets_deg[i]);
    }
    std::printf("\n");
  } else {
    std::printf("Failed to get zero position offsets.\n");
  }

  revo3_close(ctx);
  return 0;
}
