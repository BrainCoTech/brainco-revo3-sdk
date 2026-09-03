#include <revo3/revo3.hpp>

#include <chrono>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

static revo3::TouchLayout build_hp_mt_layout() {
  revo3::TouchLayout layout;
  std::vector<revo3::TouchSignal> hp_signals = {
      revo3::TouchSignal::TouchPoint,     revo3::TouchSignal::Force3D,
      revo3::TouchSignal::Torque2D,       revo3::TouchSignal::ResultantForce,
  };
  // 5 HP Fingertips (module_id: 1, 3, 5, 7, 9)
  for (uint8_t i = 0; i < 5; ++i) {
    revo3::TouchModuleLayout mod{};
    mod.layout_id = "hp_fingertip_48";
    mod.module_id = i * 2 + 1;
    mod.region = revo3::TouchRegion::Fingertip;
    mod.region_index = i;
    mod.signals = hp_signals;
    mod.point_count = 48;
    layout.modules.push_back(mod);
  }
  // 5 MT FingerPads (module_id: 2, 4, 6, 8, 10)
  uint16_t mt_pad_counts[5] = {57, 52, 52, 52, 52};
  for (uint8_t i = 0; i < 5; ++i) {
    revo3::TouchModuleLayout mod{};
    mod.layout_id = (i == 0) ? "mt_thumbpad_57" : "mt_fingerpad_52";
    mod.module_id = (i + 1) * 2;
    mod.region = revo3::TouchRegion::FingerPad;
    mod.region_index = i;
    mod.signals = {revo3::TouchSignal::TouchPoint};
    mod.point_count = mt_pad_counts[i];
    layout.modules.push_back(mod);
  }
  // 1 MT Palm (module_id: 0)
  {
    revo3::TouchModuleLayout mod{};
    mod.layout_id = "mt_palm_36";
    mod.module_id = 0;
    mod.region = revo3::TouchRegion::Palm;
    mod.region_index = 0;
    mod.signals = {revo3::TouchSignal::TouchPoint};
    mod.point_count = 36;
    layout.modules.push_back(mod);
  }
  return layout;
}

int main(int argc, char **argv) {
  using namespace std::chrono_literals;
  revo3::init_logging(LOG_LEVEL_INFO, true);

  try {
    revo3::DiscoveryOptions discovery;
    bool test_tare = false;
    for (int index = 1; index < argc; ++index) {
      if (std::strcmp(argv[index], "--test-tare") == 0) {
        test_tare = true;
      } else {
        discovery.port = argv[index];
      }
    }

    std::printf("=================================================================\n");
    std::printf("      Revo3 C++ SDK HP + MT Hybrid Touch Verification Demo       \n");
    std::printf("=================================================================\n");

    revo3::Manager manager;
    auto hand = manager.connect_auto(discovery);
    const auto info = hand.device_info();
    std::printf("[OK] Connected to %s (Model: %u)\n", info.serial_number.c_str(),
                static_cast<unsigned>(info.model));

    auto touch = hand.touch();
    const auto value_mode = touch.value_mode();
    const char *point_unit =
        value_mode == revo3::TouchValueMode::Force ? "mN" : "ADC";

    // 1. Set HP + MT Hybrid Layout
    std::printf("\n--- 1. Setting HP + MT Hybrid Layout (11 Modules) ---\n");
    touch.set_layout(build_hp_mt_layout());
    const auto active_layout = touch.layout();
    std::printf("[OK] Registered layout with %zu modules, %zu regions\n",
                active_layout.modules.size(), active_layout.regions.size());

    // 2. Query Enabled Mask
    std::printf("\n--- 2. Querying Touch Module Enabled Mask ---\n");
    const auto mask = touch.enabled_mask();
    std::printf("[OK] Enabled Mask: 0x%04X\n", mask);

    // 3. Read 3 Snapshots
    std::printf("\n--- 3. Reading 3 Hybrid Touch Snapshots ---\n");
    const char *finger_names[5] = {"Thumb", "Index", "Middle", "Ring", "Pinky"};
    for (int frame_idx = 1; frame_idx <= 3; ++frame_idx) {
      const auto frame = touch.snapshot();
      std::printf("[Snapshot #%02d] Sequence: %llu, Modules: %zu\n", frame_idx,
                  static_cast<unsigned long long>(frame.sequence),
                  frame.modules.size());
      for (const auto &m : frame.modules) {
        if (m.layout_id.rfind("hp_", 0) == 0) {
          const char *fname = (m.region_index < 5) ? finger_names[m.region_index] : "Tip";
          std::printf("  [%-6s Tip] ID=%2u | Fx=%+7.1f Fy=%+7.1f Fz=%+7.1f mN | Mx=%+6.4f My=%+6.4f Nm | Fn=%7.1f mN | Pts=%zu\n",
                      fname, m.module_id,
                      m.has_force3d ? m.force3d.x : 0.0F,
                      m.has_force3d ? m.force3d.y : 0.0F,
                      m.has_force3d ? m.force3d.z : 0.0F,
                      m.has_torque2d ? m.torque2d.x : 0.0F,
                      m.has_torque2d ? m.torque2d.y : 0.0F,
                      m.has_resultant_force ? m.resultant_force_mn : 0.0F,
                      m.points.size());
        } else {
          uint16_t peak = 0;
          for (auto p : m.points) {
            if (p > peak) peak = p;
          }
          std::printf("  [Mod %2u %-18s] Pts=%2zu | Peak=%4u %s\n",
                      m.module_id, m.layout_id.c_str(), m.points.size(), peak,
                      point_unit);
        }
      }
      std::this_thread::sleep_for(50ms);
    }

    // 4. Touch Pull Subscription (20 frames @ 20ms)
    std::printf("\n--- 4. Testing Touch Pull Subscription (20 frames @ 20ms) ---\n");
    auto subscription = touch.subscribe(20ms);
    for (int i = 1; i <= 20; ++i) {
      const auto frame = subscription.next();
      if (i == 1 || i == 10 || i == 20) {
        std::printf("  [Sub Frame #%02d] Seq=%llu, Total Modules=%zu\n", i,
                    static_cast<unsigned long long>(frame.sequence),
                    frame.modules.size());
      }
    }
    subscription.close();
    std::printf("[OK] Subscription closed successfully.\n");

    // 5. Zero / Tare (explicit opt-in because this changes calibration state)
    if (test_tare) {
      std::printf("\n--- 5. Testing Zero / Tare ---\n");
      touch.tare();
      std::printf("[OK] Global tare sent successfully.\n");
      std::this_thread::sleep_for(100ms);
    } else {
      std::printf("\n--- 5. Zero / Tare skipped (pass --test-tare to enable) ---\n");
    }

    const auto stats = hand.statistics();
    std::printf("\n--- 6. Runtime Statistics ---\n");
    std::printf("  Touch reads:       %llu\n", static_cast<unsigned long long>(stats.touch_reads));
    std::printf("  Failed operations: %llu\n", static_cast<unsigned long long>(stats.failed_operations));

    std::printf("\n=================================================================\n");
    std::printf("       [SUCCESS] Revo3 C++ Hybrid Touch Verification Completed!  \n");
    std::printf("=================================================================\n");
    return 0;
  } catch (const revo3::SdkError &error) {
    std::fprintf(stderr, "Revo3 error: %s\n", error.what());
    return 1;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Error: %s\n", error.what());
    return 1;
  }
}
