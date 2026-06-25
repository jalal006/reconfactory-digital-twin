# Demo Scenarios

## Demo 1: Normal Production

1. Click `Start`.
2. Add red, blue, and green products.
3. Watch completed and accepted products increase.

## Demo 2: Station Failure And Rerouting

1. Add a red block.
2. Let it reach Processing A.
3. Click `Station A Overheat`.
4. Watch the product reroute to Processing B if drilling is still possible.

## Demo 3: Conveyor Jam

1. Start production.
2. Click `Conveyor Jam`.
3. Confirm the line stops safely.
4. Recover the conveyor.

## Demo 4: Defective Product

1. Choose a defect such as `wrong_colour`.
2. Add the product.
3. Confirm it goes to reject output after vision inspection.

## Demo 5: No Available Route

1. Fail Processing A.
2. Add a green component.
3. Confirm it pauses safely because assembly has no backup station.

## Demo 6: Predictive Maintenance

1. Run `python scripts/generate_sensor_data.py`.
2. Run `python scripts/run_experiment.py`.
3. Show health score and maintenance status in the dashboard.
