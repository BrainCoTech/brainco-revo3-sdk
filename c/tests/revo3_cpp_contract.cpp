#include <revo3/revo3.hpp>

#include <optional>
#include <string>
#include <type_traits>
#include <utility>

static_assert(__cplusplus >= 201703L);
static_assert(std::is_same_v<decltype(revo3::api_version()), revo3::ApiVersion>);

template <typename Type, typename = void>
struct has_protocol_alias : std::false_type {};

template <typename Type>
struct has_protocol_alias<Type,
                          std::void_t<decltype(std::declval<Type>().protocol)>>
    : std::true_type {};

template <typename Type, typename = void>
struct has_port_alias : std::false_type {};

template <typename Type>
struct has_port_alias<Type, std::void_t<decltype(std::declval<Type>().port)>>
    : std::true_type {};

static_assert(std::is_same_v<decltype(std::declval<const revo3::Hand &>().joint_layout()),
                             std::optional<revo3::JointLayout>>);
static_assert(std::is_same_v<decltype(std::declval<const revo3::OperationHandle &>().error()),
                             std::optional<revo3::SdkError>>);
static_assert(std::is_same_v<decltype(std::declval<const revo3::SdkError &>().code()),
                             revo3::SdkErrorCode>);
static_assert(
    std::is_same_v<decltype(std::declval<const revo3::SdkError &>().operation_effect()),
                   revo3::OperationEffect>);
static_assert(
    std::is_same_v<decltype(std::declval<const revo3::SdkError &>().recovery_requirement()),
                   revo3::RecoveryRequirement>);
static_assert(static_cast<std::uint32_t>(revo3::RecoveryRequirement::OperatorAction) == 4);
static_assert(
    std::is_same_v<decltype(std::declval<const revo3::SdkError &>().low_level_cause()),
                   const std::optional<std::string> &>);
static_assert(
    std::is_same_v<decltype(std::declval<revo3::DetectedDevice>().protocol_type),
                   revo3::ProtocolType>);
static_assert(
    std::is_same_v<decltype(std::declval<revo3::DetectedDevice>().hand_side),
                   revo3::HandSide>);
static_assert(std::is_same_v<decltype(std::declval<revo3::DetectedDevice>().port_name),
                             std::string>);
static_assert(!has_protocol_alias<revo3::DetectedDevice>::value);
static_assert(!has_port_alias<revo3::DetectedDevice>::value);
static_assert(std::is_same_v<decltype(revo3::TouchModuleData::force3d),
                             revo3::TouchForce3D>);
static_assert(std::is_same_v<decltype(revo3::TouchModuleData::torque2d),
                             revo3::TouchTorque2D>);

static_assert(std::is_same_v<decltype(revo3::units::deg_to_rad(1.0f)), float>);
static_assert(std::is_same_v<decltype(revo3::units::deg_to_rad(std::vector<float>{})),
                             std::vector<float>>);
static_assert(std::is_same_v<decltype(revo3::units::deg_to_rad(std::array<float, 21>{})),
                             std::array<float, 21>>);

int main() { return 0; }
