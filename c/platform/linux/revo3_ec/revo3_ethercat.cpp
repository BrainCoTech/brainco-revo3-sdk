#include "revo3_ethercat.hpp"

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstring>
#include <ecrt.h>
#include <sstream>
#include <thread>
#include <time.h>

#ifdef __linux__
#include <sched.h>
#include <sys/mman.h>
#endif

namespace revo3::ethercat {

namespace {

constexpr std::uint64_t kNanosecondsPerSecond = 1'000'000'000ULL;
constexpr std::uint64_t kDefaultOpCyclePeriodNs = 10'000'000ULL;
constexpr unsigned int kSm0 = 0;
constexpr unsigned int kSm1 = 1;
constexpr unsigned int kSm2 = 2;
constexpr unsigned int kSm3 = 3;
constexpr unsigned int kSyncInfoTerminator = 0xFF;
constexpr unsigned int kMasterAlias = 0;
constexpr unsigned int kEthercatOpStateBit = 0x08;

std::string operation_error(const char *operation, int result,
                            std::uint32_t abort_code = 0) {
  std::ostringstream stream;
  stream << operation << " failed (result=" << result;
  if (abort_code != 0) {
    stream << ", abort=0x" << std::hex << abort_code;
  }
  return stream.str() + ")";
}

} // namespace

const PdoLayout &default_pdo_layout() {
  static constexpr PdoLayout layout = default_pdo_layout_value();
  static_assert(is_valid_pdo_layout(layout), "Invalid default PDO layout");
  return layout;
}

std::uint64_t monotonic_time_ns() {
  timespec now{};
  clock_gettime(CLOCK_MONOTONIC, &now);
  return static_cast<std::uint64_t>(now.tv_sec) * kNanosecondsPerSecond +
         static_cast<std::uint64_t>(now.tv_nsec);
}

void sleep_until_monotonic_ns(std::uint64_t target_time_ns) {
#ifdef __linux__
  timespec target{};
  target.tv_sec = static_cast<time_t>(target_time_ns / kNanosecondsPerSecond);
  target.tv_nsec = static_cast<long>(target_time_ns % kNanosecondsPerSecond);
  while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &target, nullptr) ==
         EINTR) {
  }
#else
  const std::uint64_t now_ns = monotonic_time_ns();
  if (target_time_ns > now_ns) {
    std::this_thread::sleep_for(
        std::chrono::nanoseconds(target_time_ns - now_ns));
  }
#endif
}

bool enable_realtime(int priority, std::string *error) {
#ifdef __linux__
  const int min_priority = sched_get_priority_min(SCHED_FIFO);
  const int max_priority = sched_get_priority_max(SCHED_FIFO);
  if (priority < min_priority || priority > max_priority) {
    if (error != nullptr) {
      *error = "realtime priority must be in the range " +
               std::to_string(min_priority) + ".." +
               std::to_string(max_priority);
    }
    return false;
  }
  if (mlockall(MCL_CURRENT | MCL_FUTURE) != 0) {
    if (error != nullptr) {
      *error = std::string("mlockall failed: ") + std::strerror(errno);
    }
    return false;
  }
  sched_param param{};
  param.sched_priority = priority;
  if (sched_setscheduler(0, SCHED_FIFO, &param) != 0) {
    if (error != nullptr) {
      *error = std::string("sched_setscheduler failed: ") +
               std::strerror(errno);
    }
    return false;
  }
  return true;
#else
  (void)priority;
  if (error != nullptr) {
    *error = "realtime scheduling is only supported on Linux";
  }
  return false;
#endif
}

struct Master::PdoConfiguration {
  std::array<ec_pdo_entry_info_t, kPdoJointCount * 5> rx_entries{};
  std::array<ec_pdo_entry_info_t, kPdoJointCount> extra_rx_entries{};
  std::array<ec_pdo_entry_info_t, kPdoJointCount * 5> motor_tx_entries{};
  std::array<ec_pdo_entry_info_t, 2 + kTouchPacketCapacity> touch_tx_entries{};
  std::array<ec_pdo_info_t, 2> rx_pdos{};
  std::array<ec_pdo_info_t, 2> tx_pdos{};
  std::array<ec_sync_info_t, 5> syncs{};
};

Master::Master(std::uint16_t slave_position, unsigned int master_index,
               const PdoLayout &layout)
    : slave_position_(slave_position), master_index_(master_index),
      layout_(layout) {}

Master::~Master() { shutdown(); }

void Master::apply_detected_pdo_layout() {
  if (master_ == nullptr) {
    return;
  }

  ec_slave_info_t slave_info{};
  if (ecrt_master_get_slave(master_, slave_position_, &slave_info) != 0 ||
      slave_info.sync_count <= kSm3) {
    return;
  }

  const bool touch_requested = layout_.has_touch_pdo;
  std::size_t extra_rx_entry_count = 0;
  ec_sync_info_t sm2{};
  if (ecrt_master_get_sync_manager(master_, slave_position_, kSm2, &sm2) !=
      0) {
    return;
  }
  for (std::uint16_t pdo_pos = 0; pdo_pos < sm2.n_pdos; ++pdo_pos) {
    ec_pdo_info_t pdo{};
    if (ecrt_master_get_pdo(master_, slave_position_, kSm2, pdo_pos, &pdo) !=
        0) {
      break;
    }
    if (pdo.index == kRxPdoMotorControlEchoIndex) {
      extra_rx_entry_count =
          std::min<std::size_t>(pdo.n_entries, kPdoJointCount);
    }
  }

  std::size_t touch_payload_count = 0;
  bool has_touch_pdo = false;
  if (touch_requested) {
    ec_sync_info_t sm3{};
    if (ecrt_master_get_sync_manager(master_, slave_position_, kSm3, &sm3) !=
        0) {
      return;
    }
    for (std::uint16_t pdo_pos = 0; pdo_pos < sm3.n_pdos; ++pdo_pos) {
      ec_pdo_info_t pdo{};
      if (ecrt_master_get_pdo(master_, slave_position_, kSm3, pdo_pos, &pdo) !=
          0) {
        break;
      }
      if (pdo.index != kTxPdoTouchSensorDataIndex) {
        continue;
      }
      has_touch_pdo = true;
      for (std::uint16_t entry_pos = 0; entry_pos < pdo.n_entries;
           ++entry_pos) {
        ec_pdo_entry_info_t entry{};
        if (ecrt_master_get_pdo_entry(master_, slave_position_, kSm3, pdo_pos,
                                      entry_pos, &entry) != 0) {
          break;
        }
        if (entry.index == kTouchSensorDataObjectIndex &&
            entry.bit_length == 16) {
          ++touch_payload_count;
        }
      }
    }
  }

  layout_.extra_rx_pdo_entry_count = extra_rx_entry_count;
  layout_.touch_packet_capacity =
      std::min<std::size_t>(touch_payload_count, kTouchPacketCapacity);
  layout_.touch_input_process_data_size =
      sizeof(std::uint16_t) * (2 + layout_.touch_packet_capacity);
  layout_.has_touch_pdo = has_touch_pdo;
}

void Master::build_pdo_configuration() {
  pdo_ = new PdoConfiguration();
  for (std::size_t field = 0; field < 5; ++field) {
    for (std::size_t joint = 0; joint < layout_.pdo_joint_count; ++joint) {
      const auto subindex = static_cast<std::uint8_t>(joint + 1);
      pdo_->rx_entries[field * layout_.pdo_joint_count + joint] = {
          static_cast<std::uint16_t>(layout_.output_object_index + field),
          subindex, 16};
      pdo_->motor_tx_entries[field * layout_.pdo_joint_count + joint] = {
          static_cast<std::uint16_t>(layout_.motor_input_object_index + field),
          subindex, static_cast<std::uint8_t>(field == 4 ? 32U : 16U)};
    }
  }
  if (layout_.has_touch_pdo) {
    pdo_->touch_tx_entries[0] = {layout_.touch_input_object_index,
                                 layout_.touch_input_object_subindex, 16};
    pdo_->touch_tx_entries[1] = {
        static_cast<std::uint16_t>(layout_.touch_input_object_index + 1),
        layout_.touch_input_object_subindex, 16};
    for (std::size_t i = 0; i < layout_.touch_packet_capacity; ++i) {
      pdo_->touch_tx_entries[2 + i] = {
          static_cast<std::uint16_t>(layout_.touch_input_object_index + 2),
          static_cast<std::uint8_t>(i + 1), 16};
    }
  }

  pdo_->rx_pdos[0] = {layout_.rx_pdo_index,
                      static_cast<unsigned int>(layout_.pdo_joint_count * 5),
                      pdo_->rx_entries.data()};
  if (layout_.extra_rx_pdo_entry_count > 0) {
    for (std::size_t i = 0; i < layout_.extra_rx_pdo_entry_count; ++i) {
      pdo_->extra_rx_entries[i] = {
          layout_.output_object_index, static_cast<std::uint8_t>(i + 1), 16};
    }
    pdo_->rx_pdos[1] = {
        layout_.extra_rx_pdo_index,
        static_cast<unsigned int>(layout_.extra_rx_pdo_entry_count),
        pdo_->extra_rx_entries.data()};
  }
  pdo_->tx_pdos[0] = {layout_.motor_tx_pdo_index,
                      static_cast<unsigned int>(layout_.pdo_joint_count * 5),
                      pdo_->motor_tx_entries.data()};
  pdo_->tx_pdos[1] = {
      layout_.touch_tx_pdo_index,
      static_cast<unsigned int>(layout_.has_touch_pdo
                                    ? 2 + layout_.touch_packet_capacity
                                    : 0),
      layout_.has_touch_pdo ? pdo_->touch_tx_entries.data() : nullptr};
  const unsigned int tx_pdo_count = layout_.has_touch_pdo ? 2U : 1U;
  const unsigned int rx_pdo_count =
      layout_.extra_rx_pdo_entry_count > 0 ? 2U : 1U;
  pdo_->syncs[0] = {kSm0, EC_DIR_OUTPUT, 0, nullptr, EC_WD_DISABLE};
  pdo_->syncs[1] = {kSm1, EC_DIR_INPUT, 0, nullptr, EC_WD_DISABLE};
  pdo_->syncs[2] = {kSm2, EC_DIR_OUTPUT, rx_pdo_count,
                    pdo_->rx_pdos.data(), EC_WD_ENABLE};
  pdo_->syncs[3] = {kSm3, EC_DIR_INPUT, tx_pdo_count,
                    pdo_->tx_pdos.data(), EC_WD_DISABLE};
  pdo_->syncs[4] = {kSyncInfoTerminator, EC_DIR_INVALID, 0, nullptr,
                    EC_WD_DEFAULT};
}

bool Master::initialize(std::string *error) {
  if (domain_ != nullptr) {
    return true;
  }
  if (!initialize_sdo(error)) {
    return false;
  }
  apply_detected_pdo_layout();
  if (!is_valid_pdo_layout(layout_)) {
    if (error != nullptr) {
      *error = std::string("invalid PDO layout: ") +
               (layout_.name == nullptr ? "<unnamed>" : layout_.name);
    }
    return false;
  }
  if (dc_config_.enabled &&
      (dc_config_.assign_activate == 0 || dc_config_.sync0_cycle_ns == 0)) {
    if (error != nullptr) {
      *error = "DC requires non-zero assign_activate and Sync0 cycle";
    }
    return false;
  }
  domain_ = ecrt_master_create_domain(master_);
  if (domain_ == nullptr) {
    if (error != nullptr) {
      *error = "ecrt_master_create_domain failed";
    }
    shutdown();
    return false;
  }
  slave_config_ = ecrt_master_slave_config(master_, kMasterAlias,
                                            slave_position_, kVendorId,
                                            kProductCode);
  if (slave_config_ == nullptr) {
    if (error != nullptr) {
      *error = "Revo3 slave configuration was not found";
    }
    shutdown();
    return false;
  }

  for (std::size_t i = 0; i < layout_.motor_count; ++i) {
    std::array<std::uint8_t, 2> bytes{};
    std::size_t result_size = 0;
    std::uint32_t abort_code = 0;
    const int result = ecrt_master_sdo_upload(
        master_, slave_position_, kJointActualPositionArrayIndex,
        static_cast<std::uint8_t>(i + 1), bytes.data(), bytes.size(),
        &result_size, &abort_code);
    if (result != 0 || result_size != bytes.size()) {
      command_.position[i] = 0;
      continue;
    }
    command_.position[i] = EC_READ_U16(bytes.data());
  }
  outputs_initialized_ = true;

  build_pdo_configuration();
  const int pdo_result =
      ecrt_slave_config_pdos(slave_config_, EC_END, pdo_->syncs.data());
  if (pdo_result != 0) {
    if (error != nullptr) {
      *error = operation_error("ecrt_slave_config_pdos", pdo_result);
    }
    shutdown();
    return false;
  }

  if (dc_config_.enabled) {
    ecrt_slave_config_dc(slave_config_, dc_config_.assign_activate,
                         dc_config_.sync0_cycle_ns,
                         dc_config_.sync0_shift_ns,
                         dc_config_.sync1_cycle_ns,
                         dc_config_.sync1_shift_ns);
  }

  std::array<ec_pdo_entry_reg_t, 4> registrations{};
  registrations[0] = {kMasterAlias, slave_position_, kVendorId, kProductCode,
                      layout_.output_object_index,
                      layout_.output_object_subindex, &output_offset_,
                      nullptr};
  registrations[1] = {kMasterAlias, slave_position_, kVendorId, kProductCode,
                      layout_.motor_input_object_index,
                      layout_.motor_input_object_subindex,
                      &motor_input_offset_, nullptr};
  if (layout_.has_touch_pdo) {
    registrations[2] = {kMasterAlias, slave_position_, kVendorId,
                        kProductCode,
                        layout_.touch_input_object_index,
                        layout_.touch_input_object_subindex,
                        &touch_input_offset_, nullptr};
  }
  const int registration_result =
      ecrt_domain_reg_pdo_entry_list(domain_, registrations.data());
  if (registration_result != 0) {
    if (error != nullptr) {
      *error = operation_error("ecrt_domain_reg_pdo_entry_list",
                               registration_result);
    }
    shutdown();
    return false;
  }
  return true;
}

bool Master::initialize_sdo(std::string *error) {
  if (master_ != nullptr) {
    return true;
  }
  master_ = ecrt_request_master(master_index_);
  if (master_ == nullptr) {
    if (error != nullptr) {
      *error = "ecrt_request_master failed";
    }
    return false;
  }
  return true;
}

bool Master::activate(std::string *error) {
  if (domain_ == nullptr && !initialize(error)) {
    return false;
  }
  if (dc_config_.enabled) {
    ecrt_master_application_time(master_, monotonic_time_ns());
  }
  const int result = ecrt_master_activate(master_);
  if (result != 0) {
    if (error != nullptr) {
      *error = operation_error("ecrt_master_activate", result);
    }
    return false;
  }
  domain_data_ = ecrt_domain_data(domain_);
  if (domain_data_ == nullptr) {
    if (error != nullptr) {
      *error = "ecrt_domain_data returned null";
    }
    return false;
  }
  active_ = true;
  return true;
}

bool Master::wait_for_operational(unsigned int timeout_ms,
                                  std::uint64_t cycle_period_ns,
                                  std::string *error) {
  if (master_ == nullptr) {
    if (error != nullptr) {
      *error = "master is not initialized";
    }
    return false;
  }
  const auto deadline =
      std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
  if (cycle_period_ns == 0) {
    cycle_period_ns = kDefaultOpCyclePeriodNs;
  }
  ec_master_state_t master_state{};
  ec_slave_config_state_t slave_state{};
  std::uint64_t next_cycle_ns = monotonic_time_ns();
  do {
    if (active_) {
      if (!cycle(next_cycle_ns)) {
        if (error != nullptr) {
          *error = "EtherCAT process-data exchange failed while waiting for OP";
        }
        return false;
      }
    }
    ecrt_master_state(master_, &master_state);
    if (slave_config_ != nullptr) {
      ecrt_slave_config_state(slave_config_, &slave_state);
      if (slave_state.operational) {
        return true;
      }
    } else if ((master_state.al_states & kEthercatOpStateBit) != 0) {
      return true;
    }
    next_cycle_ns += cycle_period_ns;
    sleep_until_monotonic_ns(next_cycle_ns);
  } while (std::chrono::steady_clock::now() < deadline);

  if (error != nullptr) {
    std::ostringstream stream;
    stream << "EtherCAT slave did not reach OP within " << timeout_ms
           << " ms"
           << " (link=" << static_cast<int>(master_state.link_up)
           << ", responding=" << master_state.slaves_responding
           << ", master_al=0x" << std::hex
           << static_cast<int>(master_state.al_states)
           << ", slave_online=" << std::dec
           << static_cast<int>(slave_state.online)
           << ", slave_operational="
           << static_cast<int>(slave_state.operational)
           << ", slave_al=0x" << std::hex
           << static_cast<int>(slave_state.al_state) << ')';
    *error = stream.str();
  }
  return false;
}

void Master::sync_distributed_clocks(std::uint64_t application_time_ns) {
  if (!dc_config_.enabled) {
    return;
  }
  if (!dc_reference_synced_) {
    ecrt_master_sync_reference_clock_to(master_, application_time_ns);
    dc_reference_synced_ = true;
  } else {
    ecrt_master_sync_reference_clock(master_);
  }
  ecrt_master_sync_slave_clocks(master_);
}

void Master::read_process_data() {
  const std::uint8_t *motor = domain_data_ + motor_input_offset_;
  for (std::size_t i = 0; i < layout_.pdo_joint_count; ++i) {
    feedback_.status[i] =
        EC_READ_U16(motor + layout_.motor_status_offset + i * 2);
    feedback_.velocity[i] =
        EC_READ_U16(motor + layout_.motor_velocity_offset + i * 2);
    feedback_.position[i] =
        EC_READ_U16(motor + layout_.motor_position_offset + i * 2);
    feedback_.current[i] =
        EC_READ_U16(motor + layout_.motor_current_offset + i * 2);
    feedback_.error[i] =
        EC_READ_U32(motor + layout_.motor_error_offset + i * 4);
  }
  if (layout_.has_touch_pdo) {
    const std::uint8_t *touch = domain_data_ + touch_input_offset_;
    touch_packet_.index = EC_READ_U16(touch + layout_.touch_index_offset);
    touch_packet_.length = std::min<std::uint16_t>(
        EC_READ_U16(touch + layout_.touch_length_offset),
        static_cast<std::uint16_t>(layout_.touch_packet_capacity));
    for (std::size_t i = 0; i < touch_packet_.length; ++i) {
      touch_packet_.data[i] =
          EC_READ_U16(touch + layout_.touch_data_offset + i * 2);
    }
  } else {
    touch_packet_ = TouchPacket{};
  }
}

void Master::write_process_data() {
  std::uint8_t *output = domain_data_ + output_offset_;
  for (std::size_t i = 0; i < layout_.pdo_joint_count; ++i) {
    EC_WRITE_U16(output + layout_.output_velocity_offset + i * 2,
                 command_.velocity[i]);
    EC_WRITE_U16(output + layout_.output_position_offset + i * 2,
                 command_.position[i]);
    EC_WRITE_U16(output + layout_.output_current_offset + i * 2,
                 command_.current[i]);
    EC_WRITE_U16(output + layout_.output_kp_offset + i * 2, command_.kp[i]);
    EC_WRITE_U16(output + layout_.output_kd_offset + i * 2, command_.kd[i]);
  }
}

bool Master::cycle(std::uint64_t application_time_ns) {
  if (!active_) {
    return false;
  }
  if (dc_config_.enabled) {
    if (application_time_ns == 0) {
      application_time_ns = monotonic_time_ns();
    }
    if (ecrt_master_application_time(master_, application_time_ns) != 0) {
      return false;
    }
  }
  if (ecrt_master_receive(master_) < 0) {
    return false;
  }
  ecrt_domain_process(domain_);
  read_process_data();
  write_process_data();
  sync_distributed_clocks(application_time_ns);
  ecrt_domain_queue(domain_);
  return ecrt_master_send(master_) >= 0;
}

bool Master::read_sdo(std::uint16_t index, std::uint8_t subindex, void *data,
                      std::size_t capacity, std::size_t *result_size,
                      std::uint32_t *abort_code) {
  if (master_ == nullptr) {
    return false;
  }
  std::uint32_t local_abort = 0;
  const int result = ecrt_master_sdo_upload(
      master_, slave_position_, index, subindex,
      static_cast<std::uint8_t *>(data), capacity, result_size, &local_abort);
  if (abort_code != nullptr) {
    *abort_code = local_abort;
  }
  return result == 0;
}

bool Master::write_sdo(std::uint16_t index, std::uint8_t subindex,
                       const void *data, std::size_t size,
                       std::uint32_t *abort_code) {
  if (master_ == nullptr) {
    return false;
  }
  std::uint32_t local_abort = 0;
  const int result = ecrt_master_sdo_download(
      master_, slave_position_, index, subindex,
      const_cast<std::uint8_t *>(static_cast<const std::uint8_t *>(data)), size,
      &local_abort);
  if (abort_code != nullptr) {
    *abort_code = local_abort;
  }
  return result == 0;
}

void Master::shutdown() {
  domain_data_ = nullptr;
  active_ = false;
  dc_reference_synced_ = false;
  outputs_initialized_ = false;
  if (master_ != nullptr) {
    ecrt_release_master(master_);
  }
  master_ = nullptr;
  domain_ = nullptr;
  slave_config_ = nullptr;
  delete pdo_;
  pdo_ = nullptr;
}

} // namespace revo3::ethercat
