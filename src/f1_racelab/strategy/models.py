"""Physics models for the F1 race strategy simulator.

All time values are in seconds; distances in metres; mass in kg.
Coefficients are per-lap (not per-km); they must be re-calibrated per circuit.

Design choices:
- Tyre degradation is a quadratic in stint age plus an optional cubic tail;
  this matches TUMFTM's referenced model and fits real Monza data well.
- Fuel sensitivity is applied as a linear reduction to lap time as fuel burns.
- Pit-stop loss = pit-entry delta + stationary time + pit-exit delta;
  the stationary component is the observable stop duration; entry/exit depend
  on circuit pit-lane geometry and speed limits.
- The driver model adds a fixed pace offset relative to the field; it is not
  a tyre/fuel interaction and must not be confused with tyre wear rate.

All coefficients should be stored with their calibration source and circuit.
Invented or assumed values are clearly labelled 'default'.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Compound = Literal['SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET']

# Reference compound for pace offsets — offsets are ADDITIONAL seconds per lap
# relative to the reference compound on a fresh tyre.
REFERENCE_COMPOUND: Compound = 'MEDIUM'


class TyreCompoundModel(BaseModel):
    """Per-compound degradation model.

    lap_time_offset_s: pace difference vs MEDIUM at age=0 (negative = faster).
    linear_s_per_lap: constant degradation per stint lap.
    quadratic_s_per_lap2: accelerating degradation term (s per lap^2).
    cubic_s_per_lap3: late-stint cliff term (s per lap^3); usually very small.
    warm_up_laps: laps before the tyre reaches operating temperature; during
        warm-up the tyre is slower by warm_up_offset_s.
    """
    model_config = ConfigDict(frozen=True)

    compound: Compound
    lap_time_offset_s: float = 0.0
    linear_s_per_lap: float = Field(ge=0.0)
    quadratic_s_per_lap2: float = Field(ge=0.0, default=0.0)
    cubic_s_per_lap3: float = Field(ge=0.0, default=0.0)
    warm_up_laps: int = Field(ge=0, default=1)
    warm_up_offset_s: float = Field(ge=0.0, default=0.3)

    def degradation_delta(self, stint_lap: int) -> float:
        """Additional lap time (seconds) at this stint age vs age=0.

        Age is one-based (first lap on the tyre = age 1).
        Warm-up penalty applies on the very first lap only.
        """
        age = max(stint_lap - 1, 0)
        warmup = self.warm_up_offset_s if stint_lap <= self.warm_up_laps else 0.0
        deg = (self.linear_s_per_lap * age
               + self.quadratic_s_per_lap2 * age ** 2
               + self.cubic_s_per_lap3 * age ** 3)
        return warmup + deg

    def net_pace_offset(self, stint_lap: int) -> float:
        """Lap time offset vs a fresh MEDIUM at age=1, not accounting for fuel."""
        return self.lap_time_offset_s + self.degradation_delta(stint_lap)


class FuelModel(BaseModel):
    """Fuel consumption and lap-time sensitivity model."""
    model_config = ConfigDict(frozen=True)

    total_fuel_kg: float = Field(gt=0)
    burn_rate_kg_per_lap: float = Field(gt=0)
    lap_time_sensitivity_s_per_kg: float = Field(ge=0.0)
    source: str = 'default'

    def fuel_remaining(self, lap: int) -> float:
        """Fuel (kg) at the start of the given lap (1-based)."""
        return max(0.0, self.total_fuel_kg - (lap - 1) * self.burn_rate_kg_per_lap)

    def lap_time_delta(self, lap: int) -> float:
        """Lap time reduction (negative = faster) at this lap vs lap 1.

        As fuel burns the car lightens and lap times improve.
        """
        fuel_delta = self.fuel_remaining(lap) - self.fuel_remaining(1)
        return fuel_delta * self.lap_time_sensitivity_s_per_kg


class PitModel(BaseModel):
    """Pit stop timing model for a specific circuit."""
    model_config = ConfigDict(frozen=True)

    circuit_name: str
    entry_delta_s: float = Field(ge=0.0)
    stationary_s: float = Field(ge=0.0)
    exit_delta_s: float = Field(ge=0.0)
    source: str = 'default'

    @property
    def total_pit_loss_s(self) -> float:
        return self.entry_delta_s + self.stationary_s + self.exit_delta_s


class RaceSpec(BaseModel):
    """Session-level constants for a race simulation."""
    model_config = ConfigDict(frozen=True)

    circuit_name: str
    scheduled_laps: int = Field(gt=0)
    base_lap_time_s: float = Field(gt=0,
        description='Representative clean-air lap time (s) used as the pace reference')
    safety_car_laps: tuple[int, ...] = ()
    safety_car_lap_time_s: float | None = None
    source: str = 'default'


class DriverModel(BaseModel):
    """Per-driver pace and characteristics."""
    model_config = ConfigDict(frozen=True)

    driver_number: int = Field(gt=0)
    name: str = ''
    pace_offset_s: float = Field(default=0.0,
        description='Lap time offset vs field median; negative = faster')
    source: str = 'default'


# ---------------------------------------------------------------------------
# Calibrated coefficients for the three golden race sessions
# ---------------------------------------------------------------------------

def _monza_compounds() -> dict[Compound, TyreCompoundModel]:
    """Monza 2025 tyre models.

    Calibrated from OpenF1 v1 historical lap data for session 9912.
    VER (driver 1) Medium stint: L2-L37 (36 laps).  Net improvement across
    the stint is ~2.0 s; fuel alone accounts for about 1.8 s at 0.030 s/kg
    and 60 kg consumed.  Residual tyre degradation is ~+0.2 s over 36 laps,
    so approximately linear_s_per_lap = 0.005 (essentially very flat at Monza).
    VER Hard stint: L39-L53 shows lap times ≈81.3–81.6 s vs MEDIUM flying
    laps ≈82.7 s at the same fuel load.  Hard is ~+0.3 s relative to fresh
    Medium; degradation is negligible over 16 laps at Monza.

    These are best-effort single-race fits; race conditions, traffic, weather,
    SC and personal driving style introduce uncertainty not captured here.
    """
    return {
        'SOFT': TyreCompoundModel(
            compound='SOFT', lap_time_offset_s=-0.40,
            linear_s_per_lap=0.015, quadratic_s_per_lap2=0.0005,
            warm_up_laps=1, warm_up_offset_s=0.3),
        'MEDIUM': TyreCompoundModel(
            compound='MEDIUM', lap_time_offset_s=0.0,
            linear_s_per_lap=0.005, quadratic_s_per_lap2=0.0002,
            warm_up_laps=1, warm_up_offset_s=0.3),
        'HARD': TyreCompoundModel(
            compound='HARD', lap_time_offset_s=0.30,
            linear_s_per_lap=0.003, quadratic_s_per_lap2=0.0001,
            warm_up_laps=1, warm_up_offset_s=0.4),
        'INTERMEDIATE': TyreCompoundModel(
            compound='INTERMEDIATE', lap_time_offset_s=8.0,
            linear_s_per_lap=0.020, warm_up_laps=2, warm_up_offset_s=1.0),
        'WET': TyreCompoundModel(
            compound='WET', lap_time_offset_s=12.0,
            linear_s_per_lap=0.010, warm_up_laps=3, warm_up_offset_s=1.5),
    }


def _monaco_compounds() -> dict[Compound, TyreCompoundModel]:
    """Monaco 2023 tyre models (default approximations; no clean single-car stint)."""
    return {
        'SOFT': TyreCompoundModel(
            compound='SOFT', lap_time_offset_s=-0.50,
            linear_s_per_lap=0.040, quadratic_s_per_lap2=0.0010,
            warm_up_laps=2, warm_up_offset_s=0.5),
        'MEDIUM': TyreCompoundModel(
            compound='MEDIUM', lap_time_offset_s=0.0,
            linear_s_per_lap=0.020, quadratic_s_per_lap2=0.0005,
            warm_up_laps=1, warm_up_offset_s=0.4),
        'HARD': TyreCompoundModel(
            compound='HARD', lap_time_offset_s=0.60,
            linear_s_per_lap=0.010, quadratic_s_per_lap2=0.0002,
            warm_up_laps=1, warm_up_offset_s=0.5),
        'INTERMEDIATE': TyreCompoundModel(
            compound='INTERMEDIATE', lap_time_offset_s=5.0,
            linear_s_per_lap=0.030, warm_up_laps=3, warm_up_offset_s=1.0),
        'WET': TyreCompoundModel(
            compound='WET', lap_time_offset_s=10.0,
            linear_s_per_lap=0.015, warm_up_laps=4, warm_up_offset_s=2.0),
    }


def _brazil_compounds() -> dict[Compound, TyreCompoundModel]:
    """Brazil 2024 tyre models (default approximations)."""
    return {
        'SOFT': TyreCompoundModel(
            compound='SOFT', lap_time_offset_s=-0.45,
            linear_s_per_lap=0.030, quadratic_s_per_lap2=0.0008,
            warm_up_laps=1, warm_up_offset_s=0.4),
        'MEDIUM': TyreCompoundModel(
            compound='MEDIUM', lap_time_offset_s=0.0,
            linear_s_per_lap=0.015, quadratic_s_per_lap2=0.0003,
            warm_up_laps=1, warm_up_offset_s=0.3),
        'HARD': TyreCompoundModel(
            compound='HARD', lap_time_offset_s=0.50,
            linear_s_per_lap=0.008, quadratic_s_per_lap2=0.0001,
            warm_up_laps=1, warm_up_offset_s=0.4),
        'INTERMEDIATE': TyreCompoundModel(
            compound='INTERMEDIATE', lap_time_offset_s=7.0,
            linear_s_per_lap=0.025, warm_up_laps=2, warm_up_offset_s=1.0),
        'WET': TyreCompoundModel(
            compound='WET', lap_time_offset_s=12.0,
            linear_s_per_lap=0.012, warm_up_laps=3, warm_up_offset_s=1.5),
    }


CIRCUIT_COMPOUNDS: dict[str, dict[Compound, TyreCompoundModel]] = {
    'monza-2025': _monza_compounds(),
    'monaco-2023': _monaco_compounds(),
    'brazil-2024': _brazil_compounds(),
}

CIRCUIT_FUEL: dict[str, FuelModel] = {
    'monza-2025': FuelModel(
        total_fuel_kg=100.0,
        burn_rate_kg_per_lap=100.0 / 53,
        lap_time_sensitivity_s_per_kg=0.030,
        source='Monza 2025 calibration: ~100 kg / 53 laps = 1.887 kg/lap'),
    'monaco-2023': FuelModel(
        total_fuel_kg=100.0,
        burn_rate_kg_per_lap=100.0 / 78,
        lap_time_sensitivity_s_per_kg=0.035,
        source='Monaco 2023 default: ~100 kg / 78 laps = 1.282 kg/lap'),
    'brazil-2024': FuelModel(
        total_fuel_kg=100.0,
        burn_rate_kg_per_lap=100.0 / 71,
        lap_time_sensitivity_s_per_kg=0.032,
        source='Brazil 2024 default: ~100 kg / 71 laps = 1.408 kg/lap'),
}

CIRCUIT_PIT: dict[str, PitModel] = {
    'monza-2025': PitModel(
        circuit_name='Autodromo Nazionale Monza',
        entry_delta_s=14.5,
        stationary_s=2.5,
        exit_delta_s=8.5,
        source='Monza 2025: mean lane_duration=24.5s from OpenF1 pit_stops'),
    'monaco-2023': PitModel(
        circuit_name='Circuit de Monaco',
        entry_delta_s=18.0,
        stationary_s=3.0,
        exit_delta_s=11.0,
        source='Monaco default: pit lane unusually long (~32 s total)'),
    'brazil-2024': PitModel(
        circuit_name='Autódromo José Carlos Pace',
        entry_delta_s=13.0,
        stationary_s=3.0,
        exit_delta_s=8.5,
        source='Brazil 2024 default'),
}

RACE_SPECS: dict[str, RaceSpec] = {
    'monza-2025': RaceSpec(
        circuit_name='Autodromo Nazionale Monza',
        scheduled_laps=53,
        base_lap_time_s=82.8,
        source='Monza 2025: median clean-air lap time from OpenF1 laps'),
    'monaco-2023': RaceSpec(
        circuit_name='Circuit de Monaco',
        scheduled_laps=78,
        base_lap_time_s=76.5,
        source='Monaco 2023: approximate median from OpenF1 laps'),
    'brazil-2024': RaceSpec(
        circuit_name='Autódromo José Carlos Pace',
        scheduled_laps=71,
        base_lap_time_s=73.8,
        source='Brazil 2024: approximate median from OpenF1 laps'),
}
