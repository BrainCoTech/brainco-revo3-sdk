#include "revo3_ethercat.hpp"

#include <cassert>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace {

bool close(float lhs, float rhs) { return std::fabs(lhs - rhs) < 0.001f; }

} // namespace

int main() {
  using namespace revo3::ethercat;

  assert(close(position_raw_to_deg(position_deg_to_raw(90.25f)), 90.25f));
  assert(close(position_raw_to_deg(position_deg_to_raw(-12.5f)), -12.5f));
  assert(close(velocity_raw_to_rpm(velocity_rpm_to_raw(-50.0f)), -50.0f));
  assert(close(current_raw_to_ma(current_ma_to_raw(-1250.0f)), -1250.0f));
  assert(close(gain_raw_to_value(gain_value_to_raw(3.25f)), 3.25f));

  bool rejected = false;
  try {
    (void)position_deg_to_raw(std::numeric_limits<float>::infinity());
  } catch (const std::invalid_argument &) {
    rejected = true;
  }
  assert(rejected);

  rejected = false;
  try {
    (void)velocity_rpm_to_raw(1000.0f);
  } catch (const std::out_of_range &) {
    rejected = true;
  }
  assert(rejected);
}
