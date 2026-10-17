"""Deterministic single- and multi-car race lap simulator.

The simulator reduces car state lap-by-lap using physics models from models.py.
It tracks free pace (what a car would do in clean air) and realized pace
(with safety-car restrictions and traffic penalties).

Key design decisions:
- Lap times are computed deterministically; Monte Carlo noise is added in
  monte_carlo.py, not here.  This makes unit tests stable.
- Safety car laps use a fixed SC lap time; all cars converge to the same pace.
- Traffic penalty is applied when a faster car is within a time window behind
  a slower car; this is heuristic and not aerodynamic simulation.
- A pit stop is scheduled for a specific lap number; the lap on which a driver
  pits takes the entry delta + stationary + exit delta as extra lap time.
- The lap state emitted at each step is immutable (frozen Pydantic model) for
  deterministic replay and seek.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from f1_racelab.strategy.models import (
    Compound,
    DriverModel,
    FuelModel,
    PitModel,
    RaceSpec,
    TyreCompoundModel,
)

TRAFFIC_WINDOW_S: float = 2.0
TRAFFIC_PENALTY_S: float = 0.3


class PitStop(BaseModel):
    model_config = ConfigDict(frozen=True)
    lap: int = Field(gt=0, description='Lap on which the driver enters the pits')
    compound: Compound = Field(description='Compound fitted after the stop')


class Strategy(BaseModel):
    model_config = ConfigDict(frozen=True)
    driver_number: int = Field(gt=0)
    start_compound: Compound
    pit_stops: tuple[PitStop, ...] = ()

    @property
    def label(self) -> str:
        if not self.pit_stops:
            return f'{self.start_compound[0]}'
        parts = [self.start_compound[0]]
        for s in sorted(self.pit_stops, key=lambda p: p.lap):
            parts.append(f'→L{s.lap}→{s.compound[0]}')
        return ''.join(parts)


class LapState(BaseModel):
    """Immutable per-lap per-driver simulation result."""
    model_config = ConfigDict(frozen=True)

    lap: int = Field(ge=1)
    driver_number: int = Field(gt=0)
    compound: Compound
    stint_lap: int = Field(ge=1)
    fuel_kg: float = Field(ge=0.0)
    free_lap_time_s: float = Field(gt=0.0)
    realized_lap_time_s: float = Field(gt=0.0)
    cumulative_race_time_s: float = Field(ge=0.0)
    pitted_this_lap: bool = False
    pit_loss_s: float = 0.0
    is_safety_car_lap: bool = False
    traffic_penalty_s: float = 0.0
    estimation: Literal['simulated'] = 'simulated'


class CarSimulationState:
    """Mutable running state updated each lap (not serialized directly)."""

    def __init__(self, strategy: Strategy, fuel_model: FuelModel) -> None:
        self.driver_number = strategy.driver_number
        self.strategy = strategy
        self.fuel_model = fuel_model
        self.compound: Compound = strategy.start_compound
        self.stint_lap = 1
        self.cumulative_time = 0.0
        self._pit_map: dict[int, Compound] = {s.lap: s.compound for s in strategy.pit_stops}

    def fuel_at_lap(self, lap: int) -> float:
        return self.fuel_model.fuel_remaining(lap)

    def is_pitting(self, lap: int) -> bool:
        return lap in self._pit_map


def simulate_race(
    spec: RaceSpec,
    strategies: list[Strategy],
    compounds: dict[Compound, TyreCompoundModel],
    fuel: FuelModel,
    pit: PitModel,
    drivers: list[DriverModel] | None = None,
    traffic: bool = True,
) -> dict[int, list[LapState]]:
    """Simulate a full race for all drivers, lap by lap.

    Returns a dict mapping driver_number → list of LapState (len = scheduled_laps).
    Safety car laps are drawn from spec.safety_car_laps.  Traffic is applied
    when a car's on-track position (based on cumulative time) is within
    TRAFFIC_WINDOW_S of the car ahead.

    All generated LapState objects have estimation='simulated'; they must
    never be mixed with historical measured data without a visible label.
    """
    driver_models = {d.driver_number: d for d in (drivers or [])}
    cars = {s.driver_number: CarSimulationState(s, fuel) for s in strategies}
    results: dict[int, list[LapState]] = {s.driver_number: [] for s in strategies}
    sc_laps = set(spec.safety_car_laps)
    sc_time = spec.safety_car_lap_time_s or (spec.base_lap_time_s * 1.40)

    for lap in range(1, spec.scheduled_laps + 1):
        lap_times: dict[int, float] = {}
        is_sc = lap in sc_laps

        for driver_number, car in cars.items():
            fuel_at = car.fuel_at_lap(lap)
            tyre = compounds[car.compound]
            driver = driver_models.get(driver_number)
            pace_offset = driver.pace_offset_s if driver else 0.0

            if is_sc:
                free_time = sc_time
            else:
                free_time = (
                    spec.base_lap_time_s
                    + pace_offset
                    + tyre.net_pace_offset(car.stint_lap)
                    + fuel.lap_time_delta(lap)
                )

            pitting = car.is_pitting(lap)
            pit_loss = pit.total_pit_loss_s if pitting else 0.0
            realized = free_time + pit_loss
            lap_times[driver_number] = realized

        # Traffic: sort cars by cumulative race time ascending (leader first).
        sorted_drivers = sorted(cars.keys(), key=lambda d: cars[d].cumulative_time)
        traffic_penalties: dict[int, float] = {}
        if traffic and not is_sc:
            for i in range(1, len(sorted_drivers)):
                ahead_num = sorted_drivers[i - 1]
                behind_num = sorted_drivers[i]
                ahead_total = cars[ahead_num].cumulative_time + lap_times[ahead_num]
                behind_total = cars[behind_num].cumulative_time + lap_times[behind_num]
                gap = behind_total - ahead_total
                if gap < TRAFFIC_WINDOW_S and lap_times[behind_num] < lap_times[ahead_num]:
                    traffic_penalties[behind_num] = TRAFFIC_PENALTY_S

        for driver_number, car in cars.items():
            pitting = car.is_pitting(lap)
            pit_loss = pit.total_pit_loss_s if pitting else 0.0
            traffic_pen = traffic_penalties.get(driver_number, 0.0)
            realized = lap_times[driver_number] + traffic_pen
            car.cumulative_time += realized

            state = LapState(
                lap=lap,
                driver_number=driver_number,
                compound=car.compound,
                stint_lap=car.stint_lap,
                fuel_kg=car.fuel_at_lap(lap),
                free_lap_time_s=lap_times[driver_number] - (pit_loss),
                realized_lap_time_s=realized,
                cumulative_race_time_s=car.cumulative_time,
                pitted_this_lap=pitting,
                pit_loss_s=pit_loss,
                is_safety_car_lap=is_sc,
                traffic_penalty_s=traffic_pen,
            )
            results[driver_number].append(state)

            # Advance tyre state: update compound and stint_lap AFTER recording.
            if pitting:
                car.compound = car._pit_map[lap]
                car.stint_lap = 1
            else:
                car.stint_lap += 1

    return results


def race_time(laps: list[LapState]) -> float:
    """Total race time from the last lap's cumulative time."""
    return laps[-1].cumulative_race_time_s if laps else 0.0


def gap_history(
    laps_a: list[LapState],
    laps_b: list[LapState],
) -> list[float]:
    """Lap-by-lap gap in seconds: B cumulative time − A cumulative time.

    Positive = A is ahead of B; negative = B is ahead.
    The two lists must have the same length (same scheduled_laps race).
    """
    if len(laps_a) != len(laps_b):
        raise ValueError('Gap history requires equal lap counts')
    return [b.cumulative_race_time_s - a.cumulative_race_time_s
            for a, b in zip(laps_a, laps_b)]


def undercut_window(
    laps_a: list[LapState],
    laps_b: list[LapState],
    pit_model: PitModel,
    *,
    min_lap: int = 5,
    max_lap: int | None = None,
) -> list[dict]:
    """Identify laps where B could undercut A.

    B can undercut A on lap N when:
    - B is behind A (gap > 0) by less than pit_model.total_pit_loss_s.
    - After A's next scheduled stop, B would emerge ahead.
    This is a simplified forward-looking check; it does not simulate the
    full race from lap N onward.

    Returns a list of {lap, gap_s, pit_loss_s, undercut_feasible}.
    """
    limit = max_lap or len(laps_a)
    gaps = gap_history(laps_a, laps_b)
    windows = []
    for i, lap in enumerate(range(1, len(laps_a) + 1)):
        if lap < min_lap or lap > limit:
            continue
        gap = gaps[i]
        feasible = 0.0 < gap < pit_model.total_pit_loss_s
        windows.append({'lap': lap, 'gap_s': round(gap, 3),
                        'pit_loss_s': round(pit_model.total_pit_loss_s, 3),
                        'undercut_feasible': feasible})
    return windows
