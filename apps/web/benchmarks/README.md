# Local replay browser observations

Run all three real cached replay packs through one Chromium page:

```bash
cd apps/web
npm run benchmark:replay
```

This opt-in command starts the existing read-only API on `127.0.0.1:8012` and
Vite development server on `127.0.0.1:5182`, with no upstream downloads. Both
ports must be free. The normal `test:e2e` command does not discover this spec.
Build the supported Monza 2025, Monaco 2023 and São Paulo 2024 replay packs first
using the reproduction instructions in `docs/START_HERE.md` from the repo root.
Chromium must already be installed for the project's Playwright version.

Each session runs at 1× with a 1440×1000 viewport. It seeks to the recorded race
start, samples a visible document for four seconds, pauses, then seeks forward
10 seconds, back 10 seconds, and to session end. Twelve seeks and twelve seconds
of observation fit in a 45-second test timeout; server startup is additional.
The report is written beneath ignored `data/processed/browser_benchmarks/` with
a UTC timestamp. Existing successful reports are preserved.

The JSON contains raw requestAnimationFrame intervals and their median/p95,
callback cadence, supported Long Tasks API entries, canonical clock changes and
per-frame panel disagreement counts, state-request observations, decoded JSON
body byte counts, CDP JS heap snapshots, individual seek observations, source
hashes, manifest hashes, Git state and runtime/machine metadata. Clock agreement
is checked in one browser evaluation to avoid sampling different React commits.
A seek finishes when the requested API timestamp is visible on the main clock
and all eight panels. Request matching uses the exact target to exclude delayed
session-reset responses.

Interpret these measurements carefully:

- RAF cadence measures callback scheduling in a visible headless document. It
  does not measure painted frames, compositor throughput, smooth car motion or
  GPU FPS.
- Network duration includes the local proxy, API work and browser delivery.
  Body bytes measure decoded JSON; they do not measure compressed wire bytes.
  Failed/aborted fetches are retained, since cancellation can be normal on seek.
- The per-session request summary covers playback and subsequent seeks; raw
  request URLs preserve each requested time. Startup and race-start requests
  remain in the top-level request records.
- JS heap is measured without forced garbage collection. It excludes Python,
  browser native/GPU memory and other processes. A difference is not proof of
  a memory leak.
- Seek duration includes Playwright input dispatch, local API response and DOM
  observation. The harness does not isolate renderer-only latency.
- This is one short run with Vite development tooling and a shared host. Compare
  source/configuration fingerprints and concurrent workload before interpreting
  differences. Repeat independently for statistical claims or release budgets.

Assertions protect data availability, visible-document sampling, clock agreement
and absence of browser exceptions. There are no arbitrary latency/FPS gates.

The final fingerprint includes the extracted map/geometry renderer and backend
geometry/trail modules. The initial 2026-10-16 baseline predates those modules
and retains its original smaller fingerprint; missing baseline hashes are not
available. Geometry ID, centerline point count and source provenance are also
included in subsequent reports. These metadata additions do not change the
sampling algorithm. Later replay features and packs differ from that baseline,
so a before/after difference cannot identify a causal optimization benefit.
