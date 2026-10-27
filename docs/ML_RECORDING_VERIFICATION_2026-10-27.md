# ML recording verification — 27 October 2026

The reported failed recording stopped during input-to-Vision delivery. Stored
events show `Backend authorization is stale` at 16:40:11 UTC, cancellation with
confirmed stopping, and a Station A fault 41 seconds later. The fault detector
maps excessive vibration to its existing timeout category; the late bearing
scenario crossed its 3.2 mm/s threshold. This was not a predictive assignment
being rerouted after pickup. A safety latch correctly requires explicit recovery.

Health estimation now scores all ready station windows in one Isolation Forest
call per tick. Per-station histories, warmup fallback, scores and scheduling rules
are preserved. In unloaded WSL measurements using a separate database, steady
median tick time was 59 ms before and 38 ms after; the warmup-transition tick was
252 ms and 235 ms respectively. These measurements reduce a synchronous workload;
they do not establish a real-time latency bound or prove every source of the
original backend delay. Safety and authorization timeouts are unchanged.

The telemetry sender accepts `--hold-after 40 --hold-seconds 120`. For the default
seed-42, 90-sample bearing scenario this holds approximately 1.152 mm/s vibration,
below the hard-fault threshold, instead of continuing to failure. Start the line,
wait for the hold message, then add a red block. Existing jobs remain assigned.

Two isolated real Gazebo/Nav2 runs with ML maintenance enabled passed: an ordinary
red production cycle, then the revised recording sequence with held degradation
before product creation. The second run completed:

`input_queue -> vision -> station_b -> quality -> accepted_output`.

Its SQLite event record contains `predictive_reroute` avoiding A (health 0.2081,
anomaly 0.7919) and choosing B (health 0.7727), followed by accepted completion.
No station fault or safety-latch event was recorded in this test database.
Real camera inspection confidence was 1.0. The isolated stack shut down after
success; its extra telemetry sender then reported connection refusal as the
backend closed, rather than a failure during production.

Local evidence is in `logs/ml_recording_verification.json` and
`logs/amr_smoke/test_9003.db`; runtime artifacts are ignored by Git. The temporary
verification wrapper reused the smoke runner, inserted the held telemetry before
product creation, and asserted B was in the completed route and A was absent.
The test ran headlessly; screen recording adds load and was not measured here.

Regression coverage compares mixed warmup/ML batch results to individual
predictions, keeps histories isolated, rejects invalid batches before insertion,
and verifies that the held demo samples stay below the bearing fault threshold.
The full Ubuntu suite passed 370 tests in 30.41 seconds; Ruff lint/format, all 20
browser scenarios and Git whitespace checks passed.
See [recording commands](DEMO_SCENARIOS.md#demo-6-predictive-maintenance).

## Follow-up: authorization still expired in the user's GUI run

The user reproduced `Backend authorization is stale` after the batching change,
during input-to-Vision delivery at approximately 17:55 local time. The earlier
headless passes therefore did not establish that the recording issue was fixed.

The API now captures detached telemetry histories on its event loop and runs ML
inference in a worker thread. Authorization reads and Stop/Reset remain available
during inference. Factory mutations stay on the event loop, tick operations are
serialized, and results from a reset run are discarded. Synchronous simulation
and offline experiments retain their normal tick interface.

The manager now polls authorization independently of its ordered status and
latest-heartbeat writer. Previously, a GET followed by two sequential POSTs and
the polling delay could age the observation past 0.6 seconds. A failed read still
invalidates the observation; a failed write also blocks authorization until the
write path recovers. Queue overflow remains latched unavailable, and receipt
timestamps and freshness thresholds are unchanged.

Regression cases deliberately block inference and status posting, verify fresh
authorization/Stop responses, reject old-run inference after Reset, and check
that successful reads cannot conceal failed writes (or the reverse).

The follow-up live run enabled the Gazebo GUI and two additional 10 Hz polling
streams (`/api/status` and `/api/transport`) while holding the same degradation.
It completed through Vision, B, Quality and Accepted with real camera inspection.
The 1,917 successful polling requests had a maximum response time of 0.238 s;
none exceeded 0.5 s. The database recorded predictive avoidance of A (health
0.2164) in favor of B (health 0.7727), followed by accepted completion, with no
station-fault or safety-latch events. Connection refusal occurred only when the
test deliberately closed its backend after completion. Evidence is preserved in
`logs/ml_gui_authorization_fix/` and `logs/amr_smoke/test_12327.db`.
This exercised GUI rendering and dashboard-like traffic, but not video encoding.
The complete Ubuntu regression suite then passed 376 tests in 29.54 seconds;
Ruff lint/format, all 20 browser scenarios and whitespace checks passed.

A separate real backend-outage trial also passed after the polling change:
command inhibition at 0.697 s, stable stop at 1.147 s from 0.45 m/s, 0.3195 m
travel, retained payload and no false delivery. Restart did not clear the latch;
explicit reset and a new delivery succeeded. The report is
`logs/amr_smoke/safety_backend-outage_1793120796328491809.json`.
