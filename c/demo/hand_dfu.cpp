#include "../common/revo3_common.h"

#include <atomic>
#include <cstdio>
#include <cstring>

namespace {

std::atomic<bool> g_done(false);
std::atomic<bool> g_failed(false);

const char *dfu_state_name(uint8_t state) {
  switch (state) {
  case DFU_STATE_IDLE:
    return "Idle";
  case DFU_STATE_STARTING:
    return "Starting";
  case DFU_STATE_STARTED:
    return "Started";
  case DFU_STATE_TRANSFER:
    return "Transfer";
  case DFU_STATE_COMPLETED:
    return "Completed";
  case DFU_STATE_ABORTED:
    return "Aborted";
  default:
    return "Unknown";
  }
}

void print_usage(const char *program) {
  std::printf("Usage:\n");
  std::printf("  %s <firmware_file>\n", program);
  std::printf("  %s --modbus <port> [baud] [slave_id] <firmware_file>\n", program);
}

const char *firmware_arg(int argc, char **argv) {
  if (argc > 1 && std::strcmp(argv[1], "--modbus") == 0) {
    if (argc > 5) {
      return argv[5];
    }
    return nullptr;
  }
  if (argc > 1) {
    return argv[1];
  }
  return nullptr;
}

} // namespace

int main(int argc, char **argv) {
  init_logging(LOG_LEVEL_INFO);

  if (argc > 1 && std::strcmp(argv[1], "--help") == 0) {
    print_usage(argv[0]);
    return 0;
  }

  const char *firmware = firmware_arg(argc, argv);
  if (!firmware) {
    print_usage(argv[0]);
    return 1;
  }

  Revo3Context ctx;
  int init_argc = argc;
  if (argc > 1 && std::strcmp(argv[1], "--modbus") != 0) {
    init_argc = 1;
  }
  if (!revo3_init_from_args(ctx, init_argc, argv)) {
    return 1;
  }

  std::printf("=== Revo3 C++ DFU ===\n");
  revo3_print_device_info(ctx.handle, ctx.slave_id);
  std::printf("Firmware: %s\n", firmware);

  FILE *file = std::fopen(firmware, "rb");
  if (!file) {
    std::fprintf(stderr, "[ERROR] Firmware file not found: %s\n", firmware);
    revo3_close(ctx);
    return 1;
  }
  std::fclose(file);

  set_dfu_state_callback([](uint8_t slave_id, uint8_t state) {
    std::printf("\n[DFU] slave=%u state=%s (%u)\n", slave_id, dfu_state_name(state), state);
    if (state == DFU_STATE_COMPLETED) {
      g_done = true;
    } else if (state == DFU_STATE_ABORTED) {
      g_failed = true;
    }
  });

  set_dfu_progress_callback([](uint8_t slave_id, float progress) {
    std::printf("\r[DFU] slave=%u progress=%.1f%%", slave_id, progress * 100.0f);
    std::fflush(stdout);
  });

  if (revo3_start_dfu(ctx.handle, ctx.slave_id, firmware, 5) != 0) {
    std::fprintf(stderr, "[ERROR] Failed to start Revo3 DFU.\n");
    revo3_close(ctx);
    return 1;
  }

  while (!g_done && !g_failed) {
    revo3_sleep_ms(500);
  }

  std::printf("\n%s\n", g_done ? "[INFO] DFU completed." : "[ERROR] DFU failed.");
  revo3_close(ctx);
  return g_done ? 0 : 1;
}
