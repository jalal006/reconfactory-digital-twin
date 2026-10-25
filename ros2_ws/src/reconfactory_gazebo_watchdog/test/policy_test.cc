#include "reconfactory_gazebo_watchdog/Policy.hh"
#include <gtest/gtest.h>
#include <limits>
using namespace reconfactory;

class Watchdog : public ::testing::Test {
protected:
  Policy p;
  double now{0};
  const Velocity moving{0.45, 0, 0, 0, 0, 0};
  void Zeros(int n = 9) {
    for (int i = 0; i < n; ++i) {
      now += 0.05;
      p.Command({}, now);
      p.Odometry(0, 0, now);
      p.Output(now);
    }
  }
  void Arm() {
    Zeros();
    ASSERT_TRUE(p.StartupReady(now));
    p.Command(moving, now);
    ASSERT_EQ(p.state, "ARMED");
    p.Command({}, now);
  }
};
TEST_F(Watchdog, StartupInhibits) {
  p.Command(moving, now);
  EXPECT_EQ(p.Output(now), Velocity{});
}
TEST_F(Watchdog, StartupNeedsOdometry) {
  p.Command({}, now);
  now = 0.2;
  p.Command({}, now);
  EXPECT_EQ(p.state, "STARTUP_INHIBITED");
}
TEST_F(Watchdog, FreshZeroSequencePreparesWithoutArming) {
  Zeros();
  EXPECT_TRUE(p.StartupReady(now));
  EXPECT_EQ(p.state, "STARTUP_INHIBITED");
  EXPECT_EQ(p.Output(now), Velocity{});
  p.Command(moving, now);
  EXPECT_EQ(p.state, "ARMED");
  EXPECT_EQ(p.Output(now), moving);
}
TEST_F(Watchdog, ForwardsFreshCommand) {
  Arm();
  p.Command(moving, now);
  EXPECT_EQ(p.Output(now), moving);
}
TEST_F(Watchdog, TimeoutInhibitsAndLatches) {
  Arm();
  p.Command(moving, now);
  now += 0.31;
  EXPECT_EQ(p.Output(now), Velocity{});
  EXPECT_EQ(p.state, "FAULT_LATCHED");
}
TEST_F(Watchdog, NonfiniteRejected) {
  Arm();
  auto v = moving;
  v[4] = std::numeric_limits<double>::quiet_NaN();
  p.Command(v, now);
  EXPECT_EQ(p.Output(now), Velocity{});
  EXPECT_EQ(p.state, "FAULT_LATCHED");
}
TEST_F(Watchdog, InfinityRejected) {
  Arm();
  auto v = moving;
  v[0] = std::numeric_limits<double>::infinity();
  p.Command(v, now);
  EXPECT_EQ(p.state, "FAULT_LATCHED");
}
TEST_F(Watchdog, LateCommandCannotHideExpiry) {
  Arm();
  now += 0.31;
  p.Command(moving, now);
  EXPECT_EQ(p.state, "FAULT_LATCHED");
}
TEST_F(Watchdog, ZeroHoldsDoNotExpire) {
  Arm();
  Zeros(500);
  EXPECT_EQ(p.state, "ARMED");
}
TEST_F(Watchdog, GateRestartCannotClearLatch) {
  Arm();
  now += 1;
  p.Output(now);
  Zeros();
  p.Command(moving, now);
  EXPECT_EQ(p.Output(now), Velocity{});
  EXPECT_EQ(p.state, "FAULT_LATCHED");
}
TEST_F(Watchdog, ResetDeniedMoving) {
  Arm();
  p.Fault("test", now);
  Zeros();
  p.Odometry(.4, 0, now);
  EXPECT_FALSE(p.Reset(now));
}
TEST_F(Watchdog, ResetDeniedWithoutFreshZero) {
  Arm();
  p.Fault("test", now);
  Zeros();
  now += .31;
  EXPECT_FALSE(p.Reset(now));
}
TEST_F(Watchdog, ResetDeniedWithNonzeroInput) {
  Arm();
  p.Fault("test", now);
  Zeros();
  p.Command(moving, now);
  EXPECT_FALSE(p.Reset(now));
}
TEST_F(Watchdog, ResetRequiresNewInitialization) {
  Arm();
  p.Fault("test", now);
  Zeros();
  ASSERT_TRUE(p.Reset(now));
  EXPECT_EQ(p.state, "STARTUP_INHIBITED");
  p.Command(moving, now);
  EXPECT_EQ(p.Output(now), Velocity{});
  Zeros();
  EXPECT_TRUE(p.StartupReady(now));
  EXPECT_EQ(p.state, "STARTUP_INHIBITED");
  EXPECT_EQ(p.Output(now), Velocity{});
  p.Command(moving, now);
  EXPECT_EQ(p.state, "ARMED");
  EXPECT_EQ(p.Output(now), moving);
}
TEST_F(Watchdog, PauseNeverReplays) {
  Arm();
  p.Command(moving, now);
  p.Simulation(true, false, now);
  now += 2;
  p.Simulation(false, false, now);
  EXPECT_EQ(p.Output(now), Velocity{});
  EXPECT_EQ(p.state, "FAULT_LATCHED");
}
TEST_F(Watchdog, TimeResetLatches) {
  Arm();
  p.Simulation(false, true, now);
  EXPECT_EQ(p.state, "FAULT_LATCHED");
}
TEST_F(Watchdog, InitialPausedWorldCannotArm) {
  p.Simulation(true, false, now);
  Zeros();
  EXPECT_EQ(p.state, "STARTUP_INHIBITED");
  p.Simulation(false, false, now);
  Zeros();
  EXPECT_TRUE(p.StartupReady(now));
  p.Command(moving, now);
  EXPECT_EQ(p.state, "ARMED");
}
TEST_F(Watchdog, StartupGapNeverArmsOrLatches) {
  Zeros(500);
  now += 1;
  EXPECT_EQ(p.Output(now), Velocity{});
  EXPECT_FALSE(p.StartupReady(now));
  EXPECT_EQ(p.state, "STARTUP_INHIBITED");
  Zeros();
  EXPECT_TRUE(p.StartupReady(now));
}
TEST_F(Watchdog, ExpiredStartupRejectsMovementUntilNewZeroWindow) {
  Zeros();
  now += .31;
  p.Command(moving, now);
  EXPECT_EQ(p.Output(now), Velocity{});
  EXPECT_EQ(p.state, "STARTUP_INHIBITED");
  Zeros();
  p.Command(moving, now);
  EXPECT_EQ(p.Output(now), moving);
}
TEST_F(Watchdog, ArmedIdleStillLatchesOnTimeout) {
  Arm();
  Zeros();
  now += .31;
  EXPECT_EQ(p.Output(now), Velocity{});
  EXPECT_EQ(p.state, "FAULT_LATCHED");
}
TEST_F(Watchdog, TimeoutEventsNotRepeated) {
  Arm();
  now += 1;
  p.Output(now);
  auto n = p.sequence;
  for (int i = 0; i < 100; ++i)
    p.Output(++now);
  EXPECT_EQ(p.sequence, n);
}
TEST_F(Watchdog, OdometryGapRestartsStoppedWindow) {
  Arm();
  p.Fault("test", now);
  now += 1;
  p.Odometry(0, 0, now);
  EXPECT_FALSE(p.Stopped(now));
}
TEST_F(Watchdog, InvalidOdometryFailsClosed) {
  Arm();
  p.Odometry(NAN, 0, now);
  EXPECT_EQ(p.state, "FAULT_LATCHED");
  EXPECT_FALSE(p.Stopped(now));
}
TEST_F(Watchdog, InvalidConfiguration) {
  for (double v : {0., -1., double(INFINITY), double(NAN)}) {
    Config c;
    c.commandTimeout = v;
    EXPECT_THROW(Policy{c}, std::invalid_argument);
  }
}
