"""What-if / counterfactual race branch engine.

A 'branch' forks a real historical race at a chosen lap.  Laps 1..fork_lap use
measured times from the replay pack; laps fork_lap+1..end are simulated.
The two segments are stitched into one continuous timeline so strategy
comparisons are valid.

All simulated laps retain estimation='simulated'.  Historical laps get
estimation='historical'.  The splice boundary is explicitly labelled.

Use cases:
- "What if VER had pitted on lap 30 instead of lap 37?"
- "What if a safety car had appeared on lap 20?"
- "What would a two-stop have cost?"

Limitations (written into every BranchResult):
- Historical lap times include traffic, SC, personal effort and fuel effects
  that the simulator does not know about.  The simulated segment uses model-
  calibrated coefficients, not the same driver's real pace on that day.
- Fork lap is the last lap whose measured time is used; the first simulated
  lap begins with a fresh tyre state matching the counterfactual compound.
- No rival response is modelled; rivals continue their historical strategies.
- Spliced cumulative time at the fork inherits measured data noise.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from f1_racelab.strategy.models import (
    CIRCUIT_COMPOUNDS,
    CIRCUIT_FUEL,
    CIRCUIT_PIT,
    RACE_SPECS,
    Compound,
)
from f1_racelab.strategy.simulator import (
    Strategy,
    simulate_race,
)

PACK_ROOT = Path(__file__).resolve().parents[3] / 'data/processed/replay_packs'

BRANCH_LIMITS = (
    'Historical segment uses measured lap times; noise/SC/traffic are embedded.',
    'Simulated segment uses model coefficients, not the driver\'s real-day pace.',
    'Rivals\' strategies are unchanged; no rival response is simulated.',
    'Spliced cumulative time inherits measurement noise at the fork lap.',
    'Tyre age at fork start resets to 1 on the counterfactual compound.',
    'Fuel model uses constant burn rate; no energy deployment or fuel save.',
)


class BranchLap(BaseModel):
    """One lap in a what-if timeline — either historical or simulated."""
    model_config = ConfigDict(frozen=True)

    lap: int = Field(ge=1)
    driver_number: int = Field(gt=0)
    compound: Compound
    stint_lap: int = Field(ge=1)
    lap_time_s: float = Field(gt=0.0)
    cumulative_race_time_s: float = Field(ge=0.0)
    pitted_this_lap: bool = False
    pit_loss_s: float = 0.0
    estimation: Literal['historical', 'simulated']
    is_fork_lap: bool = False


class BranchResult(BaseModel):
    """Output of a what-if branch comparison."""
    model_config = ConfigDict(frozen=True)

    session_slug: str
    driver_number: int
    fork_lap: int
    actual_strategy_label: str
    counterfactual_strategy_label: str
    actual_laps: tuple[BranchLap, ...]
    counterfactual_laps: tuple[BranchLap, ...]
    actual_total_race_time_s: float
    counterfactual_total_race_time_s: float
    delta_counterfactual_vs_actual_s: float
    simulation_limits: tuple[str, ...] = BRANCH_LIMITS

    @property
    def counterfactual_is_faster(self) -> bool:
        return self.delta_counterfactual_vs_actual_s < 0.0


def _load_measured_laps(session_slug: str, driver_number: int,
                        pack_root: Path = PACK_ROOT) -> dict[int, float]:
    """Return {lap_number: lap_duration_seconds} for one driver from the pack."""
    candidates = list(pack_root.glob(f'{session_slug.replace("-", "_")}_race.json.gz'))
    if not candidates:
        raise FileNotFoundError(f'No race pack for {session_slug!r}')
    pack = json.loads(gzip.decompress(candidates[0].read_bytes()))
    driver_id = str(driver_number)
    return {
        e['payload']['lap_number']: e['payload']['lap_duration_seconds']
        for e in pack['events']
        if e['type'] == 'lap'
        and e['payload'].get('driver_id') == driver_id
        and isinstance(e['payload'].get('lap_duration_seconds'), (int, float))
    }


def _load_measured_stints(session_slug: str, driver_number: int,
                          pack_root: Path = PACK_ROOT) -> list[dict]:
    """Return stint records for one driver, sorted by lap_start."""
    candidates = list(pack_root.glob(f'{session_slug.replace("-", "_")}_race.json.gz'))
    if not candidates:
        raise FileNotFoundError(f'No race pack for {session_slug!r}')
    pack = json.loads(gzip.decompress(candidates[0].read_bytes()))
    driver_id = str(driver_number)
    stints = [
        e['payload'] for e in pack['events']
        if e['type'] == 'stint' and e['payload'].get('driver_id') == driver_id
    ]
    return sorted(stints, key=lambda s: s.get('lap_start', 0))


def _compound_at_lap(stints: list[dict], lap: int) -> Compound:
    """Return the compound in use on a given lap from stint records."""
    compound: Compound = 'MEDIUM'
    for s in stints:
        if s.get('lap_start', 1) <= lap:
            raw = s.get('compound', 'MEDIUM').upper()
            if raw in ('SOFT', 'MEDIUM', 'HARD', 'INTERMEDIATE', 'WET'):
                compound = raw  # type: ignore[assignment]
    return compound


def _historical_segment(
    session_slug: str,
    driver_number: int,
    fork_lap: int,
    pack_root: Path = PACK_ROOT,
) -> tuple[list[BranchLap], float]:
    """Build the historical prefix (laps 1..fork_lap) for one driver.

    Returns (laps, cumulative_time_at_fork).
    """
    measured = _load_measured_laps(session_slug, driver_number, pack_root)
    stints = _load_measured_stints(session_slug, driver_number, pack_root)
    spec = RACE_SPECS[session_slug]

    branch_laps: list[BranchLap] = []
    cumulative = 0.0
    stint_lap = 1
    current_compound = _compound_at_lap(stints, 1)

    for lap_number in range(1, min(fork_lap, spec.scheduled_laps) + 1):
        # Detect compound change at this lap
        lap_compound = _compound_at_lap(stints, lap_number)
        if lap_number > 1 and lap_compound != current_compound:
            stint_lap = 1
            current_compound = lap_compound
        else:
            if lap_number > 1:
                stint_lap += 1

        lap_time = measured.get(lap_number)
        if lap_time is None or lap_time <= 0:
            # Estimate from spec if missing
            lap_time = spec.base_lap_time_s

        # Detect pit on this lap: when next stint starts on lap_number + 1
        pitted = any(
            s.get('lap_start') == lap_number + 1
            for s in stints
        )
        pit_loss = 0.0
        if pitted:
            pit = CIRCUIT_PIT.get(session_slug)
            pit_loss = pit.total_pit_loss_s if pit else 25.0

        cumulative += lap_time
        branch_laps.append(BranchLap(
            lap=lap_number,
            driver_number=driver_number,
            compound=current_compound,
            stint_lap=stint_lap,
            lap_time_s=round(lap_time, 3),
            cumulative_race_time_s=round(cumulative, 3),
            pitted_this_lap=pitted,
            pit_loss_s=round(pit_loss, 3),
            estimation='historical',
            is_fork_lap=(lap_number == fork_lap),
        ))

        if pitted:
            stint_lap = 0  # will be incremented to 1 at start of next iteration

    return branch_laps, cumulative


def _simulated_segment(
    session_slug: str,
    driver_number: int,
    strategy: Strategy,
    fork_lap: int,
    cumulative_at_fork: float,
    pack_root: Path = PACK_ROOT,
) -> list[BranchLap]:
    """Simulate laps (fork_lap+1)..scheduled_laps for the counterfactual strategy.

    The simulation runs from lap 1 as usual (so tyre/fuel physics are correct),
    then we discard the first fork_lap laps and offset cumulative times so the
    simulated segment continues from cumulative_at_fork.
    """
    spec = RACE_SPECS[session_slug]
    compounds = CIRCUIT_COMPOUNDS[session_slug]
    fuel = CIRCUIT_FUEL[session_slug]
    pit = CIRCUIT_PIT[session_slug]

    results = simulate_race(spec=spec, strategies=[strategy],
                            compounds=compounds, fuel=fuel, pit=pit,
                            traffic=False)
    sim_laps = results[strategy.driver_number]

    # Discard laps up to and including fork_lap; re-root cumulative time
    offset = sim_laps[fork_lap - 1].cumulative_race_time_s if fork_lap <= len(sim_laps) else 0.0
    branch_laps: list[BranchLap] = []
    for lap_state in sim_laps[fork_lap:]:
        branch_laps.append(BranchLap(
            lap=lap_state.lap,
            driver_number=driver_number,
            compound=lap_state.compound,
            stint_lap=lap_state.stint_lap,
            lap_time_s=round(lap_state.realized_lap_time_s, 3),
            cumulative_race_time_s=round(
                cumulative_at_fork + lap_state.cumulative_race_time_s - offset, 3
            ),
            pitted_this_lap=lap_state.pitted_this_lap,
            pit_loss_s=round(lap_state.pit_loss_s, 3),
            estimation='simulated',
        ))
    return branch_laps


def branch(
    session_slug: str,
    driver_number: int,
    actual_strategy: Strategy,
    counterfactual_strategy: Strategy,
    fork_lap: int,
    pack_root: Path = PACK_ROOT,
) -> BranchResult:
    """Fork a real race at fork_lap and compare actual vs counterfactual.

    Returns a BranchResult with:
    - actual_laps: historical laps 1..end (using measured times from the pack
      for 1..fork_lap, then simulated with actual_strategy for rest)
    - counterfactual_laps: historical 1..fork_lap + simulated with
      counterfactual_strategy from fork_lap+1..end

    The historical segment is identical for both timelines; only the
    simulated suffix differs.
    """
    spec = RACE_SPECS[session_slug]
    if fork_lap < 1 or fork_lap >= spec.scheduled_laps:
        raise ValueError(
            f'fork_lap must be in [1, {spec.scheduled_laps - 1}]; got {fork_lap}'
        )

    # Build shared historical prefix
    hist_laps, cum_at_fork = _historical_segment(
        session_slug, driver_number, fork_lap, pack_root
    )

    # Build simulated suffixes for both strategies
    actual_suffix = _simulated_segment(
        session_slug, driver_number, actual_strategy,
        fork_lap, cum_at_fork, pack_root
    )
    counterfactual_suffix = _simulated_segment(
        session_slug, driver_number, counterfactual_strategy,
        fork_lap, cum_at_fork, pack_root
    )

    # Combine
    actual_full = hist_laps + actual_suffix
    counterfactual_full = hist_laps + counterfactual_suffix

    actual_total = actual_full[-1].cumulative_race_time_s if actual_full else 0.0
    cf_total = counterfactual_full[-1].cumulative_race_time_s if counterfactual_full else 0.0

    return BranchResult(
        session_slug=session_slug,
        driver_number=driver_number,
        fork_lap=fork_lap,
        actual_strategy_label=actual_strategy.label,
        counterfactual_strategy_label=counterfactual_strategy.label,
        actual_laps=tuple(actual_full),
        counterfactual_laps=tuple(counterfactual_full),
        actual_total_race_time_s=round(actual_total, 3),
        counterfactual_total_race_time_s=round(cf_total, 3),
        delta_counterfactual_vs_actual_s=round(cf_total - actual_total, 3),
    )
