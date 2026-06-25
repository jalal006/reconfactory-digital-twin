from maintenance.health import HealthScorer, SensorPoint, detect_degradation_trend


def test_health_scorer_marks_nominal_machine_healthy():
    scorer = HealthScorer()
    recommendation = scorer.recommend(
        SensorPoint(
            machine_id="station_a",
            temperature_c=36.0,
            vibration_mm_s=0.12,
            current_a=0.9,
        )
    )

    assert recommendation.health_score > 0.9
    assert recommendation.status == "healthy"


def test_health_scorer_warns_on_degraded_machine():
    scorer = HealthScorer()
    recommendation = scorer.recommend(
        SensorPoint(
            machine_id="station_a",
            temperature_c=82.0,
            vibration_mm_s=3.4,
            current_a=2.6,
        )
    )

    assert recommendation.health_score < 0.4
    assert recommendation.status == "critical"
    assert "temperature trending high" in recommendation.reasons


def test_degradation_trend_detects_rising_sensor_values():
    points = [
        SensorPoint(
            "station_a", temperature_c=35 + i, vibration_mm_s=0.1 + i * 0.1, current_a=1.0
        )
        for i in range(12)
    ]

    trend = detect_degradation_trend(points, window=4)

    assert trend["trend"] == "degrading"
