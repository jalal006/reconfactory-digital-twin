#include "reconfactory_gazebo_watchdog/Policy.hh"
#include <chrono>
#include <gz/msgs/boolean.pb.h>
#include <gz/msgs/odometry.pb.h>
#include <gz/msgs/stringmsg.pb.h>
#include <gz/msgs/twist.pb.h>
#include <gz/plugin/Register.hh>
#include <gz/sim/System.hh>
#include <gz/transport/Node.hh>
#include <memory>
#include <mutex>
#include <nlohmann/json.hpp>
#include <random>

namespace reconfactory {
class ActuatorWatchdog : public gz::sim::System,
                         public gz::sim::ISystemConfigure,
                         public gz::sim::ISystemPreUpdate,
                         public gz::sim::ISystemReset {
  using Json = nlohmann::json;
  gz::transport::Node::Publisher output, status;
  std::mutex mutex;
  Policy policy;
  double lastOutput{-1}, lastStatus{-1};
  unsigned long sample{0};
  std::string instance;
  bool configured{false}, configValid{true};
  std::chrono::steady_clock::duration lastSim{};
  // Destroy transport callbacks before the policy and its mutex.
  gz::transport::Node node;
  static double Now() {
    return std::chrono::duration<double>(
               std::chrono::steady_clock::now().time_since_epoch())
        .count();
  }

public:
  void Configure(const gz::sim::Entity &,
                 const std::shared_ptr<const sdf::Element> &sdf,
                 gz::sim::EntityComponentManager &,
                 gz::sim::EventManager &) override {
    instance =
        std::to_string(std::random_device{}()) + "-" + std::to_string(Now());
    Config c;
    try {
      c.commandTimeout =
          sdf->Get<double>("command_timeout_s", c.commandTimeout).first;
      c.outputPeriod =
          sdf->Get<double>("output_period_s", c.outputPeriod).first;
      c.startupZero =
          sdf->Get<double>("startup_zero_confirmation_s", c.startupZero).first;
      c.odomTimeout =
          sdf->Get<double>("odometry_timeout_s", c.odomTimeout).first;
      c.stoppedDuration =
          sdf->Get<double>("stopped_duration_s", c.stoppedDuration).first;
      if (!sdf->Get<bool>("require_explicit_reset_after_timeout", true).first)
        throw std::invalid_argument("Automatic timeout reset is not supported");
      policy = Policy(c);
    } catch (const std::exception &e) {
      configValid = false;
      policy.Fault(e.what(), Now());
    }
    output = node.Advertise<gz::msgs::Twist>("/amr/actuator_cmd_vel");
    status =
        node.Advertise<gz::msgs::StringMsg>("/amr/actuator_watchdog/state");
    node.Subscribe("/amr/cmd_vel_requested", &ActuatorWatchdog::Command, this);
    node.Subscribe("/amr/odom", &ActuatorWatchdog::Odometry, this);
    node.Advertise("/amr/actuator_watchdog/reset",
                   &ActuatorWatchdog::RequestReset, this);
    configured = true;
  }
  void Command(const gz::msgs::Twist &msg) {
    std::lock_guard<std::mutex> lock(mutex);
    if (!msg.has_linear() || !msg.has_angular()) {
      policy.Fault("Malformed Twist", Now());
      return;
    }
    policy.Command({msg.linear().x(), msg.linear().y(), msg.linear().z(),
                    msg.angular().x(), msg.angular().y(), msg.angular().z()},
                   Now());
  }
  void Odometry(const gz::msgs::Odometry &msg) {
    std::lock_guard<std::mutex> lock(mutex);
    if (!msg.has_twist()) {
      policy.Fault("Missing odometry twist", Now());
      return;
    }
    policy.Odometry(
        std::hypot(msg.twist().linear().x(), msg.twist().linear().y()),
        msg.twist().angular().z(), Now());
  }
  bool RequestReset(const gz::msgs::Boolean &req, gz::msgs::Boolean &rep) {
    std::lock_guard<std::mutex> lock(mutex);
    rep.set_data(configValid && req.data() && policy.Reset(Now()));
    return true;
  }
  void Reset(const gz::sim::UpdateInfo &,
             gz::sim::EntityComponentManager &) override {
    std::lock_guard<std::mutex> lock(mutex);
    policy.Fault("Simulation reset", Now());
  }
  void PreUpdate(const gz::sim::UpdateInfo &info,
                 gz::sim::EntityComponentManager &) override {
    if (!configured)
      return;
    Velocity velocity{};
    std::string observation;
    bool publish = false;
    {
      std::lock_guard<std::mutex> lock(mutex);
      const auto now = Now();
      policy.Simulation(info.paused,
                        info.simTime < lastSim || info.dt.count() < 0, now);
      lastSim = info.simTime;
      velocity = policy.Output(now);
      publish = now - lastOutput >= policy.config.outputPeriod;
      if (publish)
        lastOutput = now;
      if (now - lastStatus >= 0.1) {
        lastStatus = now;
        Json events = Json::array();
        for (const auto &e : policy.events)
          events.push_back(
              {{"event_id", instance + ":" + std::to_string(e.sequence)},
               {"event_type", e.type},
               {"reason", e.reason},
               {"steady_time_s", e.time},
               {"command_age_ms",
                e.commandAge < 0 ? Json(nullptr) : Json(e.commandAge * 1000)}});
        observation =
            Json(
                {{"instance_id", instance},
                 {"sample_sequence", ++sample},
                 {"transition_sequence", policy.sequence},
                 {"state", policy.state},
                 {"startup_ready", policy.StartupReady(now)},
                 {"reason", policy.reason},
                 {"motion_inhibited", policy.state != "ARMED" || policy.paused},
                 {"reset_required", policy.state == "FAULT_LATCHED"},
                 {"robot_stopped_confirmed", policy.Stopped(now)},
                 {"command_age_ms",
                  policy.commandAt < 0 ? Json(nullptr)
                                       : Json((now - policy.commandAt) * 1000)},
                 {"last_timeout_steady_s", policy.timeoutAt < 0
                                               ? Json(nullptr)
                                               : Json(policy.timeoutAt)},
                 {"command_age_at_timeout_ms",
                  policy.timeoutAge < 0 ? Json(nullptr)
                                        : Json(policy.timeoutAge * 1000)},
                 {"events", events}})
                .dump();
      }
    }
    // No HTTP, database or service calls in this callback. Transport is
    // asynchronous.
    if (publish) {
      gz::msgs::Twist msg;
      msg.mutable_linear()->set_x(velocity[0]);
      msg.mutable_linear()->set_y(velocity[1]);
      msg.mutable_linear()->set_z(velocity[2]);
      msg.mutable_angular()->set_x(velocity[3]);
      msg.mutable_angular()->set_y(velocity[4]);
      msg.mutable_angular()->set_z(velocity[5]);
      output.Publish(msg);
    }
    if (!observation.empty()) {
      gz::msgs::StringMsg msg;
      msg.set_data(observation);
      status.Publish(msg);
    }
  }
};
} // namespace reconfactory
GZ_ADD_PLUGIN(reconfactory::ActuatorWatchdog, gz::sim::System,
              reconfactory::ActuatorWatchdog::ISystemConfigure,
              reconfactory::ActuatorWatchdog::ISystemPreUpdate,
              reconfactory::ActuatorWatchdog::ISystemReset)
