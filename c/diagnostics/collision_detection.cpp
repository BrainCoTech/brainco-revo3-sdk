#include <revo3/revo3.hpp>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>

int main(int argc, char **argv) {
  using namespace std::chrono_literals;

  try {
    revo3::DiscoveryOptions discovery;
    std::uint16_t joint_index = 13;
    float target_position_deg = 60.0F;
    bool run_motion = false;

    for (int index = 1; index < argc; ++index) {
      if (std::strcmp(argv[index], "--run") == 0) {
        run_motion = true;
      } else if (std::strcmp(argv[index], "--port") == 0 &&
                 index + 1 < argc) {
        discovery.port = argv[++index];
      } else if (std::strcmp(argv[index], "--slave-id") == 0 &&
                 index + 1 < argc) {
        discovery.slave_id =
            static_cast<std::uint8_t>(std::strtoul(argv[++index], nullptr, 0));
      } else if (std::strcmp(argv[index], "--joint") == 0 &&
                 index + 1 < argc) {
        joint_index = static_cast<std::uint16_t>(
            std::strtoul(argv[++index], nullptr, 0));
      } else if (std::strcmp(argv[index], "--target") == 0 &&
                 index + 1 < argc) {
        target_position_deg = std::strtof(argv[++index], nullptr);
      }
    }

    if (!run_motion) {
      std::printf(
          "Collision test is disabled by default. Re-run with --run to "
          "connect and move one joint.\n");
      return 0;
    }

    revo3::Manager manager;
    auto hand = manager.connect_auto(discovery);

    revo3::ExperimentalCollisionConfig config;
    config.enabled = true;
    config.source = revo3::CollisionDetectionSource::Hybrid;
    config.strategy = revo3::CollisionProtectionStrategy::SoftStop;
    config.position_error_threshold_deg = 12.0F;
    config.current_threshold_ma = 500.0F;
    config.debounce_time = 50ms;
    config.max_cached_status_age = 50ms;
    config.auto_clear_time = 1000ms;
    hand.experimental_collision().configure(config);

    std::printf(
        "Experimental collision detection is enabled. Obstruct joint %u "
        "during motion.\n",
        joint_index);
    auto motion = hand.motion().move_joint(joint_index, target_position_deg, 3s);

    bool collision_triggered = false;
    const auto deadline = std::chrono::steady_clock::now() + 4s;
    while (std::chrono::steady_clock::now() < deadline) {
      const auto active = hand.experimental_collision().active_joints();
      if (active.at(joint_index)) {
        collision_triggered = true;
        std::printf("Collision detected on joint %u.\n", joint_index);
        motion.cancel();
        break;
      }
      std::this_thread::sleep_for(50ms);
    }

    if (!collision_triggered) {
      const auto state = motion.wait(1s);
      std::printf("No collision was detected; motion state=%d.\n",
                  static_cast<int>(state));
    }

    hand.experimental_collision().reset();
    config.enabled = false;
    hand.experimental_collision().configure(config);
    return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Collision demo failed: %s\n", error.what());
    return 1;
  }
}
