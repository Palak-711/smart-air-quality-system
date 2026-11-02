import pytest
from api.validation import SensorValidator
from api.rules import evaluate_rules  # adjust import based on your rules structure

def test_sensor_validator_range():
    validator = SensorValidator()
    valid, msg = validator.validate_reading("Delhi", 45.0, 90.0)
    assert valid is True

    valid, msg = validator.validate_reading("Delhi", -5.0)
    assert valid is False

def test_pm10_less_than_pm25():
    validator = SensorValidator()
    valid, msg = validator.validate_reading("Delhi", 80.0, 40.0)
    assert valid is False
