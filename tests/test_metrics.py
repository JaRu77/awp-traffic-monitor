from awp_traffic.metrics import calculate_metrics, interpret_conditions


def test_calculate_metrics_for_nominal_values():
    metrics = calculate_metrics(
        current_speed=30,
        free_flow_speed=60,
        current_travel_time=120,
        free_flow_travel_time=60,
        confidence=0.9,
    )

    assert metrics.congestion_index == 0.5
    assert metrics.delay_ratio == 2.0
    assert metrics.delay_seconds == 60
    assert metrics.interpretation == "silne przeciazenie"


def test_calculate_metrics_handles_missing_denominator():
    metrics = calculate_metrics(
        current_speed=30,
        free_flow_speed=0,
        current_travel_time=120,
        free_flow_travel_time=None,
        confidence=0.9,
    )

    assert metrics.congestion_index is None
    assert metrics.delay_ratio is None
    assert metrics.delay_seconds is None
    assert metrics.interpretation == "brak danych lub niska wiarygodnosc"


def test_low_confidence_overrides_other_interpretation():
    metrics = calculate_metrics(
        current_speed=60,
        free_flow_speed=60,
        current_travel_time=60,
        free_flow_travel_time=60,
        confidence=0.2,
    )

    assert metrics.interpretation == "brak danych lub niska wiarygodnosc"


def test_interpretation_categories():
    assert interpret_conditions(0.95, 1.05, confidence=0.9) == "ruch plynny"
    assert interpret_conditions(0.80, 1.20, confidence=0.9) == "lekkie spowolnienie"
    assert interpret_conditions(0.55, 1.70, confidence=0.9) == "wyrazne spowolnienie"
    assert interpret_conditions(0.30, 2.20, confidence=0.9) == "silne przeciazenie"
