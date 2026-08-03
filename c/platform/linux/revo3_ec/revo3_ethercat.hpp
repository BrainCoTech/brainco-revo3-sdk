#ifndef REVO3_ETHERCAT_HPP
#define REVO3_ETHERCAT_HPP

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>

struct ec_domain;
struct ec_master;
struct ec_slave_config;

namespace revo3::ethercat {

constexpr std::uint32_t kVendorId = 0x00BC0000;
constexpr std::uint32_t kProductCode = 0x00000002;
constexpr std::size_t kPdoJointCount = 23;
constexpr std::size_t kMotorCount = 21;
constexpr std::size_t kTouchPacketCapacity = 200;
constexpr std::uint16_t kDefaultDcAssignActivate = 0x0300;

constexpr std::uint16_t kRxPdoMotorControlIndex = 0x1600;
constexpr std::uint16_t kRxPdoMotorControlEchoIndex = 0x1601;
constexpr std::uint16_t kTxPdoMotorDataIndex = 0x1A00;
constexpr std::uint16_t kTxPdoTouchSensorDataIndex = 0x1A01;
constexpr std::uint16_t kSm2AssignmentIndex = 0x1C12;
constexpr std::uint16_t kSm3AssignmentIndex = 0x1C13;

constexpr std::uint16_t kJointTargetVelocityArrayIndex = 0x6000;
constexpr std::uint16_t kJointTargetPositionArrayIndex = 0x6001;
constexpr std::uint16_t kJointTargetCurrentArrayIndex = 0x6002;
constexpr std::uint16_t kJointTargetKpArrayIndex = 0x6003;
constexpr std::uint16_t kJointTargetKdArrayIndex = 0x6004;
constexpr std::uint16_t kJointStatusCodeArrayIndex = 0x7000;
constexpr std::uint16_t kJointActualVelocityArrayIndex = 0x7001;
constexpr std::uint16_t kJointActualPositionArrayIndex = 0x7002;
constexpr std::uint16_t kJointActualCurrentArrayIndex = 0x7003;
constexpr std::uint16_t kJointErrorCodeArrayIndex = 0x7004;
constexpr std::uint16_t kTouchSensorIndexObjectIndex = 0x7005;
constexpr std::uint16_t kTouchSensorLengthObjectIndex = 0x7006;
constexpr std::uint16_t kTouchSensorDataObjectIndex = 0x7007;

constexpr std::uint16_t kMotorTempDataObjectIndex = 0x8000;
constexpr std::uint16_t kFirmwareVersionObjectIndex = 0x8001;
constexpr std::uint16_t kHardwareVersionObjectIndex = 0x8002;
constexpr std::uint16_t kSerialNumberObjectIndex = 0x8003;
constexpr std::uint16_t kMotorSnObjectIndexBase = 0x8004;
constexpr std::uint16_t kMotorVersionObjectIndex = 0x8019;
constexpr std::uint16_t kMotorSystemParamsObjectIndex = 0x801A;
constexpr std::uint16_t kHandTypeObjectIndex = 0x801B;
constexpr std::uint16_t kTouchVendorObjectIndex = 0x801C;

constexpr std::uint16_t kPositionZeroCommandIndex = 0x8802;
constexpr std::uint16_t kFactoryResetCommandIndex = 0x8803;
constexpr std::uint16_t kSoftwareResetCommandIndex = 0x8804;
constexpr std::uint16_t kManualCalibrationCommandIndex = 0x8805;
constexpr std::uint16_t kClearMotorErrorCommandIndex = 0x8806;
constexpr std::uint16_t kEnterTeachingModeCommandIndex = 0x8807;

constexpr std::uint16_t kBuzzerSwitchObjectIndex = 0x9003;
constexpr std::uint16_t kVibrationSwitchObjectIndex = 0x9004;
constexpr std::uint16_t kAutoCalibrationObjectIndex = 0x9006;
constexpr std::uint16_t kEmergencyStopObjectIndex = 0x9007;
constexpr std::uint16_t kMotorErrorAutoClearObjectIndex = 0x9008;
constexpr std::uint16_t kAllMotorProtectThresholdObjectIndex = 0x9009;
constexpr std::uint16_t kMotorProtectCurrentArrayIndex = 0x900A;
constexpr std::uint16_t kMotorTravelMinArrayIndex = 0x900B;
constexpr std::uint16_t kMotorTravelMaxArrayIndex = 0x900C;
constexpr std::uint16_t kMotorSpeedMinArrayIndex = 0x900D;
constexpr std::uint16_t kMotorSpeedMaxArrayIndex = 0x900E;

constexpr std::size_t kOutputProcessDataSize = 234;
constexpr std::size_t kMotorInputProcessDataSize = 276;
constexpr std::size_t kTouchInputProcessDataSize = 404;
constexpr std::size_t kRxPdoMotorControlEchoEntryCount = 2;

constexpr std::size_t kOutputVelocityOffset = 0;
constexpr std::size_t kOutputPositionOffset = 46;
constexpr std::size_t kOutputCurrentOffset = 92;
constexpr std::size_t kOutputKpOffset = 138;
constexpr std::size_t kOutputKdOffset = 184;

constexpr std::size_t kMotorStatusOffset = 0;
constexpr std::size_t kMotorVelocityOffset = 46;
constexpr std::size_t kMotorPositionOffset = 92;
constexpr std::size_t kMotorCurrentOffset = 138;
constexpr std::size_t kMotorErrorOffset = 184;

constexpr std::size_t kTouchIndexOffset = 0;
constexpr std::size_t kTouchLengthOffset = 2;
constexpr std::size_t kTouchDataOffset = 4;

struct PdoLayout {
  const char *name;
  std::uint16_t rx_pdo_index;
  std::uint16_t extra_rx_pdo_index;
  std::size_t extra_rx_pdo_entry_count;
  std::uint16_t motor_tx_pdo_index;
  std::uint16_t touch_tx_pdo_index;
  bool has_touch_pdo;
  std::size_t pdo_joint_count;
  std::size_t motor_count;
  std::size_t touch_packet_capacity;
  std::size_t output_process_data_size;
  std::size_t motor_input_process_data_size;
  std::size_t touch_input_process_data_size;
  std::uint16_t output_object_index;
  std::uint8_t output_object_subindex;
  std::uint16_t motor_input_object_index;
  std::uint8_t motor_input_object_subindex;
  std::uint16_t touch_input_object_index;
  std::uint8_t touch_input_object_subindex;
  std::size_t output_velocity_offset;
  std::size_t output_position_offset;
  std::size_t output_current_offset;
  std::size_t output_kp_offset;
  std::size_t output_kd_offset;
  std::size_t motor_status_offset;
  std::size_t motor_velocity_offset;
  std::size_t motor_position_offset;
  std::size_t motor_current_offset;
  std::size_t motor_error_offset;
  std::size_t touch_index_offset;
  std::size_t touch_length_offset;
  std::size_t touch_data_offset;
};

constexpr bool pdo_range_fits(std::size_t offset, std::size_t count,
                              std::size_t element_size,
                              std::size_t process_data_size) {
  return element_size != 0 && offset <= process_data_size &&
         count <= (process_data_size - offset) / element_size;
}

constexpr bool is_valid_pdo_layout(const PdoLayout &layout) {
  return layout.name != nullptr && layout.rx_pdo_index != 0 &&
         layout.motor_tx_pdo_index != 0 && layout.pdo_joint_count > 0 &&
         (layout.extra_rx_pdo_entry_count == 0 ||
          (layout.extra_rx_pdo_index != 0 &&
           layout.extra_rx_pdo_entry_count <= layout.pdo_joint_count)) &&
         layout.pdo_joint_count <= kPdoJointCount &&
         layout.motor_count <= layout.pdo_joint_count &&
         layout.motor_count <= kMotorCount &&
         pdo_range_fits(layout.output_velocity_offset, layout.pdo_joint_count,
                        sizeof(std::uint16_t),
                        layout.output_process_data_size) &&
         pdo_range_fits(layout.output_position_offset, layout.pdo_joint_count,
                        sizeof(std::uint16_t),
                        layout.output_process_data_size) &&
         pdo_range_fits(layout.output_current_offset, layout.pdo_joint_count,
                        sizeof(std::uint16_t),
                        layout.output_process_data_size) &&
         pdo_range_fits(layout.output_kp_offset, layout.pdo_joint_count,
                        sizeof(std::uint16_t),
                        layout.output_process_data_size) &&
         pdo_range_fits(layout.output_kd_offset, layout.pdo_joint_count,
                        sizeof(std::uint16_t),
                        layout.output_process_data_size) &&
         pdo_range_fits(layout.motor_status_offset, layout.pdo_joint_count,
                        sizeof(std::uint16_t),
                        layout.motor_input_process_data_size) &&
         pdo_range_fits(layout.motor_velocity_offset, layout.pdo_joint_count,
                        sizeof(std::uint16_t),
                        layout.motor_input_process_data_size) &&
         pdo_range_fits(layout.motor_position_offset, layout.pdo_joint_count,
                        sizeof(std::uint16_t),
                        layout.motor_input_process_data_size) &&
         pdo_range_fits(layout.motor_current_offset, layout.pdo_joint_count,
                        sizeof(std::uint16_t),
                        layout.motor_input_process_data_size) &&
         pdo_range_fits(layout.motor_error_offset, layout.pdo_joint_count,
                        sizeof(std::uint32_t),
                        layout.motor_input_process_data_size) &&
         (!layout.has_touch_pdo ||
          (layout.touch_tx_pdo_index != 0 &&
           layout.touch_packet_capacity <= kTouchPacketCapacity &&
           pdo_range_fits(layout.touch_index_offset, 1,
                          sizeof(std::uint16_t),
                          layout.touch_input_process_data_size) &&
           pdo_range_fits(layout.touch_length_offset, 1,
                          sizeof(std::uint16_t),
                          layout.touch_input_process_data_size) &&
           pdo_range_fits(layout.touch_data_offset,
                          layout.touch_packet_capacity,
                          sizeof(std::uint16_t),
                          layout.touch_input_process_data_size)));
}

constexpr PdoLayout default_pdo_layout_value() {
  return {
      "stark3_etc_drive_fixed", kRxPdoMotorControlIndex,
      kRxPdoMotorControlEchoIndex, kRxPdoMotorControlEchoEntryCount,
      kTxPdoMotorDataIndex, kTxPdoTouchSensorDataIndex, true,
      kPdoJointCount, kMotorCount, kTouchPacketCapacity,
      kOutputProcessDataSize, kMotorInputProcessDataSize,
      kTouchInputProcessDataSize, kJointTargetVelocityArrayIndex, 0x01,
      kJointStatusCodeArrayIndex, 0x01, kTouchSensorIndexObjectIndex, 0x00,
      kOutputVelocityOffset, kOutputPositionOffset, kOutputCurrentOffset,
      kOutputKpOffset, kOutputKdOffset, kMotorStatusOffset,
      kMotorVelocityOffset, kMotorPositionOffset, kMotorCurrentOffset,
      kMotorErrorOffset, kTouchIndexOffset, kTouchLengthOffset,
      kTouchDataOffset,
  };
}

struct DcConfig {
  bool enabled = false;
  std::uint16_t assign_activate = kDefaultDcAssignActivate;
  std::uint32_t sync0_cycle_ns = 1'000'000;
  std::int32_t sync0_shift_ns = 0;
  std::uint32_t sync1_cycle_ns = 0;
  std::int32_t sync1_shift_ns = 0;
};

const PdoLayout &default_pdo_layout();
std::uint64_t monotonic_time_ns();
void sleep_until_monotonic_ns(std::uint64_t target_time_ns);
bool enable_realtime(int priority, std::string *error = nullptr);

struct MotorCommand {
  std::array<std::uint16_t, kPdoJointCount> velocity{};
  std::array<std::uint16_t, kPdoJointCount> position{};
  std::array<std::uint16_t, kPdoJointCount> current{};
  std::array<std::uint16_t, kPdoJointCount> kp{};
  std::array<std::uint16_t, kPdoJointCount> kd{};
};

struct MotorFeedback {
  std::array<std::uint16_t, kPdoJointCount> status{};
  std::array<std::uint16_t, kPdoJointCount> velocity{};
  std::array<std::uint16_t, kPdoJointCount> position{};
  std::array<std::uint16_t, kPdoJointCount> current{};
  std::array<std::uint32_t, kPdoJointCount> error{};
};

struct TouchPacket {
  std::uint16_t index = 0;
  std::uint16_t length = 0;
  std::array<std::uint16_t, kTouchPacketCapacity> data{};
};

class Master {
public:
  explicit Master(std::uint16_t slave_position = 0,
                  unsigned int master_index = 0,
                  const PdoLayout &layout = default_pdo_layout());
  ~Master();

  Master(const Master &) = delete;
  Master &operator=(const Master &) = delete;

  bool initialize(std::string *error = nullptr);
  bool initialize_sdo(std::string *error = nullptr);
  bool activate(std::string *error = nullptr);
  bool cycle(std::uint64_t application_time_ns = 0);
  void shutdown();
  void configure_dc(const DcConfig &config) { dc_config_ = config; }
  bool wait_for_operational(unsigned int timeout_ms,
                            std::uint64_t cycle_period_ns = 0,
                            std::string *error = nullptr);

  MotorCommand &command() { return command_; }
  const MotorFeedback &feedback() const { return feedback_; }
  const TouchPacket &touch_packet() const { return touch_packet_; }
  bool outputs_initialized() const { return outputs_initialized_; }
  const PdoLayout &pdo_layout() const { return layout_; }

  bool read_sdo(std::uint16_t index, std::uint8_t subindex, void *data,
                std::size_t capacity, std::size_t *result_size,
                std::uint32_t *abort_code = nullptr);
  bool write_sdo(std::uint16_t index, std::uint8_t subindex, const void *data,
                 std::size_t size, std::uint32_t *abort_code = nullptr);

private:
  void apply_detected_pdo_layout();
  void build_pdo_configuration();
  void sync_distributed_clocks(std::uint64_t application_time_ns);
  void read_process_data();
  void write_process_data();

  std::uint16_t slave_position_;
  unsigned int master_index_;
  PdoLayout layout_;
  DcConfig dc_config_{};
  ec_master *master_ = nullptr;
  ec_domain *domain_ = nullptr;
  ec_slave_config *slave_config_ = nullptr;
  std::uint8_t *domain_data_ = nullptr;
  unsigned int output_offset_ = 0;
  unsigned int motor_input_offset_ = 0;
  unsigned int touch_input_offset_ = 0;
  bool active_ = false;
  bool dc_reference_synced_ = false;
  bool outputs_initialized_ = false;
  MotorCommand command_{};
  MotorFeedback feedback_{};
  TouchPacket touch_packet_{};

  struct PdoConfiguration;
  PdoConfiguration *pdo_ = nullptr;
};

} // namespace revo3::ethercat

#endif
