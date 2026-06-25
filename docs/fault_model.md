# Fault Model

The first release uses deterministic threshold and status rules. This is deliberate: the project should prove correct baseline behavior before adding machine learning.

## Detected Faults

| Fault | Trigger | Recovery Behavior |
|---|---|---|
| Overheat | Temperature exceeds configured limit | Remove station from scheduling and reroute compatible work |
| Jam | Jam flag is true | Stop affected movement and pause unsafe work |
| Sensor failure | Sensor status is false | Mark equipment unavailable |
| Camera failure | Vision camera status is false | Pause vision work because product identity cannot be trusted |
| Timeout | Runtime exceeds configured process limit | Release product and diagnose process anomaly |
| Communication loss | Heartbeat age exceeds configured limit | Mark equipment unavailable |

## Diagnosis Output

Each fault produces:

- Fault ID
- Machine ID
- Fault type
- Severity
- Likely cause
- Recommendation
- Human-readable explanation
- Detection timestamp

## Safety Rule

The scheduler never assigns new work to a machine whose `healthy` flag is false. Recovery returns a machine to `idle` only after sensors are reset.
