#include <revo3/revo3.hpp>

#include <chrono>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

struct Options {
  revo3::DiscoveryOptions discovery;
  bool override_ultra_vision_touch = false;
  std::string layout = "auto";
  std::vector<std::uint16_t> mx_point_counts;
};

const char *require_value(int argc, char **argv, int &index,
                          const char *option) {
  if (index + 1 >= argc) {
    throw std::invalid_argument(std::string(option) + " requires a value");
  }
  return argv[++index];
}

std::vector<std::uint16_t> parse_point_counts(const std::string &value) {
  std::vector<std::uint16_t> counts;
  std::size_t begin = 0;
  while (begin <= value.size()) {
    const auto end = value.find(',', begin);
    const auto item = value.substr(begin, end - begin);
    std::size_t consumed = 0;
    const auto count = std::stoul(item, &consumed, 0);
    if (item.empty() || consumed != item.size() || count > UINT16_MAX) {
      throw std::invalid_argument("invalid --mx-point-counts value");
    }
    counts.push_back(static_cast<std::uint16_t>(count));
    if (end == std::string::npos) {
      break;
    }
    begin = end + 1;
  }
  if (counts.size() != 11) {
    throw std::invalid_argument(
        "--mx-point-counts requires exactly 11 comma-separated values");
  }
  return counts;
}

Options parse_options(int argc, char **argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string argument = argv[index];
    if (argument == "--port") {
      options.discovery.port = require_value(argc, argv, index, "--port");
    } else if (argument == "--model") {
      const std::string value = require_value(argc, argv, index, "--model");
      if (value != "ultra-vision-touch") {
        throw std::invalid_argument("--model must be ultra-vision-touch");
      }
      options.override_ultra_vision_touch = true;
    } else if (argument == "--layout") {
      options.layout = require_value(argc, argv, index, "--layout");
      if (options.layout != "auto" && options.layout != "vision-mt" &&
          options.layout != "vision-mx") {
        throw std::invalid_argument(
            "--layout must be auto, vision-mt, or vision-mx");
      }
    } else if (argument == "--mx-point-counts") {
      options.mx_point_counts = parse_point_counts(
          require_value(argc, argv, index, "--mx-point-counts"));
    } else if (!argument.empty() && argument.front() != '-') {
      options.discovery.port = argument;
    } else {
      throw std::invalid_argument("unknown option: " + argument);
    }
  }
  return options;
}

revo3::TouchLayout build_vision_array_layout(
    const std::string &layout_name,
    const std::vector<std::uint16_t> &mx_point_counts) {
  revo3::TouchLayout layout;
  const std::uint16_t physical_ids[] = {2, 4, 6, 8, 10};
  const std::uint16_t mt_point_counts[] = {57, 52, 52, 52, 52};
  if (layout_name == "vision-mx" && mx_point_counts.size() != 11) {
    throw std::invalid_argument(
        "vision-mx requires --mx-point-counts for physical modules 0..10");
  }
  for (std::uint8_t index = 0; index < 5; ++index) {
    const auto physical_id = physical_ids[index];
    const auto point_count = layout_name == "vision-mt"
                                 ? mt_point_counts[index]
                                 : mx_point_counts[physical_id];
    revo3::TouchModuleLayout module{};
    module.module_id = physical_id;
    module.region = revo3::TouchRegion::FingerPad;
    module.region_index = index;
    module.signals = {revo3::TouchSignal::TouchPoint};
    module.point_count = point_count;
    module.layout_id = layout_name == "vision-mt"
                           ? (index == 0 ? "mt_thumbpad_57"
                                         : "mt_fingerpad_52")
                           : "mx_fingerpad_" + std::to_string(point_count);
    layout.modules.push_back(std::move(module));
  }
  revo3::TouchModuleLayout palm{};
  palm.module_id = 0;
  palm.region = revo3::TouchRegion::Palm;
  palm.region_index = 0;
  palm.signals = {revo3::TouchSignal::TouchPoint};
  palm.point_count =
      layout_name == "vision-mt" ? 36 : mx_point_counts.front();
  palm.layout_id = layout_name == "vision-mt"
                       ? "mt_palm_36"
                       : "mx_palm_" + std::to_string(palm.point_count);
  layout.modules.push_back(std::move(palm));
  return layout;
}

}  // namespace

int main(int argc, char **argv) {
  revo3::init_logging(LOG_LEVEL_INFO, true);
  using namespace std::chrono_literals;

  try {
    const auto options = parse_options(argc, argv);

    revo3::Manager manager;
    auto devices = manager.discover(options.discovery);
    if (devices.empty()) {
      throw revo3::SdkError("no Revo3 hand found");
    }
    auto detected = devices.front();
    if (options.override_ultra_vision_touch) {
      detected.model =
          static_cast<Revo3Model>(REVO3_MODEL_ULTRA_VISION_TOUCH);
    }
    auto hand = manager.connect(detected);

    auto touch = hand.touch();
    if (options.layout != "auto") {
      touch.set_layout(
          build_vision_array_layout(options.layout, options.mx_point_counts));
      std::printf("Applied model/layout override: UltraVisionTouch + %s\n",
                  options.layout.c_str());
    }
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
    bool has_mt = false;
    bool has_mx = false;
    for (const auto &module : layout.modules) {
      std::printf("  module=%u region=%u[%u] points=%u layout=%s signals=%zu\n",
                  module.module_id, static_cast<unsigned>(module.region),
                  module.region_index, module.point_count,
                  module.layout_id.c_str(), module.signals.size());
      has_mt = has_mt || module.layout_id.rfind("mt_", 0) == 0;
      has_mx = has_mx || module.layout_id.rfind("mx_", 0) == 0;
    }
    std::printf("Enabled mask: 0x%04x\n", touch.enabled_mask());
    if (has_mt) {
      std::printf("Read mode: %u\n",
                  static_cast<unsigned>(touch.read_mode()));
    }
    if (has_mt || has_mx) {
      std::printf("Value mode: %u\n",
                  static_cast<unsigned>(touch.value_mode()));
    }

    if (!layout.modules.empty()) {
      const auto first_id = static_cast<std::uint8_t>(layout.modules.front().module_id);
      const auto single = touch.module_snapshot(first_id);
      std::printf("Single-module snapshot: module=%u state=%u\n",
                  single.module_id,
                  static_cast<unsigned>(single.sample_state));

      std::vector<std::uint8_t> selected_ids{first_id};
      if (layout.modules.size() > 1) {
        selected_ids.push_back(
            static_cast<std::uint8_t>(layout.modules.back().module_id));
      }
      const auto selected = touch.snapshot(selected_ids);
      std::printf("Selected snapshot: modules=%zu\n", selected.modules.size());
    }

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
