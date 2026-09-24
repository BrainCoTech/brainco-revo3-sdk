#pragma once
#include <revo3/revo3.hpp>
#include "motion_profiles.hpp"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <iostream>
#include <set>
#include <sstream>
#include <stdexcept>
#include <thread>

namespace revo3_motion_demo {
using Values = std::vector<float>;
using Clock = std::chrono::steady_clock;
constexpr double pi = 3.14159265358979323846;
inline volatile std::sig_atomic_t running = 1;
inline void signal_handler(int) { running = 0; }
inline bool flex(int j) { return j < 16 && j % 4 != 0; }
struct Options {
  bool run = false, dump = false, left = false;
  double tempo = 1, tolerance = 0, minimum = 0, maximum = 60, frequency = 0.75, omega = 25;
  int repeat = 1, cycles = 3;
  std::set<int> skipped;
  revo3::DiscoveryOptions discovery;
};
inline double numeric(const std::string &s) {
  std::size_t end = 0;
  double value = std::stod(s, &end);
  if (end != s.size() || !std::isfinite(value)) throw std::invalid_argument("Invalid number: " + s);
  return value;
}
inline Options parse(int argc, char **argv) {
  Options o;
  for (int i = 1; i < argc; ++i) {
    std::string key = argv[i];
    if (key == "--run") { o.run = true; continue; }
    if (key == "--dump-profile") { o.dump = true; continue; }
    if (key == "--help") {
      std::cout << "Offline preview by default. --run --port PORT --slave-id ID --side left|right\n"
                   "--tempo N --repeat N --skip-joints 2,12,20 --feedback-tolerance-deg 0..2\n"
                   "Classic: --minimum DEG --maximum DEG --frequency HZ --cycles N --omega N\n";
      o.dump = true; continue;
    }
    if (++i >= argc) throw std::invalid_argument("Missing value: " + key);
    std::string value = argv[i];
    if (key == "--port") o.discovery.port = value;
    else if (key == "--side") {
      if (value != "left" && value != "right") throw std::invalid_argument("Invalid side");
      o.left = value == "left";
    } else if (key == "--skip-joints") {
      std::stringstream items(value); std::string item;
      if (value.empty() || value.back() == ',') throw std::invalid_argument("Invalid skipped joints");
      while (std::getline(items, item, ',')) {
        double j = numeric(item);
        if (j < 0 || j > 20 || j != std::floor(j) || !o.skipped.insert(static_cast<int>(j)).second)
          throw std::invalid_argument("Skipped joints must be unique integers in 0..20");
      }
    } else {
      double n = numeric(value);
      if (key == "--tempo") o.tempo = n;
      else if (key == "--feedback-tolerance-deg") o.tolerance = n;
      else if (key == "--minimum") o.minimum = n;
      else if (key == "--maximum") o.maximum = n;
      else if (key == "--frequency") o.frequency = n;
      else if (key == "--omega") o.omega = n;
      else if (key == "--slave-id" && n >= 1 && n <= 247 && n == std::floor(n)) o.discovery.slave_id = static_cast<uint8_t>(n);
      else if ((key == "--repeat" || key == "--cycles") && n >= 1 && n <= 1000 && n == std::floor(n)) {
        if (key == "--repeat") o.repeat = static_cast<int>(n); else o.cycles = static_cast<int>(n);
      } else throw std::invalid_argument("Unknown option or invalid value: " + key);
    }
  }
  if (o.tempo <= 0 || o.tolerance < 0 || o.tolerance > 2 || o.minimum >= o.maximum ||
      o.frequency <= 0 || o.frequency >= 50 || o.omega < 0)
    throw std::invalid_argument("Invalid tempo, tolerance, or sine parameters");
  return o;
}
inline void positions_ok(const Values &p, const revo3::DeviceConfig &c) {
  constexpr double kPositionBoundaryToleranceDeg = 0.1;
  if (p.size() != 21) throw std::runtime_error("Expected 21 positions");
  for (int j = 0; j < 21; ++j) {
    double lo = c.joint_min_position_deg[j], hi = c.joint_max_position_deg[j];
    if (!std::isfinite(lo) || !std::isfinite(hi) || lo >= hi || !std::isfinite(p[j]) ||
        p[j] < lo - kPositionBoundaryToleranceDeg || p[j] > hi + kPositionBoundaryToleranceDeg)
      throw std::runtime_error("Position outside limits: J" + std::to_string(j));
  }
}
inline double speed(const revo3::DeviceConfig &c, int j, double direction) {
  double lo = c.joint_min_speed_rpm[j], hi = c.joint_max_speed_rpm[j];
  double limit = direction < 0 && lo < 0 ? -lo : hi;
  if (!std::isfinite(lo) || !std::isfinite(hi) || lo > hi || limit <= 0)
    throw std::runtime_error("Invalid speed envelope");
  return limit;
}
inline void health(revo3::Hand &hand, const Options &o) {
  auto h = hand.health().snapshot();
  bool known = false;
  for (int j = 0; j < 21; ++j) {
    auto code = h.motor_fault_codes[j];
    known = known || (code & 0x100);
    if ((code & 0x37) && !o.skipped.count(j))
      throw std::runtime_error("Motor fault: J" + std::to_string(j) + " code=" + std::to_string(code));
  }
  if (h.system_state || h.system_error_code || ((h.safety_state == 2 || h.safety_state == 3 || h.faulted_motor_count) && !known))
    throw std::runtime_error("System or safety fault");
}
inline std::pair<Values, Values> wave(double elapsed, double duration) {
  Values p(21, 0), v(21, 0);
  if (elapsed <= 0 || elapsed >= duration) return {p,v};
  double scale = duration/6.5, width = 1.6*scale;
  for (int i = 0; i < 4; ++i) {
    double value = 0, rate = 0;
    for (int cycle = 0; cycle < 3; ++cycle) {
      double u = (elapsed - i*0.3*scale - cycle*2.0*scale)/width;
      if (u > 0 && u < 1) {
        double sine = std::sin(pi*u);
        value += std::pow(sine,4); rate += 4*pi/width*std::pow(sine,3)*std::cos(pi*u);
      }
    }
    for (int k = 1; k < 4; ++k) {
      int j = (3-i)*4+k; double amplitude = k == 3 ? 45 : 60;
      p[j] = static_cast<float>(amplitude*value); v[j] = static_cast<float>(amplitude*rate/6);
    }
  }
  return {p,v};
}
inline std::pair<Values, Values> smooth(const Values &a, const Values &b, double t, double duration, double delay) {
  Values p(21), v(21);
  for (int j = 0; j < 21; ++j) {
    double d = flex(j) ? delay : 0, span = duration-d;
    double r = std::clamp((t-d)/span,0.0,1.0);
    double blend = 10*std::pow(r,3)-15*std::pow(r,4)+6*std::pow(r,5);
    double rate = (30*r*r-60*std::pow(r,3)+30*std::pow(r,4))/span;
    p[j] = static_cast<float>(a[j]+(b[j]-a[j])*blend);
    v[j] = static_cast<float>((b[j]-a[j])*rate/6);
  }
  return {p,v};
}
inline void dump(const std::vector<Step> &steps) {
  std::cout << '[';
  for (std::size_t i = 0; i < steps.size(); ++i) {
    const auto &s = steps[i];
    if (i) std::cout << ',';
    std::cout << "{\"name\":\"" << s.name << "\",\"duration\":" << s.duration << ",\"hold\":" << s.hold
              << ",\"finger_delay\":" << s.delay << ",\"wave\":" << (s.wave ? "true" : "false") << ",\"positions_deg\":[";
    for (int j = 0; j < 21; ++j) { if (j) std::cout << ','; std::cout << s.target[j]; }
    std::cout << "]}";
  }
  std::cout << "]\n";
}
inline void execute(revo3::Hand &hand, const Options &o, const std::string &kind, std::vector<Step> steps) {
  auto layout = hand.joint_layout();
  if (!layout || layout->joint_count != 21) throw std::runtime_error("Requires 21 joints");
  auto info = hand.device_info();
  if (info.hand_side != (o.left ? revo3::HandSide::Left : revo3::HandSide::Right)) throw std::runtime_error("Hand side mismatch");
  std::cout << "Device: " << info.serial_number << "; firmware=" << hand.firmware_info().controller_firmware_version << '\n';
  auto c = hand.config().snapshot();
  if (c.software_stop_enabled || c.teaching_mode_enabled) throw std::runtime_error("Resolve software stop or zero-force mode first");
  health(hand,o);
  auto state = hand.state().snapshot();
  Values initial(state.motors.positions_deg,state.motors.positions_deg+21);
  for (int j = 0; j < 21; ++j) {
    double lo=c.joint_min_position_deg[j], hi=c.joint_max_position_deg[j];
    if (!std::isfinite(initial[j]) || !std::isfinite(lo) || !std::isfinite(hi) || lo >= hi)
      throw std::runtime_error("Invalid feedback or position limits");
    if (!o.skipped.count(j) && (initial[j]<lo-o.tolerance || initial[j]>hi+o.tolerance))
      throw std::runtime_error("Initial feedback outside tolerance: J"+std::to_string(j));
    initial[j]=static_cast<float>(std::clamp(double(initial[j]),lo,hi));
    speed(c,j,-1); speed(c,j,1);
  }
  for (const auto &step:steps) {
    positions_ok(step.target,c);
    if (step.wave) { Values peak(21,0); for (int j=0;j<16;++j) if(flex(j)) peak[j]=j%4==3?45:60; positions_ok(peak,c); }
  }
  Values sine_start=initial, sine_end=initial;
  if (kind=="classic") {
    for(int j=0;j<16;++j) if(flex(j) && !o.skipped.count(j)) {
      sine_start[j]=static_cast<float>(o.minimum); sine_end[j]=static_cast<float>(o.maximum);
      if ((o.maximum-o.minimum)*pi*o.frequency/6 > std::min(speed(c,j,-1),speed(c,j,1)))
        throw std::runtime_error("Sine peak speed exceeds limits");
    }
    positions_ok(sine_start,c); positions_ok(sine_end,c);
  }
  auto session=hand.motion().open_servo(std::chrono::milliseconds(500));
  try {
    Values current=initial, kp(21,1),kd(21,0.1f),zero(21,0);
    for(int j:o.skipped) kp[j]=kd[j]=0;
    auto last_health=Clock::now();
    auto send=[&](Values p, Values v) {
      if(!running) throw std::runtime_error("Interrupted");
      for(int j:o.skipped) {p[j]=initial[j];v[j]=0;}
      positions_ok(p,c);
      for(int j=0;j<21;++j) if(!std::isfinite(v[j]) || std::abs(v[j])>speed(c,j,v[j])+1e-5) throw std::runtime_error("Velocity exceeds limits");
      session.send_mit(p,v,kp,kd,zero);
      if(std::chrono::duration<double>(Clock::now()-last_health).count()>=0.25) {health(hand,o);last_health=Clock::now();}
    };
    auto segment=[&](Step step) {
      health(hand,o);
      std::cout << "Step: " << step.name << std::endl;
      for(int j:o.skipped) step.target[j]=initial[j];
      double delay=step.delay/o.tempo, duration=step.duration/o.tempo;
      for(int j=0;j<21;++j) if(!o.skipped.count(j)) {
        if(step.wave && flex(j)) {
          double amplitude=j%4==3?45:60;
          duration=std::max(duration,6.5*4*pi*amplitude/(1.6*6*std::min(speed(c,j,-1),speed(c,j,1))));
        } else if(!step.wave) duration=std::max(duration,delay+1.875*std::abs(step.target[j]-current[j])/(6*speed(c,j,step.target[j]-current[j])));
      }
      auto began=Clock::now();
      while(true) {
        double elapsed=std::chrono::duration<double>(Clock::now()-began).count();
        auto sample=step.wave?wave(std::min(elapsed,duration),duration):smooth(current,step.target,std::min(elapsed,duration),duration,delay);
        send(sample.first,sample.second);
        if(elapsed>=duration+step.hold/o.tempo) break;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
      }
      current=step.target;
    };
    if(kind=="classic") {
      segment({"sine_entry",sine_start,2,0,0,false});
      Values filtered=sine_start; std::vector<double> filter_v(21,0);
      auto began=Clock::now(),previous=began;
      double total=o.cycles/o.frequency;
      while(true) {
        auto now=Clock::now(); double t=std::min(total,std::chrono::duration<double>(now-began).count());
        double dt=std::chrono::duration<double>(now-previous).count(); previous=now;
        Values p=sine_start,v(21,0);
        double amplitude=(o.maximum-o.minimum)/2, phase=2*pi*o.frequency*t;
        for(int j=0;j<16;++j) if(flex(j) && !o.skipped.count(j)) {
          p[j]=static_cast<float>(o.minimum+amplitude*(1-std::cos(phase)));
          v[j]=static_cast<float>(amplitude*2*pi*o.frequency*std::sin(phase)/6);
        }
        if(o.omega>0) for(int j=0;j<21;++j) {
          double error=filtered[j]-p[j], coefficient=filter_v[j]+o.omega*error, decay=std::exp(-o.omega*dt);
          filtered[j]=static_cast<float>(p[j]+(error+coefficient*dt)*decay);
          filter_v[j]=(filter_v[j]-o.omega*coefficient*dt)*decay;
          p[j]=filtered[j];v[j]=static_cast<float>(filter_v[j]/6);
        }
        send(p,v);current=p;
        if(t>=total) break;
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
      }
    } else for(int repeat=0;repeat<o.repeat;++repeat) for(const auto &step:steps) segment(step);
    segment({"return_initial",initial,1,0.2,0,false});
    health(hand,o);
    auto actual=hand.state().snapshot(); double error=0;
    for(int j=0;j<21;++j) if(!o.skipped.count(j)) error=std::max(error,double(std::abs(actual.motors.positions_deg[j]-initial[j])));
    if(error>5) throw std::runtime_error("Return tracking error exceeds 5 degrees");
    session.close();
    std::cout << "Completed; max return error=" << error << " deg; skipped=";
    for(int j:o.skipped) std::cout << j << ' ';
    std::cout << std::endl;
  } catch(...) {
    try {hand.motion().software_stop();} catch(const std::exception &e) {std::cerr << "Software stop unconfirmed: " << e.what() << '\n';}
    session.close(); throw;
  }
}
inline int main(const std::string &kind,int argc,char **argv) {
  try {
    auto options=parse(argc,argv); auto steps=profile(kind);
    if(options.dump) {dump(steps);return 0;}
    if(!options.run) {
      std::cout << "Offline preview: " << kind << "; no connection opened\n";
      if(kind=="classic") std::cout << "Sine " << options.minimum << ".." << options.maximum << " deg, " << options.frequency << " Hz\n";
      else for(const auto &step:steps) std::cout << step.name << " duration=" << step.duration/options.tempo << "s\n";
      std::cout << "Pass --run to execute candidate poses; contact is not calibrated.\n";return 0;
    }
    running=1;std::signal(SIGINT,signal_handler);std::signal(SIGTERM,signal_handler);
    revo3::Manager manager; auto hand=manager.connect_auto(options.discovery);
    execute(hand,options,kind,steps);return 0;
  } catch(const std::exception &e) {std::cerr << "Demo failed: " << e.what() << '\n';return running?1:130;}
}
}  // namespace revo3_motion_demo
