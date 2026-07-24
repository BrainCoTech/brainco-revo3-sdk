#pragma once

#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>

namespace revo3::examples {

struct MitPlanSample {
  double position = 0.0;
  double velocity_per_second = 0.0;
  std::size_t cycle_index = 0;
  bool returning = false;
  bool finished = false;
};

class RepeatingMitPlan {
public:
  RepeatingMitPlan(double start_position, double target_position,
                   double segment_duration_seconds,
                   std::size_t repeat_count)
      : start_position_(start_position), target_position_(target_position),
        segment_duration_seconds_(segment_duration_seconds),
        repeat_count_(repeat_count) {
    if (!std::isfinite(start_position_) || !std::isfinite(target_position_) ||
        !std::isfinite(segment_duration_seconds_) ||
        segment_duration_seconds_ <= 0.0 || repeat_count_ == 0 ||
        repeat_count_ > std::numeric_limits<std::size_t>::max() / 2 ||
        !std::isfinite(static_cast<double>(repeat_count_ * 2) *
                       segment_duration_seconds_)) {
      throw std::invalid_argument("invalid MIT plan configuration");
    }
  }

  MitPlanSample sample(double elapsed_seconds) const {
    if (!std::isfinite(elapsed_seconds) || elapsed_seconds <= 0.0) {
      return {start_position_, 0.0, 0, false, false};
    }

    const std::size_t segment_count = repeat_count_ * 2;
    const double total_duration =
        static_cast<double>(segment_count) * segment_duration_seconds_;
    if (elapsed_seconds >= total_duration) {
      return {start_position_, 0.0, repeat_count_, true, true};
    }

    const auto segment_index = static_cast<std::size_t>(
        elapsed_seconds / segment_duration_seconds_);
    const bool returning = segment_index % 2 != 0;
    const double segment_start =
        static_cast<double>(segment_index) * segment_duration_seconds_;
    const double normalized_time = (elapsed_seconds - segment_start) /
                                   segment_duration_seconds_;
    const double u2 = normalized_time * normalized_time;
    const double u3 = u2 * normalized_time;
    const double u4 = u3 * normalized_time;
    const double u5 = u4 * normalized_time;
    const double quintic_position_ratio = 10.0 * u3 - 15.0 * u4 + 6.0 * u5;
    const double quintic_velocity_ratio =
        (30.0 * u2 - 60.0 * u3 + 30.0 * u4) /
        segment_duration_seconds_;
    const double from = returning ? target_position_ : start_position_;
    const double to = returning ? start_position_ : target_position_;

    return {from + (to - from) * quintic_position_ratio,
            (to - from) * quintic_velocity_ratio,
            segment_index / 2,
            returning,
            false};
  }

  double total_duration_seconds() const {
    return static_cast<double>(repeat_count_ * 2) *
           segment_duration_seconds_;
  }

private:
  double start_position_;
  double target_position_;
  double segment_duration_seconds_;
  std::size_t repeat_count_;
};

} // namespace revo3::examples
