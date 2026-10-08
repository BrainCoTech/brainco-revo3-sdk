#include <revo3/revo3.hpp>

#include <cstdio>
#include <cstring>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

int main(int argc, char **argv) {
  try {
    revo3::DiscoveryOptions discovery;
    std::string mode = "position";
    std::string scope = "hand";
    int joint_index = 0;
    int finger_index = 1;
    bool run = false;
    for (int i = 1; i < argc; ++i) {
      if (!std::strcmp(argv[i], "--help") || !std::strcmp(argv[i], "-h")) {
        std::printf("Usage: %s [--port PORT] [--mode position|current|mit] [--scope hand|joint|finger|thumb] [--joint-index 0..20] [--finger-index 1..4] [--run]\n"
                    "Default: read-only; --run may change control or hand support.\n", argv[0]);
        return 0;
      } else if (!std::strcmp(argv[i], "--port") && i + 1 < argc) {
        discovery.port = argv[++i];
      } else if (!std::strcmp(argv[i], "--mode") && i + 1 < argc) {
        mode = argv[++i];
      } else if (!std::strcmp(argv[i], "--scope") && i + 1 < argc) {
        scope = argv[++i];
      } else if ((!std::strcmp(argv[i], "--joint-index") || !std::strcmp(argv[i], "--finger-index")) && i + 1 < argc) {
        const bool is_joint = !std::strcmp(argv[i], "--joint-index");
        const std::string text = argv[++i];
        std::size_t parsed = 0;
        const int value = std::stoi(text, &parsed);
        if (parsed != text.size()) throw std::invalid_argument("Invalid index");
        if (is_joint) joint_index = value; else finger_index = value;
      } else if (!std::strcmp(argv[i], "--run")) {
        run = true;
      } else {
        throw std::invalid_argument("Unknown or incomplete option");
      }
    }
    if (mode != "position" && mode != "current" && mode != "mit") {
      throw std::invalid_argument("--mode must be position, current, or mit");
    }
    if (scope != "hand" && scope != "joint" && scope != "finger" && scope != "thumb") {
      throw std::invalid_argument("--scope must be hand, joint, finger, or thumb");
    }
    if (joint_index < 0 || joint_index > 20 || finger_index < 1 || finger_index > 4) {
      throw std::invalid_argument("joint index must be 0..20 and finger index 1..4");
    }
    revo3::Manager manager;
    auto hand = manager.connect_auto(discovery);
    const auto layout = hand.joint_layout();
    if (!layout || layout->joint_count != 21) {
      throw std::runtime_error("This example requires a 21-joint hand");
    }
    const auto state = hand.state().snapshot();
    std::vector<float> positions(std::begin(state.motors.positions_deg),
                                       std::end(state.motors.positions_deg));
    std::printf("Current positions (deg):");
    for (float value : positions) std::printf(" %.2f", value);
    std::printf("\n");
    if (!run) {
      std::printf("Read-only: add --run to send one command\n");
      return 0;
    }
    const auto health = hand.health().snapshot();
    if (health.safety_state == 1 || health.safety_state == 2 ||
        health.system_state != 0 || health.system_error_code != 0 ||
        health.faulted_motor_count != 0) {
      throw std::runtime_error("Refusing control because health reports a fault");
    }
    if (scope == "joint") {
      positions = {positions[joint_index]};
    } else if (scope == "finger") {
      const int start = (4 - finger_index) * 4;
      positions = std::vector<float>(positions.begin() + start, positions.begin() + start + 4);
    } else if (scope == "thumb") {
      positions = std::vector<float>(positions.begin() + 16, positions.end());
    }
    const auto count = positions.size();
    const std::vector<float> zeros(count, 0.0f);
    if (scope == "hand") {
      if (mode == "position") {
        hand.motion().set_position(positions);
      }
      else if (mode == "current") {
        hand.motion().set_current(zeros);
      }
      else {
        hand.motion().set_mit(positions, zeros, std::vector<float>(count, 1.0f), std::vector<float>(count, 0.1f), zeros);
      }
    }
    else if (scope == "joint") {
      if (mode == "position") {
        hand.motion().set_joint_position(static_cast<std::uint16_t>(joint_index), positions[0]);
      }
      else if (mode == "current") {
        hand.motion().set_joint_current(static_cast<std::uint16_t>(joint_index), 0.0f);
      }
      else {
        hand.motion().set_joint_mit(static_cast<std::uint16_t>(joint_index), positions[0], 0.0f, 1.0f, 0.1f, 0.0f);
      }
    }
    else if (scope == "finger") {
      if (mode == "position") {
        hand.motion().set_finger_position(static_cast<std::uint16_t>(finger_index), positions);
      }
      else if (mode == "current") {
        hand.motion().set_finger_current(static_cast<std::uint16_t>(finger_index), zeros);
      }
      else {
        hand.motion().set_finger_mit(static_cast<std::uint16_t>(finger_index), positions, zeros, std::vector<float>(count, 1.0f), std::vector<float>(count, 0.1f), zeros);
      }
    }
    else if (scope == "thumb") {
      if (mode == "position") {
        hand.motion().set_thumb_position(positions);
      }
      else if (mode == "current") {
        hand.motion().set_thumb_current(zeros);
      }
      else {
        hand.motion().set_thumb_mit(positions, zeros, std::vector<float>(count, 1.0f), std::vector<float>(count, 0.1f), zeros);
      }
    }
    std::printf("Sent one %s %s command; no heartbeat or automatic resend\n", scope.c_str(), mode.c_str());
    std::printf("Firmware determines target retention; closing the link does not stop control\n");
    return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Error: %s; inspect state before retrying\n", error.what());
    return 1;
  }
}
