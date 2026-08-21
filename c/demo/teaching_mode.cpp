#include <revo3/revo3.hpp>

#include <chrono>
#include <cstdio>
#include <cstring>

int main(int argc, char **argv) {
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
    std::fprintf(stderr, "Teaching changes motor control; pass --move to continue.\n");
    return 2;
  }

  try {
    revo3::Manager manager;
    auto hand = manager.connect_auto(discovery);
    std::printf("Recording for 5 seconds; move the hand manually.\n");
    const auto trajectory = hand.motion().teach_hand(5s, 10ms);
    std::printf("Recorded %zu frames. Replaying now.\n", trajectory.size());
    hand.motion().replay_hand(trajectory, 10ms, 1.0F, 0.1F);
    std::printf("Replay completed.\n");
    return 0;
  } catch (const std::exception &error) {
    std::fprintf(stderr, "Error: %s\n", error.what());
    return 1;
  }
}
