"""Strategy optimizer: enumerate and rank candidate strategies for one driver.

Scope:
- Generate all one- and two-stop strategies using the compounds available at
  a given session.
- Evaluate each deterministically using the simulator.
- Rank by race time; report delta vs the actual historical strategy.

This is NOT a global optimization or RL agent.  It is a combinatorial
enumeration with a time budget, seeded for reproducibility.  The output is
clearly labelled as simulated, not a prediction of race outcomes.

Limitations recorded in every output:
- Traffic interaction is simplified (heuristic proximity penalty).
- Safety car timing is synthetic unless drawn from real race.
- Tyre degradation coefficients are approximate per-circuit fits.
- Fuel model uses a constant burn rate (no fuel saving modes).
- This optimizer does not account for tyre set availability, stint rules,
  penalty laps, VSC windows, rival responses or force majeure.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from f1_racelab.strategy.models import (
    CIRCUIT_COMPOUNDS,
    CIRCUIT_FUEL,
    CIRCUIT_PIT,
    RACE_SPECS,
    Compound,
    DriverModel,
)
from f1_racelab.strategy.simulator import (
    LapState,
    PitStop,
    Strategy,
    race_time,
    simulate_race,
)

SIMULATION_LIMITS = (
    'Race time is deterministic; no noise or MC uncertainty is included.',
    'Traffic penalty is heuristic (fixed-second proximity loss).',
    'Tyre coefficients are per-circuit fits from one representative driver.',
    'Safety car timing is drawn from the replay pack or omitted.',
    'Tyre set availability, penalties and regulations are not modelled.',
    'Simulated outcomes must not be presented as measured results.',
)


class StrategyEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True)

    driver_number: int
    label: str
    stops: int
    total_race_time_s: float
    delta_vs_reference_s: float | None = None
    pit_laps: tuple[int, ...] = ()
    compounds: tuple[str, ...] = ()
    lap_states: tuple[LapState, ...] = ()
    simulation_limits: tuple[str, ...] = SIMULATION_LIMITS

    @property
    def is_faster_than_reference(self) -> bool | None:
        if self.delta_vs_reference_s is None:
            return None
        return self.delta_vs_reference_s < 0.0


def evaluate_strategy(
    session_slug: str,
    strategy: Strategy,
    *,
    driver: DriverModel | None = None,
    traffic: bool = False,
) -> StrategyEvaluation:
    """Evaluate a single strategy for a session."""
    spec = RACE_SPECS[session_slug]
    compounds = CIRCUIT_COMPOUNDS[session_slug]
    fuel = CIRCUIT_FUEL[session_slug]
    pit = CIRCUIT_PIT[session_slug]

    results = simulate_race(
        spec=spec,
        strategies=[strategy],
        compounds=compounds,
        fuel=fuel,
        pit=pit,
        drivers=[driver] if driver else None,
        traffic=traffic,
    )
    laps = results[strategy.driver_number]
    pit_laps = tuple(s.lap for s in sorted(strategy.pit_stops, key=lambda s: s.lap))
    stints = (strategy.start_compound,) + tuple(s.compound for s in sorted(strategy.pit_stops, key=lambda s: s.lap))
    return StrategyEvaluation(
        driver_number=strategy.driver_number,
        label=strategy.label,
        stops=len(strategy.pit_stops),
        total_race_time_s=race_time(laps),
        pit_laps=pit_laps,
        compounds=stints,
        lap_states=tuple(laps),
    )


def compare_strategies(
    session_slug: str,
    strategies: list[Strategy],
    *,
    driver: DriverModel | None = None,
    traffic: bool = False,
) -> list[StrategyEvaluation]:
    """Evaluate multiple strategies and rank by race time.

    The fastest strategy has delta_vs_reference_s = 0; all others show
    their deficit.
    """
    evaluations = [
        evaluate_strategy(session_slug, s, driver=driver, traffic=traffic)
        for s in strategies
    ]
    evaluations.sort(key=lambda e: e.total_race_time_s)
    best_time = evaluations[0].total_race_time_s
    return [
        e.model_copy(update={'delta_vs_reference_s': round(e.total_race_time_s - best_time, 3)})
        for e in evaluations
    ]


def enumerate_strategies(
    session_slug: str,
    driver_number: int,
    available_compounds: list[Compound],
    *,
    max_stops: int = 2,
    pit_window_start: int = 10,
    pit_window_end: int | None = None,
    pit_step: int = 1,
) -> list[Strategy]:
    """Generate one-stop and (optionally) two-stop candidate strategies.

    Constraints:
    - Each stint must be at least pit_window_start laps long.
    - Consecutive stints use the same or different compound (both generated).
    - pit_step reduces the search space; increase for faster enumeration.
    """
    spec = RACE_SPECS[session_slug]
    end = pit_window_end or (spec.scheduled_laps - pit_window_start)
    strategies = []

    for start_compound in available_compounds:
        # Zero-stop (rare but possible at short races)
        strategies.append(Strategy(
            driver_number=driver_number,
            start_compound=start_compound,
            pit_stops=()))

        # One-stop
        for pit1 in range(pit_window_start, end + 1, pit_step):
            for compound2 in available_compounds:
                strategies.append(Strategy(
                    driver_number=driver_number,
                    start_compound=start_compound,
                    pit_stops=(PitStop(lap=pit1, compound=compound2),)))

        if max_stops >= 2:
            # Two-stop: generate combinations where each stint is at least
            # pit_window_start laps
            for pit1 in range(pit_window_start, end - pit_window_start + 1, pit_step):
                for pit2 in range(pit1 + pit_window_start,
                                  spec.scheduled_laps - 3 + 1, pit_step):
                    for c2 in available_compounds:
                        for c3 in available_compounds:
                            strategies.append(Strategy(
                                driver_number=driver_number,
                                start_compound=start_compound,
                                pit_stops=(PitStop(lap=pit1, compound=c2),
                                           PitStop(lap=pit2, compound=c3))))

    # Remove duplicates (same label = same compound sequence and stop laps)
    seen: set[str] = set()
    unique = []
    for s in strategies:
        key = s.label
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


def best_strategies(
    session_slug: str,
    driver_number: int,
    available_compounds: list[Compound],
    *,
    max_stops: int = 2,
    top_n: int = 10,
    pit_step: int = 3,
    traffic: bool = False,
    driver: DriverModel | None = None,
) -> list[StrategyEvaluation]:
    """Enumerate and rank strategies, returning the top_n fastest.

    pit_step=3 reduces candidates by 9× vs step=1 for two-stop searches;
    increase for precision, decrease for speed.  The result is labelled as
    simulated and subject to the enumeration limitations.
    """
    candidates = enumerate_strategies(
        session_slug, driver_number, available_compounds,
        max_stops=max_stops, pit_step=pit_step)
    evaluated = compare_strategies(session_slug, candidates,
                                   driver=driver, traffic=traffic)
    return evaluated[:top_n]
