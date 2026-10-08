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
    bool run = false;
    for (int i = 1; i < argc; ++i) {
      if (!std::strcmp(argv[i], "--help") || !std::strcmp(argv[i], "-h")) {
        std::printf("Usage: %s [--port PORT] [--mode position|current|mit] [--run]\n"
                    "Default: read-only; --run may change control or hand support.\n", argv[0]);
        return 0;
      } else if (!std::strcmp(argv[i], "--port") && i + 1 < argc) {
        discovery.port = argv[++i];
      } else if (!std::strcmp(argv[i], "--mode") && i + 1 < argc) {
        mode = argv[++i];
      } else if (!std::strcmp(argv[i], "--run")) {
        run = true;
      } else {
        throw std::invalid_argument("Unknown or incomplete option");
      }
    }
    if (mode != "position" && mode != "current" && mode != "mit") {
      throw std::invalid_argument("--mode must be position, current, or mit");
    }
    revo3::Manager manager;
    auto hand = manager.connect_auto(discovery);
    const auto layout = hand.joint_layout();
    if (!layout || layout->joint_count != 21) {
      throw std::runtime_error("This example requires a 21-joint hand");
    }
    const auto state = hand.state().snapshot();
    const std::vector<float> positions(std::begin(state.motors.positions_deg),
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
    const std::vector<float> zeros(21, 0.0f);
    if (mode == "position") {
      hand.motion().set_position(positions);
    } else if (mode == "current") {
      hand.motion().set_current(zeros);
    } else {
      hand.motion().set_mit(positions, zeros, std::vector<float>(21, 1.0f),
                            std::vector<float>(21, 0.1f), zeros);
    }
    std::printf("Sent one %s command; no heartbeat or automatic resend\n", mode.c_str());
    std::printf("Firmware determines target retention; closing the link does not stop control\n");
    return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Error: %s; inspect state before retrying\n", error.what());
    return 1;
  }
}
