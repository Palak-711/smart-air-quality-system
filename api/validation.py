from typing import Tuple, Dict, Any

class SensorValidator:
    """Validates raw sensor values and flags potential hardware anomalies or invalid drops."""

    MIN_PM25 = 0.0
    MAX_PM25 = 1000.0
    MAX_PM25_JUMP = 80.0  # Reasonable delta per reading

    def __init__(self):
        self.last_valid_pm25: Dict[str, float] = {}

    def validate_reading(self, city: str, pm25: float, pm10: float = None) -> Tuple[bool, str]:
        """Validates incoming PM2.5 readings for physical sanity and sensor jump anomalies."""
        
        # Check range bounds
        if pm25 < self.MIN_PM25 or pm25 > self.MAX_PM25:
            return False, f"PM2.5 reading {pm25} out of physical range [{self.MIN_PM25}, {self.MAX_PM25}]"

        # Check PM10 inconsistency if PM10 is supplied
        if pm10 is not None and pm10 < pm25:
            return False, f"Invalid reading: PM10 ({pm10}) cannot be smaller than PM2.5 ({pm25})"

        # Check for unphysical instantaneous jumps
        if city in self.last_valid_pm25:
            last_pm25 = self.last_valid_pm25[city]
            if abs(pm25 - last_pm25) > self.MAX_PM25_JUMP:
                return False, f"Unusual jump detected: delta {abs(pm25 - last_pm25)} exceeds threshold {self.MAX_PM25_JUMP}"

        # Update cached last valid reading
        self.last_valid_pm25[city] = pm25
        return True, "Valid"
