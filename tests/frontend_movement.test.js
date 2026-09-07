// Run with: node tests/frontend_movement.test.js
function runFrontendMovementTests(source) {
  const checks = `
    function assert(condition, message) {
      if (!condition) throw new Error(message);
    }
    for (const productType of ["red_block", "blue_cylinder", "green_component"]) {
      for (const output of ["accepted_output", "reject_output"]) {
        visualProducts.clear();
        clock.now = 1000;
        const product = {
          product_id: "P-00001", product_type: productType,
          status: output === "accepted_output" ? "completed" : "rejected",
          current_location: output,
          route: ["input_queue", "vision", "station_a", "quality_buffer", "quality", output],
        };
        const state = {
          running: true, products: [product],
          gazebo_visuals: {
            source: "gazebo", updated_at: Date.now() / 1000,
            product_locations: { "P-00001": "quality" },
          },
        };
        updateProductTargets(state);
        const visual = visualProducts.get(product.product_id);
        assert(visual.destination === output, "Quality must dispatch to its output");
        const firstTransport = visual.transportStartedAt;
        clock.now += 100;
        state.gazebo_visuals.product_locations[product.product_id] = "quality_buffer";
        updateProductTargets(state);
        assert(visual.pendingDestination === null, "Delayed buffer must not queue Quality again");
        assert(visual.transportStartedAt === firstTransport, "Output transfer must not restart");
        clock.now += 5000;
        // Also discard requests queued before the terminal transfer began.
        visual.pendingDestination = "quality";
        updateProductTargets(state);
        assert(visual.location === output && visual.destination === output, "Product must stay in its output");
        assert(!isVisualTransporting(visual, clock.now), "Output must not animate a second transfer");
        state.gazebo_visuals.product_locations[product.product_id] = "quality";
        updateProductTargets(state);
        assert(visual.location === output && !visual.route, "Repeated station reports must not replay output");
        visualProducts.clear();
        state.gazebo_visuals.product_locations[product.product_id] = "station_a";
        updateProductTargets(state);
        assert(visualProducts.get(product.product_id).destination === "quality", "Backend completion must not skip Quality visually");
        state.products = [];
        updateProductTargets(state);
        assert(visualProducts.size === 0, "Reset must clear terminal products");
      }
    }
    for (const station of ["station_a", "station_b"]) {
      visualProducts.clear();
      routeIndicatorUntil.clear();
      clock.now = 1000;
      const product = {
        product_id: "P-00002", product_type: "red_block", status: "processing",
        assigned_station: station, current_location: station,
        route: ["input_queue", "vision", "processing_buffer", station],
      };
      const state = {
        running: true, products: [product],
        gazebo_visuals: { source: "gazebo", updated_at: Date.now() / 1000,
          product_locations: { "P-00002": "vision" } },
      };
      updateProductTargets(state);
      const visual = visualProducts.get(product.product_id);
      assert(visual.destination === station, "Vision must dispatch to processing");
      product.assigned_station = "quality";
      product.current_location = "quality";
      product.route.push("quality_buffer", "quality");
      state.gazebo_visuals.updated_at = Date.now() / 1000 - 10;
      clock.now += 100;
      updateProductTargets(state);
      assert(visual.destination === station && visual.pendingDestination === null,
        "Stale Gazebo data must not switch to backend positions");
      assert(!routeIndicatorUntil.has(station + "_to_quality_buffer"),
        "A sync gap must not flash a future backend route");
      clock.now += 5000;
      updateProductTargets(state);
      assert(visual.location === station && !visual.route, "Finish the leg and wait during a sync gap");
      state.gazebo_visuals.updated_at = Date.now() / 1000;
      state.gazebo_visuals.product_locations[product.product_id] = "input_queue";
      updateProductTargets(state);
      assert(visual.location === station && !visual.route, "Delayed input report must not undo processing arrival");
      state.gazebo_visuals.product_locations[product.product_id] = station;
      updateProductTargets(state);
      assert(visual.destination === "quality", "A new station report must resume forward movement");
      assert(forwardVisualDestination(product, visual, "recovery_buffer") === "recovery_buffer",
        "Fault recovery must still allow movement to the recovery buffer");
    }
  `;
  const clock = { now: 0 };
  const document = {
    getElementById: () => ({ addEventListener() {} }),
    querySelectorAll: () => [],
  };
  const run = new Function(
    "document", "window", "fetch", "requestAnimationFrame", "performance", "clock",
    source + "\n" + checks,
  );
  run(document, { addEventListener() {} }, () => new Promise(() => {}), () => 1,
    { now: () => clock.now }, clock);
  return "8 browser movement scenarios passed";
}

if (typeof require === "function") {
  const fs = require("node:fs");
  const path = require("node:path");
  console.log(runFrontendMovementTests(fs.readFileSync(path.join(__dirname, "../frontend/app.js"), "utf8")));
}
