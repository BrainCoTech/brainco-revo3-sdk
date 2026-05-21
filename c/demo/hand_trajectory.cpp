#include "../common/revo3_common.h"

#include <cstdio>

namespace {

void fill_zero(float *targets) {
  for (int i = 0; i < 21; ++i) {
    targets[i] = 0.0f;
  }
}

} // namespace

int main(int argc, char **argv) {
  init_logging(LOG_LEVEL_INFO);

  Revo3Context ctx;
  if (!revo3_init_from_args(ctx, argc, argv)) {
    return 1;
  }

  std::printf("=== Revo3 C++ Hand Trajectory Demo ===\n");
  revo3_print_device_info(ctx.handle, ctx.slave_id);

  std::printf("Single joint: J3 -> 30 deg over 1.5 s...\n");
  if (revo3_move_joint(ctx.handle, ctx.slave_id, 3, 30.0f, 1.5f, 0.01f) != 0) {
    std::printf("[WARN] revo3_move_joint failed.\n");
  }

  std::printf("Single joint: J3 -> 0 deg at 25 rpm...\n");
  revo3_move_joint_with_speed(ctx.handle, ctx.slave_id, 3, 0.0f, 25.0f, 0.01f);

  float targets[21];
  fill_zero(targets);
  const int pip_joints[] = {2, 6, 10, 14, 18};
  for (int joint : pip_joints) {
    targets[joint] = 45.0f;
  }

  std::printf("Full hand: PIP joints -> 45 deg with custom gains...\n");
  revo3_move_hand_with_gains(ctx.handle, ctx.slave_id, targets, 21, 2.0f, 0.01f, 5.0f, 0.5f);

  fill_zero(targets);
  std::printf("Full hand: all joints -> 0 deg at 25 rpm...\n");
  revo3_move_hand_with_speed(ctx.handle, ctx.slave_id, targets, 21, 25.0f, 0.01f);

  std::printf("Finger: Move Index (finger 1) MCP & PIP to 45 deg over 2.0 s...\n");
  float finger_targets[] = {0.0f, 45.0f, 45.0f, 0.0f};
  revo3_move_finger(ctx.handle, ctx.slave_id, 1, finger_targets, 2.0f, 0.01f);

  std::printf("Thumb: Move CMC Flex & CMC Abd to 30 deg over 2.0 s...\n");
  float thumb_targets[] = {30.0f, 30.0f, 0.0f, 0.0f, 0.0f};
  revo3_move_thumb(ctx.handle, ctx.slave_id, thumb_targets, 2.0f, 0.01f);

  std::printf("Resetting Index and Thumb back to 0 deg...\n");
  float zero_finger[] = {0.0f, 0.0f, 0.0f, 0.0f};
  float zero_thumb[] = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f};
  revo3_move_finger(ctx.handle, ctx.slave_id, 1, zero_finger, 2.0f, 0.01f);
  revo3_move_thumb(ctx.handle, ctx.slave_id, zero_thumb, 2.0f, 0.01f);

  revo3_close(ctx);
  return 0;
}
