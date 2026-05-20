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
    uint16_t summary[26] = {0};
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

  float targets[21] = {0.0f};
  set_all(targets, 0.0f);
  targets[1] = 20.0f;
  targets[5] = 20.0f;
  targets[9] = 20.0f;
  targets[13] = 20.0f;
  targets[17] = 20.0f;

  std::printf("Move MCP joints to 20 deg with trajectory...\n");
  if (revo3_move_hand(ctx.handle, ctx.slave_id, targets, 21, 2.0f, 0.01f) != 0) {
    std::printf("[WARN] Trajectory move failed.\n");
  }

  revo3_sleep_ms(300);
  set_all(targets, 0.0f);
  std::printf("Return all joints to 0 deg...\n");
  revo3_move_hand(ctx.handle, ctx.slave_id, targets, 21, 2.0f, 0.01f);

  revo3_close(ctx);
  return 0;
}
