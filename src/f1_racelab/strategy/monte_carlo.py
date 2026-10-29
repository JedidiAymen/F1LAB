"""Monte Carlo race simulation with seeded random worlds.

Each world applies per-lap Gaussian noise to free lap times.  All candidate
strategies in a comparison share the same world's noise sequence, so relative
strategy deltas are measured against identical conditions rather than noise
from different draws.  This is the 'common random worlds' technique.

Noise model (per lap, per driver):
- lap_sigma_s: standard deviation of per-lap time variation (default 0.12 s).
  This covers driver errors, minor traffic, DRS gaps and measurement variation.
  It does NOT model major incidents, retirements, mechanical failures or SC.
- pit_sigma_s: extra sigma on the pit stop stationary time (default 0.4 s).
  This covers tyre gun hesitations, wheel nut issues, traffic in the pit lane.

Limitations (included in every MC result):
- Mechanical failures, retirements, weather changes and SC timing are not
  sampled; the user must include known SC laps from spec explicitly.
- The noise distribution is Gaussian, which does not capture rare large
  incidents.
- Shared noise worlds are only valid when all strategies are evaluated against
  the same spec/models; different circuits or different calibrations require
  separate worlds.
"""
from __future__ import annotations

import random
from statistics import mean, stdev

from pydantic import BaseModel, ConfigDict, Field

from f1_racelab.strategy.models import (
    CIRCUIT_COMPOUNDS,
    CIRCUIT_FUEL,
    CIRCUIT_PIT,
    RACE_SPECS,
    DriverModel,
)
from f1_racelab.strategy.optimizer import (
    SIMULATION_LIMITS,
)
from f1_racelab.strategy.simulator import (
    LapState,
    Strategy,
    race_time,
    simulate_race,
)

MC_LIMITS = SIMULATION_LIMITS + (
    'Monte Carlo noise is Gaussian; rare large incidents are not sampled.',
    'SC/retirements/weather changes must be provided explicitly in the race spec.',
    'Shared noise worlds require identical spec and model inputs.',
)


class MCWorld:
    """One seeded noise world for a fixed number of laps and drivers."""

    def __init__(self, seed: int, n_laps: int, driver_numbers: list[int],
                 lap_sigma_s: float = 0.12, pit_sigma_s: float = 0.4) -> None:
        rng = random.Random(seed)
        self.lap_noise: dict[int, list[float]] = {}
        self.pit_noise: dict[int, list[float]] = {}
        for d in driver_numbers:
            self.lap_noise[d] = [rng.gauss(0, lap_sigma_s) for _ in range(n_laps)]
            self.pit_noise[d] = [rng.gauss(0, pit_sigma_s) for _ in range(n_laps)]

    def apply(self, base_laps: list[LapState]) -> list[LapState]:
        """Return a new list of LapState with per-lap noise applied."""
        result: list[LapState] = []
        d = base_laps[0].driver_number
        for i, lap in enumerate(base_laps):
            noise = self.lap_noise[d][i]
            pit_n = self.pit_noise[d][i] if lap.pitted_this_lap else 0.0
            adjusted = lap.realized_lap_time_s + noise + pit_n
            # Recompute cumulative: start from previous lap's cumulative
            prev_cum = result[-1].cumulative_race_time_s if result else 0.0
            result.append(lap.model_copy(update={
                'realized_lap_time_s': adjusted,
                'cumulative_race_time_s': prev_cum + adjusted,
            }))
        return result


class MCResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_label: str
    driver_number: int
    n_worlds: int
    mean_race_time_s: float
    std_race_time_s: float
    p5_race_time_s: float
    p50_race_time_s: float
    p95_race_time_s: float
    mean_delta_vs_fastest_s: float
    win_fraction: float = Field(ge=0.0, le=1.0,
        description='Fraction of worlds in which this strategy had the lowest race time')
    simulation_limits: tuple[str, ...] = MC_LIMITS


def mc_compare(
    session_slug: str,
    strategies: list[Strategy],
    *,
    n_worlds: int = 500,
    seed: int = 42,
    driver: DriverModel | None = None,
    lap_sigma_s: float = 0.12,
    pit_sigma_s: float = 0.4,
) -> list[MCResult]:
    """Compare strategies over N shared random worlds, ranked by mean race time.

    All strategies use the same per-world noise sequence, isolating the
    strategic delta from random variance.  The seed is fixed by default;
    change it to verify stability.
    """
    spec = RACE_SPECS[session_slug]
    compounds = CIRCUIT_COMPOUNDS[session_slug]
    fuel = CIRCUIT_FUEL[session_slug]
    pit = CIRCUIT_PIT[session_slug]
    driver_numbers = [s.driver_number for s in strategies]

    base_results: dict[str, list[LapState]] = {}
    for strategy in strategies:
        res = simulate_race(spec=spec, strategies=[strategy], compounds=compounds,
                            fuel=fuel, pit=pit,
                            drivers=[driver] if driver else None, traffic=False)
        base_results[strategy.label] = res[strategy.driver_number]

    world_times: dict[str, list[float]] = {s.label: [] for s in strategies}
    for world_seed in range(seed, seed + n_worlds):
        world = MCWorld(world_seed, spec.scheduled_laps, driver_numbers,
                        lap_sigma_s=lap_sigma_s, pit_sigma_s=pit_sigma_s)
        world_totals: dict[str, float] = {}
        for strategy in strategies:
            noisy = world.apply(base_results[strategy.label])
            world_totals[strategy.label] = race_time(noisy)
        for label, t in world_totals.items():
            world_times[label].append(t)

    results: list[MCResult] = []
    all_world_means = {label: mean(times) for label, times in world_times.items()}
    fastest_mean = min(all_world_means.values())

    for strategy in strategies:
        label = strategy.label
        times = sorted(world_times[label])
        n = len(times)
        wins = sum(1 for world_seed in range(seed, seed + n_worlds)
                   if world_times[label][world_seed - seed] == min(
                       world_times[s.label][world_seed - seed] for s in strategies))
        results.append(MCResult(
            strategy_label=label,
            driver_number=strategy.driver_number,
            n_worlds=n_worlds,
            mean_race_time_s=round(mean(times), 3),
            std_race_time_s=round(stdev(times) if len(times) > 1 else 0.0, 3),
            p5_race_time_s=round(times[max(0, int(n * 0.05))], 3),
            p50_race_time_s=round(times[n // 2], 3),
            p95_race_time_s=round(times[min(n - 1, int(n * 0.95))], 3),
            mean_delta_vs_fastest_s=round(mean(times) - fastest_mean, 3),
            win_fraction=round(wins / n_worlds, 4),
        ))

    results.sort(key=lambda r: r.mean_race_time_s)
    return results
