#include <revo3/revo3.hpp>

#include <cstdio>

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

    auto hands = manager.connect_all(detected);
    for (std::size_t index = 0; index < hands.size(); ++index) {
      const auto info = hands[index].device_info();
      std::printf("Hand %zu: SN=%s port=%s slave=%u\n", index,
                  info.serial_number.c_str(), detected[index].port_name.c_str(),
                  detected[index].slave_id);
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
