#include <revo3/revo3.hpp>

#include <atomic>
#include <chrono>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <thread>
#include <vector>

namespace {
std::atomic<bool> g_running{true};
void signal_handler(int) { g_running = false; }
}

int main(int argc, char **argv) {
  revo3::init_logging(LOG_LEVEL_INFO, true);
  std::signal(SIGINT, signal_handler);
  using namespace std::chrono_literals;

  bool run = false;
  revo3::DiscoveryOptions discovery;
  for (int index = 1; index < argc; ++index) {
    if (std::strcmp(argv[index], "--move") == 0 || std::strcmp(argv[index], "--run") == 0) {
      run = true;
    } else {
      discovery.port = argv[index];
    }
  }
  if (!run) {
    std::fprintf(stderr,
                 "Pass --move after checking the work area and independent "
                 "stop path\n");
    return 2;
  }

  try {
    revo3::Manager manager;
    auto hand = manager.connect_auto(discovery);
    const auto layout = hand.joint_layout();
    if (!layout) {
      throw std::runtime_error("Joint layout is unavailable");
    }
    const auto state = hand.state().snapshot();
    std::vector<float> hold(state.motors.positions_deg,
                            state.motors.positions_deg + layout->joint_count);

    auto session = hand.motion().open_servo();
    const auto deadline = std::chrono::steady_clock::now() + 1s;
    // Break loop gracefully on SIGINT (Ctrl+C)
    while (g_running && std::chrono::steady_clock::now() < deadline) {
      session.send_position(hold);
      std::this_thread::sleep_for(20ms);
    }
    std::printf("Servo session state before close: %d\n",
                static_cast<int>(session.state()));
    session.close();
    return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Error: %s\n", error.what());
    return 1;
  }
}
