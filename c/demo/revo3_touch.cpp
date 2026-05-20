#include "../common/revo3_common.h"

#include <cstdio>

int main(int argc, char **argv) {
  init_logging(LOG_LEVEL_INFO);

  Revo3Context ctx;
  if (!revo3_init_from_args(ctx, argc, argv)) {
    return 1;
  }

  std::printf("=== Revo3 C++ Touch Demo ===\n");
  revo3_print_device_info(ctx.handle, ctx.slave_id);

  revo3_set_all_touch_modules_enabled(ctx.handle, ctx.slave_id, 0x07FF);
  revo3_sleep_ms(200);

  uint16_t enabled = revo3_get_all_touch_modules_enabled(ctx.handle, ctx.slave_id);
  std::printf("Enabled touch modules: 0x%03X\n", enabled);

  uint16_t summary[26] = {0};
  if (revo3_get_touch_summary(ctx.handle, ctx.slave_id, summary) == 0) {
    std::printf("Touch summary:");
    for (uint16_t value : summary) {
      std::printf(" %u", value);
    }
    std::printf("\n");
  } else {
    std::printf("[WARN] Failed to read touch summary.\n");
  }

  uint16_t module_data[REVO3_TOUCH_MAX_POINTS] = {0};
  uint16_t count = 0;
  if (revo3_get_touch_module_data(ctx.handle, ctx.slave_id, 0, module_data, &count) == 0) {
    std::printf("Palm module points: %u, first values:", count);
    for (uint16_t i = 0; i < count && i < 8; ++i) {
      std::printf(" %u", module_data[i]);
    }
    std::printf("\n");
  }

  revo3_close(ctx);
  return 0;
}
