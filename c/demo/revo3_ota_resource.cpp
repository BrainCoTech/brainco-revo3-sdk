#include "../common/revo3_common.h"

#include <atomic>
#include <cstdio>
#include <cstring>
#include <cstdlib>

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
  std::printf("  %s <file_path> <target_type: 0|1|2>              # Auto-detect Revo3\n", program);
  std::printf("  %s --modbus <port> [baud] [slave_id] <file_path> <target_type: 0|1|2>\n", program);
  std::printf("\nTarget Types:\n");
  std::printf("  0: Main MCU firmware (MainFw)\n");
  std::printf("  1: Image resource (Image)\n");
  std::printf("  2: Motor driver firmware (MotorFw)\n");
}

} // namespace

int main(int argc, char **argv) {
  init_logging(LOG_LEVEL_INFO);

  if (argc > 1 && (std::strcmp(argv[1], "--help") == 0 || std::strcmp(argv[1], "-h") == 0)) {
    print_usage(argv[0]);
    return 0;
  }

  // Determine parameter positions
  bool is_modbus = (argc > 1 && std::strcmp(argv[1], "--modbus") == 0);
  int min_args = is_modbus ? 5 : 3;

  if (argc < min_args) {
    print_usage(argv[0]);
    return 1;
  }

  const char *file_path = argv[argc - 2];
  const char *target_str = argv[argc - 1];

  // Parse target type
  char *endptr = nullptr;
  long target_val = std::strtol(target_str, &endptr, 10);
  if (!endptr || *endptr != '\0' || target_val < 0 || target_val > 2) {
    std::fprintf(stderr, "[ERROR] Invalid target type: must be 0, 1, or 2\n");
    print_usage(argv[0]);
    return 1;
  }
  uint8_t target = static_cast<uint8_t>(target_val);

  Revo3Context ctx;
  int init_argc = is_modbus ? (argc - 2) : 1;
  if (!revo3_init_from_args(ctx, init_argc, argv)) {
    return 1;
  }

  const char *target_names[] = {"Main MCU Firmware", "Image Resource", "Motor Driver Firmware"};
  std::printf("=== Revo3 C++ Hand Multi-Target DFU ===\n");
  revo3_print_device_info(ctx.handle, ctx.slave_id);
  std::printf("File path: %s\n", file_path);
  std::printf("Target:    %s (%u)\n", target_names[target], target);

  FILE *file = std::fopen(file_path, "rb");
  if (!file) {
    std::fprintf(stderr, "[ERROR] File not found: %s\n", file_path);
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

  // Start DFU with target
  int32_t ret = revo3_start_dfu_with_target(ctx.handle, ctx.slave_id, file_path, target, 5);
  if (ret != 0) {
    std::fprintf(stderr, "[ERROR] Failed to start Revo3 DFU with target %u, error: %d\n", target, ret);
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
