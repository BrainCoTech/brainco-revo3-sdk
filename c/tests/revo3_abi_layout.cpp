#include <revo3-sdk.h>

#include <cstddef>
#include <cstdint>
#include <type_traits>

static_assert(sizeof(CRevo3TouchRegion) == 1);
static_assert(sizeof(CRevo3TouchSignal) == 1);
static_assert(sizeof(CRevo3TouchSampleState) == 1);
static_assert(sizeof(CRevo3ServoFilterMode) == 1);
static_assert(C_REVO3_SERVO_FILTER_MODE_DISABLED == 0);
static_assert(C_REVO3_SERVO_FILTER_MODE_FIRST_ORDER_LPF == 1);
static_assert(C_REVO3_SERVO_FILTER_MODE_SECOND_ORDER_CRITICALLY_DAMPED == 2);
static_assert(std::is_same_v<decltype(CRevo3DetectedDevice::protocol_type), std::uint8_t>);
static_assert(
    std::is_same_v<decltype(CRevo3DetectedDevice::nominal_baudrate_bps), std::uint32_t>);
static_assert(
    std::is_same_v<decltype(CRevo3DetectedDevice::data_baudrate_bps), std::uint32_t>);
static_assert(std::is_same_v<decltype(CRevo3DetectedDevice::model), std::uint8_t>);
static_assert(std::is_same_v<decltype(CRevo3DetectedDevice::hand_side), std::uint8_t>);
static_assert(std::is_same_v<decltype(CRevo3DetectedDevice::port_name), const char *>);
static_assert(std::is_same_v<decltype(CRevo3HandDescriptor::joint_layout_available), bool>);
static_assert(std::extent_v<decltype(CRevo3HandDescriptor::joint_layout_id)> == 64);
static_assert(std::extent_v<decltype(CRevo3ApiVersion::version)> == 32);
static_assert(std::extent_v<decltype(CRevo3ErrorInfo::message)> == 256);
static_assert(std::extent_v<decltype(CRevo3ErrorInfo::low_level_cause)> == 256);

static_assert(sizeof(CRevo3TouchRegionLayout) == 24);
static_assert(sizeof(CRevo3TouchModuleLayout) == 78);
static_assert(sizeof(CRevo3TouchLayout) == 940);
static_assert(sizeof(CRevo3TouchForce3D) == 12);
static_assert(sizeof(CRevo3TouchTorque2D) == 8);
static_assert(sizeof(CRevo3TouchModuleData) == 524);
static_assert(sizeof(CRevo3TouchFrame) == 5816);

static_assert(offsetof(CRevo3TouchModuleData, points) == 8);
static_assert(offsetof(CRevo3TouchModuleData, has_force3d) == 422);
static_assert(offsetof(CRevo3TouchModuleData, force3d) == 432);
static_assert(offsetof(CRevo3TouchModuleData, torque2d) == 444);
static_assert(offsetof(CRevo3TouchModuleData, resultant_force_mn) == 452);
static_assert(offsetof(CRevo3TouchModuleData, layout_id) == 460);

static_assert(offsetof(CRevo3TouchFrame, timestamp) == 16);
static_assert(offsetof(CRevo3TouchFrame, module_count) == 40);
static_assert(offsetof(CRevo3TouchFrame, reserved_frame_kind) == 42);
static_assert(offsetof(CRevo3TouchFrame, reserved) == 43);
static_assert(offsetof(CRevo3TouchFrame, modules) == 52);

// Units conversion symbol contracts
static_assert(std::is_same_v<decltype(revo3_deg_to_rad(1.0f)), float>);
static_assert(std::is_same_v<decltype(revo3_rad_to_deg(1.0f)), float>);
static_assert(std::is_same_v<decltype(revo3_rpm_to_rad_s(1.0f)), float>);
static_assert(std::is_same_v<decltype(revo3_rad_s_to_rpm(1.0f)), float>);
static_assert(std::is_same_v<decltype(revo3_ma_to_a(1.0f)), float>);
static_assert(std::is_same_v<decltype(revo3_a_to_ma(1.0f)), float>);
static_assert(std::is_same_v<decltype(revo3_deg_to_rad_array(nullptr, nullptr, 0)), int>);

int main() { return 0; }
