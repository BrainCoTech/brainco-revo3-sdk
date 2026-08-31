#include <revo3/revo3.hpp>

#include <chrono>
#include <cstdio>
#include <cstring>

int main(int argc, char **argv) {
  revo3::init_logging(LOG_LEVEL_INFO, true);
  using namespace std::chrono_literals;

  try {
    revo3::DiscoveryOptions discovery;
    if (argc > 1) {
      discovery.port = argv[1];
    }

    revo3::Manager manager;
    auto hand = manager.connect_auto(discovery);

    auto touch = hand.touch();
    const auto layout = touch.layout();
    std::printf("Touch modules: %zu regions=%zu\n", layout.modules.size(),
                layout.regions.size());
    for (const auto &region : layout.regions) {
      std::printf("  region=%u modules=%zu module_ids:",
                  static_cast<unsigned>(region.region),
                  region.module_ids.size());
      for (const auto module_id : region.module_ids) {
        std::printf(" %u", module_id);
      }
      std::printf("\n");
    }
    for (const auto &module : layout.modules) {
      std::printf("  module=%u region=%u[%u] points=%u layout=%s signals=%zu\n",
                  module.module_id, static_cast<unsigned>(module.region),
                  module.region_index, module.point_count,
                  module.layout_id.c_str(), module.signals.size());
    }
    std::printf("Enabled mask: 0x%04x\n", touch.enabled_mask());
    std::printf("Read mode: %u value mode: %u\n",
                static_cast<unsigned>(touch.read_mode()),
                static_cast<unsigned>(touch.value_mode()));

    auto subscription = touch.subscribe(20ms);
    for (int index = 0; index < 3; ++index) {
      const auto frame = subscription.next();
      std::printf("Frame %llu: modules=%zu\n",
                  static_cast<unsigned long long>(frame.sequence),
                  frame.modules.size());
      if (!frame.modules.empty()) {
        const auto &module = frame.modules.front();
        std::printf("  first module id=%u state=%u points=%zu resultant_force=%.1f mN\n",
                    module.module_id, static_cast<unsigned>(module.sample_state),
                    module.points.size(),
                    module.has_resultant_force ? module.resultant_force_mn : 0.0F);
      }
    }
    subscription.close();

    const auto statistics = hand.statistics();
    std::printf("Runtime statistics: touch_reads=%llu failed_operations=%llu\n",
                static_cast<unsigned long long>(statistics.touch_reads),
                static_cast<unsigned long long>(statistics.failed_operations));
    return 0;
  } catch (const revo3::SdkError &error) {
    std::fprintf(stderr, "Revo3 error: %s\n", error.what());
    return 1;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Error: %s\n", error.what());
    return 1;
  }
}
