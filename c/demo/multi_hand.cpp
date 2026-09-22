#include <revo3/revo3.hpp>

#include <algorithm>
#include <cstdio>
#include <map>
#include <string>
#include <utility>
#include <vector>

int main() {
  revo3::init_logging(LOG_LEVEL_INFO, true);
  try {
    revo3::Manager manager;
    revo3::DiscoveryOptions options;
    options.scan_all = true;
    const auto detected = manager.discover(options);
    if (detected.empty()) {
      std::fprintf(stderr, "No Revo3 hands found\n");
      return 2;
    }

    std::map<std::pair<int, std::string>, std::vector<revo3::DetectedDevice>> groups;
    for (const auto &device : detected) {
      groups[{static_cast<int>(device.protocol_type), device.port_name}].push_back(device);
    }
    const auto shared = std::find_if(
        groups.begin(), groups.end(),
        [](const auto &entry) { return entry.second.size() >= 2; });
    if (shared == groups.end()) {
      std::fprintf(
          stderr,
          "At least two Revo3 hands on the same transport port are required; "
          "multiple CANFD adapter channels cannot share one process\n");
      return 2;
    }

    const auto &selected = shared->second;
    auto hands = manager.connect_all(selected);
    for (std::size_t index = 0; index < hands.size(); ++index) {
      const auto info = hands[index].device_info();
      std::printf("Hand %zu: SN=%s port=%s slave=%u\n", index,
                  info.serial_number.c_str(), selected[index].port_name.c_str(),
                  selected[index].slave_id);
    }

    if (hands.size() > 1) {
      hands.front().close();
      const auto state = hands[1].state().snapshot();
      std::printf("Closed Hand 0; Hand 1 still reads J0=%.2f degree\n",
                  state.motors.positions_deg[0]);
    }
    return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Error: %s\n", error.what());
    return 1;
  }
}
