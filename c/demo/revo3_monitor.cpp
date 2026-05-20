#include "../common/revo3_common.h"

#include <cstdio>

int main(int argc, char **argv) {
  init_logging(LOG_LEVEL_INFO);

  Revo3Context ctx;
  if (!revo3_init_from_args(ctx, argc, argv)) {
    return 1;
  }

  std::printf("=== Revo3 C++ Buffered Monitor Demo ===\n");
  revo3_print_device_info(ctx.handle, ctx.slave_id);

  CRevo3MotorStatusBuffer *motor_buffer = revo3_motor_buffer_new(256);
  if (!motor_buffer) {
    std::fprintf(stderr, "[ERROR] Failed to allocate motor buffer.\n");
    revo3_close(ctx);
    return 1;
  }

  CDataCollector *collector =
      data_collector_new_revo3_basic(ctx.handle, motor_buffer, ctx.slave_id, 60, true);
  if (!collector) {
    std::fprintf(stderr, "[ERROR] Failed to create data collector.\n");
    revo3_motor_buffer_free(motor_buffer);
    revo3_close(ctx);
    return 1;
  }

  if (data_collector_start(collector) != 1) {
    std::fprintf(stderr, "[ERROR] Failed to start data collector.\n");
    data_collector_free(collector);
    revo3_motor_buffer_free(motor_buffer);
    revo3_close(ctx);
    return 1;
  }

  for (int tick = 0; tick < 5; ++tick) {
    revo3_sleep_ms(1000);
    CRevo3MotorStatusData data[128];
    int count = revo3_motor_buffer_pop_all(motor_buffer, data, 128);
    std::printf("[%d] samples=%d", tick + 1, count);
    if (count > 0) {
      const CRevo3MotorStatusData &latest = data[count - 1];
      std::printf(", latest positions[0..4]:");
      for (int i = 0; i < 5; ++i) {
        std::printf(" %.2f", latest.positions[i]);
      }
    }
    std::printf("\n");
  }

  data_collector_stop(collector);
  data_collector_wait(collector);
  data_collector_free(collector);
  revo3_motor_buffer_free(motor_buffer);
  revo3_close(ctx);
  return 0;
}
