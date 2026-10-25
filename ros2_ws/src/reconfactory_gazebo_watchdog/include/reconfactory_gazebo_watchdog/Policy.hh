#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include <deque>
#include <stdexcept>
#include <string>

namespace reconfactory {
using Velocity = std::array<double, 6>;
struct Config {
  double commandTimeout{0.30}, outputPeriod{0.02}, startupZero{0.30};
  double odomTimeout{0.50}, stoppedDuration{0.30};
  double linearStop{0.03}, angularStop{0.05};
  void Validate() const {
    for (double v : {commandTimeout, outputPeriod, startupZero, odomTimeout,
                     stoppedDuration, linearStop, angularStop})
      if (!std::isfinite(v) || v <= 0)
        throw std::invalid_argument("Invalid watchdog threshold");
    if (outputPeriod >= commandTimeout)
      throw std::invalid_argument("Output period must be shorter than timeout");
  }
};
struct Event {
  unsigned long sequence;
  std::string type, reason;
  double time, commandAge;
};

// Time is injected in seconds from one local steady clock; never simulation
// time.
class Policy {
public:
  explicit Policy(Config c = {}) : config(c) { config.Validate(); }
  Config config;
  std::string state{"STARTUP_INHIBITED"},
      reason{"Waiting for fresh zero stream and stopped odometry"};
  Velocity latest{};
  double commandAt{-1}, odomAt{-1}, zeroSince{-1}, stoppedSince{-1};
  double timeoutAt{-1}, timeoutAge{-1};
  bool zeroInput{false}, paused{false};
  unsigned long sequence{0};
  std::deque<Event> events;

  void Record(const std::string &type, double now) {
    events.push_back(
        {++sequence, type, reason, now, commandAt < 0 ? -1 : now - commandAt});
    if (events.size() > 64)
      events.pop_front();
  }
  void Fault(const std::string &why, double now) {
    if (state == "FAULT_LATCHED")
      return;
    state = "FAULT_LATCHED";
    reason = why;
    latest = {};
    zeroSince = -1;
    Record("actuator_watchdog_fault_latched", now);
  }
  bool Fresh(double at, double now, double limit) const {
    return at >= 0 && now >= at && now - at < limit;
  }
  bool Stopped(double now) const {
    return !paused && Fresh(odomAt, now, config.odomTimeout) &&
           stoppedSince >= 0 && now - stoppedSince >= config.stoppedDuration;
  }
  bool StartupReady(double now) const {
    return state == "STARTUP_INHIBITED" && !paused && zeroInput &&
           Fresh(commandAt, now, config.commandTimeout) && zeroSince >= 0 &&
           now - zeroSince >= config.startupZero && Stopped(now);
  }
  void Check(double now) {
    if (state == "ARMED" && !Fresh(commandAt, now, config.commandTimeout)) {
      timeoutAt = now;
      timeoutAge = commandAt < 0 ? -1 : now - commandAt;
      reason = "Command stream timeout";
      Record("actuator_watchdog_timeout", now);
      Fault(reason, now);
    }
  }
  void Command(const Velocity &v, double now) {
    Check(now); // A late command cannot hide expiry between update callbacks.
    if (!std::all_of(v.begin(), v.end(),
                     [](double x) { return std::isfinite(x); })) {
      Fault("Non-finite velocity", now);
      return;
    }
    const bool zero =
        std::all_of(v.begin(), v.end(), [](double x) { return x == 0; });
    // Initial zero traffic is not a motion request. Arm only when the upstream
    // ROS gate supplies movement after a fresh, stopped zero initialization.
    if (!zero && StartupReady(now)) {
      state = "ARMED";
      reason = "Fresh movement request after zero initialization";
      Record("actuator_watchdog_armed", now);
    }
    if (!zero || zeroSince < 0 ||
        !Fresh(commandAt, now, config.commandTimeout) || !zeroInput)
      zeroSince = zero ? now : -1;
    commandAt = now;
    zeroInput = zero;
    latest = state == "ARMED" && !paused ? v : Velocity{};
  }
  void Odometry(double linear, double angular, double now) {
    if (!std::isfinite(linear) || !std::isfinite(angular)) {
      stoppedSince = -1;
      odomAt = -1;
      Fault("Invalid odometry", now);
      return;
    }
    if (!Fresh(odomAt, now, config.odomTimeout))
      stoppedSince = -1;
    odomAt = now;
    if (paused || std::abs(linear) >= config.linearStop ||
        std::abs(angular) >= config.angularStop)
      stoppedSince = -1;
    else if (stoppedSince < 0)
      stoppedSince = now;
  }
  void Simulation(bool isPaused, bool timeReset, double now) {
    if (timeReset)
      Fault("Simulation time reset", now);
    if (isPaused && !paused && state == "ARMED")
      Fault("Simulation paused while armed", now);
    if (isPaused || paused != isPaused) {
      latest = {};
      zeroSince = -1;
      stoppedSince = -1;
    }
    paused = isPaused;
  }
  Velocity Output(double now) {
    Check(now);
    return state == "ARMED" && !paused ? latest : Velocity{};
  }
  bool Reset(double now) {
    Check(now);
    Record("actuator_watchdog_reset_requested", now);
    if (state != "FAULT_LATCHED" || !zeroInput ||
        !Fresh(commandAt, now, config.commandTimeout) || zeroSince < 0 ||
        now - zeroSince < config.startupZero || !Stopped(now)) {
      Record("actuator_watchdog_reset_rejected", now);
      return false;
    }
    state = "STARTUP_INHIBITED";
    reason = "Explicit reset; new zero initialization required";
    latest = {};
    commandAt = -1;
    zeroSince = -1;
    zeroInput = false;
    stoppedSince = -1;
    Record("actuator_watchdog_reset_completed", now);
    return true;
  }
};
} // namespace reconfactory
