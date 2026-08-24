#include <revo3-sdk.h>

#include <stddef.h>

int main(void) {
  CRevo3ApiVersion version = {0};
  CRevo3MotionOptions motion_options = {0};
  CRevo3RuntimeOptions runtime_options = {0};
  CRevo3ExperimentalCollisionConfig collision_config = {0};
  CRevo3ErrorInfo error = {0};

  /* These lower-level APIs are intentionally not wrapped by the C++ object API. */
  (void)&revo3_auto_detect_is_finished;
  (void)&revo3_auto_detect_stop;
  (void)&revo3_configure_usb_vid_pid_allowlist;
  (void)&revo3_init_logging;

  /* Public device-configuration symbol contracts. */
  (void)&revo3_device_set_rs485_baudrate;
  (void)&revo3_device_set_canfd_baudrate;

  if (revo3_get_api_version(&version, sizeof(version)) != 0 ||
      revo3_motion_options_init(&motion_options, sizeof(motion_options)) != 0 ||
      revo3_runtime_options_init(&runtime_options, sizeof(runtime_options)) != 0 ||
      revo3_experimental_collision_config_init(&collision_config,
                                                sizeof(collision_config)) != 0) {
    return 1;
  }
  if (version.major != 2 || motion_options.struct_size != sizeof(motion_options) ||
      runtime_options.struct_size != sizeof(runtime_options) ||
      collision_config.struct_size != sizeof(collision_config)) {
    return 2;
  }
  if (revo3_auto_detect_start(true, NULL, REVO3_PROTOCOL_TYPE_AUTO, 0, 0, 0,
                              true, NULL, NULL) != NULL) {
    return 3;
  }

  float deg = 180.0f;
  float rad = revo3_deg_to_rad(deg);
  if (rad < 3.1415f || rad > 3.1416f) {
    return 4;
  }
  if (revo3_rad_to_deg(rad) < 179.9f || revo3_rad_to_deg(rad) > 180.1f) {
    return 5;
  }
  if (revo3_ma_to_a(1500.0f) < 1.49f || revo3_ma_to_a(1500.0f) > 1.51f) {
    return 6;
  }

  return (int)error.struct_size;
}
