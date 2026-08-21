#include <revo3/revo3.hpp>

#include <chrono>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <thread>
#include <vector>

namespace {

enum class MoveScope { None, Hand, Joint, Finger, Thumb };
constexpr std::uint8_t kSafetyRecoveryRequired = 1;
constexpr std::uint8_t kSafetyFaulted = 2;

const char *model_name(Revo3Model model) {
  switch (model) {
  case REVO3_MODEL_ULTRA:
    return "Revo3 Ultra";
  case REVO3_MODEL_ULTRA_TOUCH:
    return "Revo3 Ultra Touch";
  case REVO3_MODEL_ULTRA_VISION_TOUCH:
    return "Revo3 Ultra VisionTouch";
  case REVO3_MODEL_PRO:
    return "Revo3 Pro";
  case REVO3_MODEL_PRO_TOUCH:
    return "Revo3 Pro Touch";
  case REVO3_MODEL_BASIC:
    return "Revo3 Basic";
  case REVO3_MODEL_BASIC_TOUCH:
    return "Revo3 Basic Touch";
  default:
    return "Revo3";
  }
}

bool health_has_fault(const revo3::HealthSnapshot &health) {
  return health.safety_state == kSafetyRecoveryRequired ||
         health.safety_state == kSafetyFaulted || health.system_state != 0 ||
         health.system_error_code != 0 || health.faulted_motor_count != 0;
}

const char *operation_state_name(revo3::OperationState state) {
  switch (state) {
  case revo3::OperationState::Pending:
    return "Pending";
  case revo3::OperationState::Running:
    return "Running";
  case revo3::OperationState::Succeeded:
    return "Succeeded";
  case revo3::OperationState::Cancelled:
    return "Cancelled";
  case revo3::OperationState::Preempted:
    return "Preempted";
  case revo3::OperationState::Failed:
    return "Failed";
  case revo3::OperationState::Indeterminate:
    return "Indeterminate";
  }
  return "Unknown";
}

}  // namespace

int main(int argc, char **argv) {
  using namespace std::chrono_literals;

  try {
    revo3::DiscoveryOptions discovery;
    MoveScope move_scope = MoveScope::None;
    bool allow_unhealthy = false;
    for (int index = 1; index < argc; ++index) {
      if (std::strcmp(argv[index], "--help") == 0 || std::strcmp(argv[index], "-h") == 0) {
        std::printf(
            "Usage: %s [--port <name>] [--move | --move-joint | --move-finger | --move-thumb] "
            "[--strict-health | --allow-unhealthy]\n\n"
            "Options:\n"
            "  --port <name>      Optional serial or CAN port (e.g. /dev/ttyUSB0)\n"
            "  --move             Move the whole hand (4-finger flex & return)\n"
            "  --move-joint       Move a single joint (joint 0)\n"
            "  --move-finger      Move a single finger (index finger)\n"
            "  --move-thumb       Move the thumb\n"
            "  --strict-health    Refuse motion when Health/State reports fault (default)\n"
            "  --allow-unhealthy  Allow motion despite Health/State warnings\n",
            argv[0]);
        return 0;
      } else if (std::strcmp(argv[index], "--port") == 0 && index + 1 < argc) {
        discovery.port = argv[++index];
      } else if (std::strcmp(argv[index], "--move") == 0) {
        move_scope = MoveScope::Hand;
      } else if (std::strcmp(argv[index], "--move-joint") == 0) {
        move_scope = MoveScope::Joint;
      } else if (std::strcmp(argv[index], "--move-finger") == 0) {
        move_scope = MoveScope::Finger;
      } else if (std::strcmp(argv[index], "--move-thumb") == 0) {
        move_scope = MoveScope::Thumb;
      } else if (std::strcmp(argv[index], "--strict-health") == 0) {
        allow_unhealthy = false;
      } else if (std::strcmp(argv[index], "--allow-unhealthy") == 0) {
        allow_unhealthy = true;
      } else {
        discovery.port = argv[index];
      }
    }

    revo3::Manager manager;
    auto hand = manager.connect_auto(discovery);

    const auto device_info = hand.device_info();
    const auto firmware_info = hand.firmware_info();
    const auto layout = hand.joint_layout();
    if (!layout) {
      throw std::runtime_error("Joint layout is unavailable");
    }

    std::printf("Device:   %s (%s)\n",
                device_info.serial_number.empty() ? "unknown" : device_info.serial_number.c_str(),
                device_info.hand_side == revo3::HandSide::Right ? "Right" : "Left");
    std::printf("Slave ID: %u\n", hand.slave_id());
    std::printf("Model: %s | Hardware revision: %s | Firmware: %s\n",
                model_name(static_cast<Revo3Model>(device_info.model)),
                device_info.hardware_revision.empty() ? "unknown" : device_info.hardware_revision.c_str(),
                firmware_info.controller_firmware_version.empty() ? "unknown" : firmware_info.controller_firmware_version.c_str());
    std::printf("Layout:   %s (%u DOF)\n\n", layout->layout_id.c_str(),
                layout->joint_count);

    const auto state = hand.state().snapshot();
    std::printf("State received: J0=%.2f degree, J0 velocity=%.2f rpm, "
                "J0 current=%.2f mA\n",
                state.motors.positions_deg[0], state.motors.velocities_rpm[0],
                state.motors.currents_ma[0]);
    const auto health = hand.health().snapshot();
    std::printf("Health: system_state=%u system_error=%u faulted_motor_count=%u\n",
                health.system_state, health.system_error_code,
                health.faulted_motor_count);

    if (move_scope != MoveScope::None) {
      const bool health_fault = health_has_fault(health);
      if (!allow_unhealthy && health_fault) {
        throw std::runtime_error(
            "Refusing to move because strict Health preflight found a fault");
      }
      if (health_fault) {
        std::printf("Warning: Health preflight found safety=%u "
                    "system_state=%u system_error=%u faulted_motor_count=%u; "
                    "continuing because --allow-unhealthy is set.\n",
                    health.safety_state, health.system_state,
                    health.system_error_code, health.faulted_motor_count);
      }
      if (layout->joint_count != 21) {
        throw std::runtime_error("Motion currently requires a 21-joint layout");
      }

      if (move_scope == MoveScope::Hand) {
        std::printf("Phase 1: Flexing fingers to 45.0 deg...\n");
        std::vector<float> flex_targets(
            state.motors.positions_deg,
            state.motors.positions_deg + layout->joint_count);
        for (int joint : {1, 2, 5, 6, 9, 10, 13, 14}) {
          flex_targets[static_cast<std::size_t>(joint)] = 45.0F;
        }
        auto motion1 = hand.motion().move_to(flex_targets, 1500ms);
        const auto res1 = motion1.wait(5s);
        std::printf("Motion 1 (Flex): %s (%d)\n", operation_state_name(res1),
                    static_cast<int>(res1));
        if (res1 != revo3::OperationState::Succeeded) {
          return 1;
        }

        std::this_thread::sleep_for(500ms);

        std::printf("Phase 2: Returning fingers to their initial positions...\n");
        std::vector<float> extend_targets(
            state.motors.positions_deg,
            state.motors.positions_deg + layout->joint_count);
        auto motion2 = hand.motion().move_to(extend_targets, 1500ms);
        const auto res2 = motion2.wait(5s);
        std::printf("Motion 2 (Return): %s (%d)\n",
                    operation_state_name(res2), static_cast<int>(res2));
        if (res2 != revo3::OperationState::Succeeded) {
          return 1;
        }
      } else {
        revo3::OperationHandle motion;
        if (move_scope == MoveScope::Joint) {
          motion = hand.motion().move_joint(0, 30.0F, 1500ms);
        } else if (move_scope == MoveScope::Finger) {
          motion = hand.motion().flex_finger(1, 30.0F, 1500ms);
        } else if (move_scope == MoveScope::Thumb) {
          std::vector<float> targets(state.motors.positions_deg + 16,
                                     state.motors.positions_deg + 21);
          targets[1] = 30.0F;
          targets[2] = 30.0F;
          targets[4] = 30.0F;
          motion = hand.motion().move_thumb(targets, 1500ms);
        }
        const auto result = motion.wait(5s);
        std::printf("Motion state: %s (%d)\n", operation_state_name(result),
                    static_cast<int>(result));
        if (result != revo3::OperationState::Succeeded) {
          return 1;
        }
      }
    }

    // Explicit close is optional. RAII closes Hand and Manager on scope exit.
    hand.close();
    return 0;
  } catch (const revo3::SdkError &error) {
    std::fprintf(stderr, "Revo3 error: %s (effect=%u, recovery=%u)\n",
                 error.what(), static_cast<unsigned>(error.operation_effect()),
                 static_cast<unsigned>(error.recovery_requirement()));
    return 1;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Error: %s\n", error.what());
    return 1;
  }
}
