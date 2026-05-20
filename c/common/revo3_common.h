#pragma once

#include "stark-sdk.h"
#include <cstdint>

struct Revo3Context {
  DeviceHandler *handle = nullptr;
  StarkProtocolType protocol = STARK_PROTOCOL_TYPE_MODBUS;
  uint8_t slave_id = 1;
};

bool revo3_init_from_args(Revo3Context &ctx, int argc, char **argv);
void revo3_close(Revo3Context &ctx);
void revo3_print_device_info(DeviceHandler *handle, uint8_t slave_id);
const char *revo3_hw_type_name(StarkHardwareType hw_type);
void revo3_sleep_ms(int ms);
