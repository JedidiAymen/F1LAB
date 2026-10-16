import { expect, test, type Page, type Request } from '@playwright/test'
import { createHash } from 'node:crypto'
import { execFileSync } from 'node:child_process'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'

const panelNames = [
  'Timing tower', 'Circuit position map', 'Driver focus', 'Race control feed',
  'Weather observations', 'Session summary', 'Tyre stints', 'Telemetry comparison',
]
const playbackWindowMs = 4000
const sha256 = (value: string | Buffer) => createHash('sha256').update(value).digest('hex')

function summary(values: number[]) {
  const sorted = [...values].sort((a, b) => a - b)
  const percentile = (p: number) => sorted.length ? sorted[Math.ceil(p * sorted.length) - 1] : null
  return { count: values.length, min: sorted[0] ?? null, median: percentile(0.5), p95: percentile(0.95), max: sorted.at(-1) ?? null }
}

async function clocks(page: Page) {
  return page.evaluate((names) => {
    const seconds = document.querySelector('[data-testid="state-clock"]')?.getAttribute('data-seconds') ?? null
    const panels = Object.fromEntries(names.map((name) => [name,
      document.querySelector(`[aria-label="${name}"]`)?.getAttribute('data-session-time') ?? null,
    ]))
    return { seconds, panels, agree: seconds !== null && Object.values(panels).every((value) => value === seconds) }
  }, panelNames)
}

async function measuredSeek(page: Page, name: string, targetSeconds: number, action: () => Promise<unknown>) {
  const responsePromise = page.waitForResponse((response) => /\/state\?seconds=/.test(response.url()) && response.ok() && Number(new URL(response.url()).searchParams.get('seconds')) === Number(targetSeconds.toFixed(3)))
  const started = performance.now()
  await action()
  const response = await responsePromise
  const target = Number(new URL(response.url()).searchParams.get('seconds'))
  await page.waitForFunction(({ seconds, names }) => {
    const clock = document.querySelector('[data-testid="state-clock"]')?.getAttribute('data-seconds')
    return Number(clock) === seconds && names.every((panel) =>
      document.querySelector(`[aria-label="${panel}"]`)?.getAttribute('data-session-time') === clock)
  }, { seconds: target, names: panelNames })
  return { name, requested_seconds: target, input_to_synchronized_dom_ms: performance.now() - started, clocks: await clocks(page) }
}

test('record real replay browser observations without performance thresholds', async ({ page, browser, request }, testInfo) => {
  const startedUtc = new Date().toISOString()
  const repo = path.resolve(import.meta.dirname, '../../..')
  const catalogResponse = await request.get('/api/v1/replays')
  expect(catalogResponse.ok()).toBe(true)
  const catalog = await catalogResponse.json() as { slug: string; available: boolean }[]
  expect(catalog.filter((entry) => !entry.available), 'Build the three real replay packs first').toEqual([])
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  const records: { slug: string; url: string; status: number | null; elapsed_ms: number; decoded_body_bytes: number | null; failure: string | null }[] = []
  const requests = new Map<Request, number>()
  const completions: Promise<void>[] = []
  let activeSlug = ''
  page.on('request', (req) => {
    if (/\/state\?seconds=/.test(req.url())) requests.set(req, performance.now())
  })
  page.on('requestfinished', (req) => {
    const start = requests.get(req)
    if (start === undefined) return
    const slug = activeSlug
    const elapsed = performance.now() - start
    completions.push((async () => {
      const response = await req.response()
      let bytes: number | null = null
      try { bytes = response ? (await response.body()).byteLength : null } catch { /* Context may close after an aborted request. */ }
      records.push({ slug, url: req.url(), status: response?.status() ?? null, elapsed_ms: elapsed, decoded_body_bytes: bytes, failure: null })
    })())
  })
  page.on('requestfailed', (req) => {
    const start = requests.get(req)
    if (start !== undefined) records.push({ slug: activeSlug, url: req.url(), status: null, elapsed_ms: performance.now() - start, decoded_body_bytes: null, failure: req.failure()?.errorText ?? 'unknown' })
  })
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Performance.enable')
  const heap = async () => {
    const result = await cdp.send('Performance.getMetrics')
    return Object.fromEntries(result.metrics.filter((metric) => ['JSHeapUsedSize', 'JSHeapTotalSize', 'Nodes', 'Documents'].includes(metric.name)).map((metric) => [metric.name, metric.value]))
  }
  const sessions: unknown[] = []
  for (const [index, sessionName] of ['2025 Italian Grand Prix', '2023 Monaco Grand Prix', '2024 São Paulo Grand Prix'].entries()) {
    activeSlug = catalog[index].slug
    if (index === 0) {
      await page.goto('/')
      await expect(page.locator('.timing-row')).toHaveCount(20)
    } else {
      await page.getByRole('combobox', { name: 'Historical session' }).click()
      await page.getByRole('option', { name: sessionName, exact: true }).click()
      await expect(page.getByTestId('state-clock')).toHaveAttribute('data-seconds', '0')
    }
    // Source URL identifies the pack; friendly labels vary between metadata providers.
    const manifestResponse = await request.get(`/api/v1/replay/${catalog[index].slug}/manifest`)
    const manifestText = await manifestResponse.text()
    const manifest = JSON.parse(manifestText) as { duration_seconds: number; race_control: { session_time_seconds: number; payload: { message: string } }[]; provider: unknown; geometry: { geometry_id?: string; centerline_xy?: unknown[]; provenance?: unknown } }
    const beforeHeap = await heap()
    const raceStart = await measuredSeek(page, 'race_start', manifest.race_control.find((event) => event.payload.message === 'SESSION STARTED')!.session_time_seconds, () => page.getByRole('button', { name: 'Jump to race start' }).click())
    const requestStart = records.length
    await page.getByRole('button', { name: 'Play replay' }).click()
    const playback = await page.evaluate(async ({ duration, names }) => {
      const intervals: number[] = []
      const longTasks: { start_ms: number; duration_ms: number }[] = []
      const clockChanges: { offset_ms: number; seconds: string | null }[] = []
      let mismatches = 0
      let hiddenFrames = 0
      let lastSeconds: string | null = null
      const supported = PerformanceObserver.supportedEntryTypes.includes('longtask')
      const observer = supported ? new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) longTasks.push({ start_ms: entry.startTime, duration_ms: entry.duration })
      }) : null
      observer?.observe({ type: 'longtask' })
      const start = performance.now()
      let previous: number | null = null
      await new Promise<void>((resolve) => {
        const frame = (now: number) => {
          if (previous !== null) intervals.push(now - previous)
          previous = now
          if (document.visibilityState !== 'visible') hiddenFrames++
          const seconds = document.querySelector('[data-testid="state-clock"]')?.getAttribute('data-seconds') ?? null
          if (seconds !== lastSeconds) { clockChanges.push({ offset_ms: now - start, seconds }); lastSeconds = seconds }
          if (seconds === null || names.some((name) => document.querySelector(`[aria-label="${name}"]`)?.getAttribute('data-session-time') !== seconds)) mismatches++
          if (now - start < duration) requestAnimationFrame(frame)
          else resolve()
        }
        requestAnimationFrame(frame)
      })
      observer?.disconnect()
      return { elapsed_ms: performance.now() - start, intervals_ms: intervals, long_task_supported: supported, long_tasks: longTasks, clock_changes: clockChanges, panel_mismatch_frames: mismatches, hidden_frames: hiddenFrames, visibility: document.visibilityState }
    }, { duration: playbackWindowMs, names: panelNames })
    await page.getByRole('button', { name: 'Pause replay' }).click()
    await expect(page.locator('.source-footer')).toContainText('SYNCED')
    const pausedClocks = await clocks(page)
    const slider = page.getByRole('slider', { name: 'Session time' })
    const seeks = [raceStart]
    seeks.push(await measuredSeek(page, 'forward_10_seconds', Number(pausedClocks.seconds) + 10, () => page.getByRole('button', { name: 'Forward 10 seconds' }).click()))
    seeks.push(await measuredSeek(page, 'back_10_seconds', Number(pausedClocks.seconds), () => page.getByRole('button', { name: 'Back 10 seconds' }).click()))
    seeks.push(await measuredSeek(page, 'session_end', manifest.duration_seconds, async () => { await slider.focus(); await slider.press('End') }))
    const afterHeap = await heap()
    await Promise.all(completions)
    const observed = records.slice(requestStart).filter((record) => record.slug === activeSlug)
    sessions.push({ slug: activeSlug, label: sessionName, duration_seconds: manifest.duration_seconds, manifest_sha256: sha256(manifestText), source_provider: manifest.provider, geometry: { geometry_id: manifest.geometry.geometry_id ?? null, centerline_point_count: manifest.geometry.centerline_xy?.length ?? 0, provenance: manifest.geometry.provenance ?? null }, before_heap: beforeHeap, after_heap: afterHeap,
      playback: { ...playback, raf_interval_summary_ms: summary(playback.intervals_ms), raf_callbacks_per_second: playback.intervals_ms.length * 1000 / playback.elapsed_ms, paused_clocks: pausedClocks }, seeks,
      state_requests_including_seeks: { count: observed.length, successful: observed.filter((row) => row.status === 200).length, latency_summary_ms: summary(observed.filter((row) => row.status === 200).map((row) => row.elapsed_ms)), decoded_body_bytes: observed.reduce((sum, row) => sum + (row.decoded_body_bytes ?? 0), 0) } })
    expect(playback.hidden_frames, 'The sampled document must stay visible').toBe(0)
    expect(playback.panel_mismatch_frames, 'All observed panel timestamps use the canonical state').toBe(0)
    expect(pausedClocks.agree).toBe(true)
  }
  await Promise.all(completions)
  const sourcePaths = ['apps/web/src/App.tsx', 'apps/web/src/App.css', 'apps/web/src/components/TrackMap.tsx', 'apps/web/src/lib/circuit-geometry.ts', 'src/f1_racelab/api.py', 'src/f1_racelab/session/location_history.py', 'src/f1_racelab/session/geometry.py', 'src/f1_racelab/session/openf1_replay.py', 'apps/web/src/lib/playback-clock.ts', 'apps/web/package-lock.json', 'apps/web/benchmarks/replay-performance.spec.ts', 'apps/web/benchmarks/playwright.config.ts']
  const sourceHashes = Object.fromEntries(await Promise.all(sourcePaths.map(async (name) => [name, sha256(await readFile(path.join(repo, name)))])))
  const report = { schema_version: 1, started_utc: startedUtc, completed_utc: new Date().toISOString(), command: 'cd apps/web && npm run benchmark:replay', evidence: 'real cached historical replay data; local headless Chromium; development Vite server',
    interpretation: ['RAF callback cadence measures scheduling in a visible document, not painted GPU frame rate.', 'State-request duration includes local proxy/network, API computation and browser delivery; body bytes are decoded JSON, not on-wire transfer size.', 'Heap is Chromium JS heap without forced GC, not total process/GPU memory.', 'Seek latency includes Playwright input dispatch and synchronized DOM observation; it is not solely API latency.', 'One bounded run per session; no statistical performance regression or 60 FPS claim.'],
    environment: { git_head: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repo, encoding: 'utf8' }).trim(), git_status: execFileSync('git', ['status', '--short'], { cwd: repo, encoding: 'utf8' }).trim(), source_sha256: sourceHashes, node: process.version, platform: process.platform, arch: process.arch, os_release: os.release(), cpu_model: os.cpus()[0]?.model, logical_cpus: os.cpus().length, browser: browser.version(), playwright: JSON.parse(await readFile(path.join(repo, 'apps/web/node_modules/@playwright/test/package.json'), 'utf8')).version, viewport: testInfo.project.use.viewport, headless: true, playback_speed: 1, playback_window_ms: playbackWindowMs }, sessions, state_requests: records, page_errors: errors }
  const outputDir = path.join(repo, 'data/processed/browser_benchmarks')
  await mkdir(outputDir, { recursive: true })
  const output = path.join(outputDir, `replay-performance-${startedUtc.replaceAll(/[:.]/g, '-')}.json`)
  await writeFile(output, JSON.stringify(report, null, 2) + '\n')
  console.log(`Replay observations: ${output}`)
  expect(errors).toEqual([])
})
