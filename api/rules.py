"""
api/rules.py  --  Policy-based actuation engine (Member 5)
==========================================================
Pure Python, no framework imports, so it can be unit-tested without FastAPI / TensorFlow.

Inputs per tick
    indoor_now   : AQI measured by the sensor node right now
    indoor_pred  : AQI forecast by the Bi-LSTM for the next hour
    outdoor      : outdoor AQI for the city (reference feed)
    prev         : previous ActuationState (needed for hysteresis)

Design rules
    * PROACTIVE   - decisions use max(now, predicted), so devices react to a *forecast* spike.
    * HYSTERESIS  - each device has a higher ON threshold than OFF threshold, so a reading that
                    hovers around a limit does not make the relay chatter.
    * CONTEXT     - ventilation (exhaust fan / open window) is only allowed when the OUTDOOR air
                    is clearly cleaner than the indoor air. Dirty outside air is never pulled in.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass(frozen=True)
class Thresholds:
    purifier_low_on: float = 100.0    # > 100  -> purifier LOW   (CPCB "Moderate" starts)
    purifier_low_off: float = 90.0
    purifier_high_on: float = 200.0   # > 200  -> purifier HIGH  (CPCB "Poor" starts)
    purifier_high_off: float = 185.0
    window_close_outdoor: float = 150.0   # outdoor above this -> windows CLOSED
    window_open_outdoor: float = 120.0    # re-open only once outdoor is back below this
    vent_indoor_on: float = 150.0     # indoor above this AND outdoor clean -> flush with fresh air
    vent_indoor_off: float = 130.0
    vent_outdoor_max: float = 100.0   # never start ventilating if outdoor AQI is above this
    vent_outdoor_max_hold: float = 110.0
    vent_min_gap_on: float = 40.0     # outdoor must be at least this much cleaner than indoor
    vent_min_gap_hold: float = 30.0


DEFAULT_THRESHOLDS = Thresholds()


@dataclass
class ActuationState:
    purifier: str = "OFF"        # OFF | LOW | HIGH
    window: str = "OPEN"         # OPEN | CLOSED
    ventilation: str = "OFF"     # OFF | ON  (exhaust fan relay)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Decision:
    state: ActuationState
    changes: List[dict]          # [{"device","from","to","reason"}]
    reasons: List[str]           # human-readable explanation of the CURRENT state
    trigger: str                 # "predicted" | "current" | "none"

    def to_dict(self) -> dict:
        return {"state": self.state.to_dict(), "changes": self.changes,
                "reasons": self.reasons, "trigger": self.trigger}


def _purifier(prev: str, eff: float, t: Thresholds) -> str:
    if prev == "HIGH":
        return "HIGH" if eff > t.purifier_high_off else ("LOW" if eff > t.purifier_low_off else "OFF")
    if prev == "LOW":
        return "HIGH" if eff > t.purifier_high_on else ("LOW" if eff > t.purifier_low_off else "OFF")
    return "HIGH" if eff > t.purifier_high_on else ("LOW" if eff > t.purifier_low_on else "OFF")


def _ventilation(prev: str, eff: float, outdoor: float, t: Thresholds) -> str:
    if prev == "ON":
        keep = (eff > t.vent_indoor_off and outdoor <= t.vent_outdoor_max_hold
                and outdoor <= eff - t.vent_min_gap_hold)
        return "ON" if keep else "OFF"
    start = (eff > t.vent_indoor_on and outdoor <= t.vent_outdoor_max
             and outdoor <= eff - t.vent_min_gap_on)
    return "ON" if start else "OFF"


def _window(prev: str, outdoor: float, vent: str, t: Thresholds) -> str:
    if vent == "ON":                       # flushing needs the window open
        return "OPEN"
    if prev == "CLOSED":
        return "OPEN" if outdoor <= t.window_open_outdoor else "CLOSED"
    return "CLOSED" if outdoor > t.window_close_outdoor else "OPEN"


def evaluate(indoor_now: float, indoor_pred: float, outdoor: float,
             prev: Optional[ActuationState] = None,
             t: Thresholds = DEFAULT_THRESHOLDS) -> Decision:
    prev = prev or ActuationState()
    eff = max(indoor_now, indoor_pred)
    trigger = "none"
    if eff > t.purifier_low_on:
        trigger = "predicted" if indoor_pred > indoor_now else "current"

    new = ActuationState()
    new.purifier = _purifier(prev.purifier, eff, t)
    new.ventilation = _ventilation(prev.ventilation, eff, outdoor, t)
    new.window = _window(prev.window, outdoor, new.ventilation, t)

    if new.purifier == "HIGH":
        r_pur = (f"Purifier HIGH: max(now={indoor_now:.0f}, forecast={indoor_pred:.0f}) "
                 f"exceeds {t.purifier_high_on:.0f}")
    elif new.purifier == "LOW":
        r_pur = f"Purifier LOW: max(now, forecast)={eff:.0f} exceeds {t.purifier_low_on:.0f}"
    else:
        r_pur = f"Purifier OFF: indoor air acceptable (max(now, forecast)={eff:.0f})"

    if new.ventilation == "ON":
        r_vent = f"Fan ON: outdoor {outdoor:.0f} is cleaner than indoor {eff:.0f}, flushing with fresh air"
        r_win = "Window OPEN: required for ventilation"
    else:
        r_vent = "Fan OFF: no benefit from outdoor air right now"
        r_win = (f"Window CLOSED: outdoor AQI {outdoor:.0f} would worsen indoor air"
                 if new.window == "CLOSED" else f"Window OPEN: outdoor AQI {outdoor:.0f} is acceptable")

    per_device = {"purifier": r_pur, "ventilation": r_vent, "window": r_win}
    changes = [{"device": d, "from": getattr(prev, d), "to": getattr(new, d), "reason": per_device[d]}
               for d in ("purifier", "window", "ventilation") if getattr(prev, d) != getattr(new, d)]
    return Decision(new, changes, [r_pur, r_win, r_vent], trigger)
