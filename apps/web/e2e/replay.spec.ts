import { expect, test, type Page } from '@playwright/test'

async function expectSynchronized(page: Page) {
  const clock = page.getByTestId('state-clock')
  await expect(clock).toBeVisible()
  const seconds = await clock.getAttribute('data-seconds')
  for (const name of [
    'Timing tower',
    'Circuit position map',
    'Driver focus',
    'Race control feed',
    'Weather observations',
    'Session summary',
    'Tyre stints',
    'Telemetry comparison',
  ]) {
    await expect(page.getByRole('region', { name })).toHaveAttribute(
      'data-session-time',
      seconds!,
    )
  }
  return Number(seconds)
}

async function chooseSession(page: Page, name: string) {
  await page.getByRole('combobox', { name: 'Historical session' }).click()
  await page.getByRole('option', { name, exact: true }).click()
  await expect(page.getByTestId('state-clock')).toHaveAttribute(
    'data-seconds',
    '0',
  )
}

test.beforeEach(async ({ page, request }) => {
  const response = await request.get('/api/v1/replays')
  const catalog = (await response.json()) as {
    slug: string
    available: boolean
  }[]
  expect(
    catalog.filter((row) => !row.available),
    'Build all three replay packs before running real-data browser tests',
  ).toEqual([])
  await page.goto('/')
  await expect(page.locator('.timing-row')).toHaveCount(20, {
    timeout: 15_000,
  })
  await expect(page.locator('.source-footer')).toContainText('SYNCED')
})

test('real Monza seeks keep map, timing, focus and control on the same state', async ({
  page,
}, testInfo) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.getByRole('button', { name: 'Jump to race start' }).click()
  await expect(page.getByTestId('state-clock')).toHaveAttribute('data-seconds', '214.805')
  const slider = page.getByRole('slider', { name: 'Session time' })
  const box = await page.locator('[data-slot="slider-track"]').boundingBox()
  expect(box).not.toBeNull()
  await page
    .locator('[data-slot="slider-track"]')
    .click({ position: { x: box!.width * 0.35, y: 2 } })
  await expect
    .poll(async () =>
      Number(
        await page.getByTestId('state-clock').getAttribute('data-seconds'),
      ),
    )
    .toBeGreaterThan(1000)
  await page
    .getByRole('region', { name: 'Timing tower' })
    .getByRole('button', { name: /NOR/ })
    .click()
  await expect(
    page.getByRole('region', { name: 'Driver focus' }),
  ).toContainText('Lando NORRIS')
  await expectSynchronized(page)
  await expect(page.locator('.map-car')).not.toHaveCount(0)
  await page.screenshot({
    path: testInfo.outputPath('monza-desktop.png'),
    fullPage: true,
  })
  await slider.focus()
  await slider.press('End')
  await expect(page.getByTestId('state-clock')).toHaveAttribute(
    'data-seconds',
    '5014.715',
  )
  await page.getByRole('button', { name: /CHEQUERED FLAG/ }).click()
  await expect(page.getByTestId('state-clock')).toHaveAttribute(
    'data-seconds',
    '4619',
  )
  await expectSynchronized(page)
  expect(errors).toEqual([])
  await expect(page.getByTestId('track-status')).toHaveAttribute(
    'data-status',
    'chequered',
  )
})

test('telemetry crosshair follows the canonical replay clock on its reference lap', async ({
  page,
}, testInfo) => {
  const panel = page.getByRole('region', { name: 'Telemetry comparison' })
  await expect(panel).toHaveAttribute('data-cursor-visible', 'false')
  await page.getByRole('button', { name: 'Jump to reference lap' }).click()
  await expect(page.getByTestId('state-clock')).toHaveAttribute(
    'data-seconds',
    /\d+\.\d{3}/,
  )
  await expect(panel).toHaveAttribute('data-cursor-visible', 'true')
  const distance = Number(await panel.getAttribute('data-cursor-distance'))
  expect(distance).toBeLessThan(1)
  await expectSynchronized(page)
  await page.screenshot({
    path: testInfo.outputPath('telemetry-cursor.png'),
    fullPage: true,
  })

  await page.getByRole('button', { name: 'Forward 10 seconds' }).click()
  await expect
    .poll(async () => Number(await panel.getAttribute('data-cursor-distance')))
    .toBeGreaterThan(100)
  await expectSynchronized(page)

  const slider = page.getByRole('slider', { name: 'Session time' })
  await slider.focus()
  await slider.press('End')
  await expect(panel).toHaveAttribute('data-cursor-visible', 'false')
  await expect(page.getByRole('button', { name: 'Jump to reference lap' })).toBeVisible()
  await expectSynchronized(page)
})

test('validated geometry and selected trail follow exact canonical seeks', async ({ page }, testInfo) => {
  const map = page.getByRole('region', { name: 'Circuit position map' })
  await expect(map).toHaveAttribute('data-geometry-id', /^openf1-driving-line:/)
  await expect(map.locator('.trace-origin')).toHaveCount(1)
  await page.getByRole('region', { name: 'Timing tower' }).getByRole('button', { name: /VER/ }).click()
  await page.getByRole('button', { name: 'Jump to reference lap' }).click()
  const seconds = await expectSynchronized(page)
  const trail = page.getByTestId('selected-trail')
  await expect(trail).toHaveAttribute('data-driver-id', '1')
  await expect(trail).toHaveAttribute('data-session-time', String(seconds))
  await expect(page.getByTestId('selected-heading')).toHaveCount(1)
  expect(Number(await trail.getAttribute('data-latest-sample-time'))).toBeLessThanOrEqual(seconds)
  const originalPaths = await trail.locator('path').evaluateAll((paths) => paths.map((path) => path.getAttribute('d')))
  expect(originalPaths.length).toBeGreaterThan(0)
  await page.getByRole('button', { name: 'Forward 10 seconds' }).click()
  await expect(page.getByTestId('state-clock')).toHaveAttribute('data-seconds', String(seconds + 10))
  await page.getByRole('button', { name: 'Back 10 seconds' }).click()
  await expect(trail).toHaveAttribute('data-session-time', String(seconds))
  expect(await trail.locator('path').evaluateAll((paths) => paths.map((path) => path.getAttribute('d')))).toEqual(originalPaths)
  await page.getByRole('region', { name: 'Timing tower' }).getByRole('button', { name: /NOR/ }).click()
  await expect(trail).toHaveAttribute('data-driver-id', '4')
  await expect(trail).toHaveAttribute('data-session-time', String(seconds))
  expect(await expectSynchronized(page)).toBe(seconds)
  await page.screenshot({ path: testInfo.outputPath('monza-geometry-trail.png'), fullPage: true })
})

test('Prediction Lab labels retrospective forecasts and separates validation from holdout', async ({
  page,
}, testInfo) => {
  await page.getByRole('button', { name: /Prediction Lab/ }).click()
  await expect(page.getByRole('heading', { name: 'Prediction Lab' })).toBeVisible()
  await expect(page.getByText('OFFLINE · HISTORICAL')).toBeVisible()
  await expect(page.getByRole('region', { name: 'Prediction cutoff contract' }))
    .toContainText('Before qualifying')
  await expect(page.getByRole('region', { name: 'Prediction cutoff contract' }))
    .toContainText('retrospective scoring')

  const rankings = page.getByRole('region', { name: 'Weekend prediction rankings' })
  await expect(rankings.getByRole('row')).toHaveCount(21)
  await expect(rankings.getByRole('columnheader', { name: 'ACTUAL ELIGIBLE RANK' })).toBeVisible()
  await expect(rankings.getByRole('columnheader', { name: 'Q CLASSIFICATION' })).toBeVisible()
  await expect(rankings).toContainText('UNTOUCHED HOLDOUT')
  await expect(page.getByText(/95% event bootstrap/)).toBeVisible()
  await expect(page.getByText(/SOURCE PUBLICATION TIME NOT RETAINED/)).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('prediction-lab-holdout.png'), fullPage: true })

  await page.getByRole('button', { name: 'After FP1' }).click()
  await expect(page.getByRole('region', { name: 'Prediction cutoff contract' })).toContainText('After FP1')
  await expect(rankings.getByRole('row')).toHaveCount(12)
  await page.getByRole('combobox', { name: 'Historical Grand Prix' }).selectOption('2025:11:test')
  const piastri = rankings.getByRole('row').filter({ hasText: 'PIA' })
  await expect(piastri.locator('td').nth(5)).toHaveText('1')
  await expect(piastri.locator('td').nth(6)).toHaveText('3')
  await page.getByRole('button', { name: 'Before qualifying' }).click()

  await page.getByRole('button', { name: /2024 · MODEL SELECTION/ }).click()
  await expect(rankings).toContainText('VALIDATION SET')
  await expect(page.getByRole('region', { name: 'validation model metrics' })).toContainText('SELECTED ON 2024')
  await expect(page.locator('.limits-grid > div').first()).toContainText('2024')
  await page.getByRole('button', { name: 'Race Control' }).click()
  await expect(page.getByRole('region', { name: 'Timing tower' })).toBeVisible()
})

test('play, speed change, pause and exact message seek use the central clock', async ({
  page,
}) => {
  await page.getByRole('combobox', { name: 'Playback speed' }).click()
  await page.getByRole('option', { name: '16×', exact: true }).click()
  await page.getByRole('button', { name: 'Play replay' }).click()
  await expect
    .poll(async () =>
      Number(
        await page.getByTestId('state-clock').getAttribute('data-seconds'),
      ),
    )
    .toBeGreaterThan(5)
  await page.getByRole('button', { name: 'Pause replay' }).click()
  await expect(page.locator('.source-footer')).toContainText('SYNCED')
  const stopped = await expectSynchronized(page)
  await page.waitForTimeout(450)
  expect(await expectSynchronized(page)).toBe(stopped)
  await page.getByRole('button', { name: 'Restart replay' }).click()
  await expect(page.getByTestId('state-clock')).toHaveAttribute(
    'data-seconds',
    '0',
  )
})

test('switching real sessions resets time and exposes missing Monaco pit data', async ({
  page,
}, testInfo) => {
  await chooseSession(page, '2023 Monaco Grand Prix')
  await expect(page.getByRole('heading', { name: 'Monaco 2023' })).toBeVisible()
  await expect(page.getByRole('status')).toContainText(
    'Pit-stop records are unavailable',
  )
  await expect(
    page.getByRole('region', { name: 'Driver focus' }),
  ).toContainText('Unavailable')
  const slider = page.getByRole('slider', { name: 'Session time' })
  await slider.focus()
  await slider.press('End')
  await expect
    .poll(async () =>
      Number(
        await page.getByTestId('state-clock').getAttribute('data-seconds'),
      ),
    )
    .toBeGreaterThan(6000)
  await expectSynchronized(page)
  await chooseSession(page, '2024 São Paulo Grand Prix')
  await expect(
    page.getByRole('heading', { name: 'São Paulo 2024' }),
  ).toBeVisible()
  await expect(page.getByRole('status')).toHaveCount(0)
  await slider.focus()
  await slider.press('End')
  await expect(
    page.getByRole('button', { name: /SAFETY CAR IN THIS LAP/ }),
  ).toBeVisible()
  await page.getByRole('button', { name: /SAFETY CAR IN THIS LAP/ }).click()
  await expect(page.getByTestId('state-clock')).toHaveAttribute(
    'data-seconds',
    '6484',
  )
  await expectSynchronized(page)
  await expect(page.getByTestId('track-status')).toHaveAttribute(
    'data-status',
    'safety_car_ending',
  )
  await page.screenshot({
    path: testInfo.outputPath('brazil-desktop.png'),
    fullPage: true,
  })
})

test('mobile keeps the session selector and replay controls usable', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await expect(
    page.getByRole('combobox', { name: 'Historical session' }),
  ).toBeVisible()
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true)
  await chooseSession(page, '2023 Monaco Grand Prix')
  await page.getByRole('button', { name: 'Forward 10 seconds' }).click()
  await expect(page.getByTestId('state-clock')).toHaveAttribute(
    'data-seconds',
    '10',
  )
  await expectSynchronized(page)
  await page.screenshot({
    path: testInfo.outputPath('monaco-mobile.png'),
    fullPage: true,
  })
})

test('Monaco rainfall reports seek to measured weather without retaining future readings', async ({
  page,
}, testInfo) => {
  await chooseSession(page, '2023 Monaco Grand Prix')
  const rain = page.getByRole('button', {
    name: 'Rain reported at 01:12:43',
    exact: true,
  })
  await rain.click()
  await expect(page.getByTestId('state-clock')).toHaveAttribute(
    'data-seconds',
    '4363.946',
  )
  await expect(page.getByTestId('rainfall')).toHaveText('Rain reported')
  await expect(
    page.getByRole('region', { name: 'Weather observations' }),
  ).toHaveAttribute('data-observed-time', '4363.946')
  await expectSynchronized(page)
  await page
    .getByRole('button', { name: 'No rain reported at 01:38:43', exact: true })
    .click()
  await expect(page.getByTestId('rainfall')).toHaveText('No rain reported')
  await rain.click()
  await expect(page.getByTestId('rainfall')).toHaveText('Rain reported')
  await expectSynchronized(page)
  await page.screenshot({
    path: testInfo.outputPath('monaco-rain-desktop.png'),
    fullPage: true,
  })
})

test('Brazil ending signals and restart keep their source meaning', async ({
  page,
}, testInfo) => {
  await chooseSession(page, '2024 São Paulo Grand Prix')
  const slider = page.getByRole('slider', { name: 'Session time' })
  for (const [message, seconds, status] of [
    ['VIRTUAL SAFETY CAR ENDING', '3590', 'vsc_ending'],
    ['RED FLAG', '4042', 'red'],
    ['SESSION STARTED', '5520.39', 'running_unknown'],
    ['SAFETY CAR IN THIS LAP', '6484', 'safety_car_ending'],
  ]) {
    await slider.focus()
    await slider.press('End')
    await expect(page.getByTestId('state-clock')).toHaveAttribute(
      'data-seconds',
      '8935.817',
    )
    await page
      .getByRole('region', { name: 'Race control feed' })
      .locator(`.control-row[data-session-time="${seconds}"]`)
      .filter({ hasText: message })
      .click()
    await expect(page.getByTestId('state-clock')).toHaveAttribute(
      'data-seconds',
      seconds,
    )
    await expect(page.getByTestId('track-status')).toHaveAttribute(
      'data-status',
      status,
    )
    await expectSynchronized(page)
  }
  await page.screenshot({
    path: testInfo.outputPath('brazil-context-desktop.png'),
    fullPage: true,
  })
})

test('Monaco stint history follows event time and keeps same-lap source rows visible', async ({
  page,
}, testInfo) => {
  await chooseSession(page, '2023 Monaco Grand Prix')
  const panel = page.getByRole('region', { name: 'Tyre stints' })
  await page
    .getByRole('region', { name: 'Timing tower' })
    .getByRole('button', { name: /HUL/ })
    .click()
  await expect(panel.locator('li[data-stint-number]')).toHaveCount(0)
  await page.getByRole('button', { name: 'Jump to race start' }).click()
  await expect(panel.locator('li[data-stint-number]')).toHaveCount(2)
  await expect(panel).toContainText('Mapped stint boundaries share a lap')
  await expect(panel).toContainText('ESTIMATED START')
  await expectSynchronized(page)
  const slider = page.getByRole('slider', { name: 'Session time' })
  await slider.focus()
  await slider.press('End')
  await expect(page.getByTestId('state-clock')).toHaveAttribute(
    'data-seconds',
    '7030.073',
  )
  await expect(panel.locator('li[data-stint-number]')).toHaveCount(4)
  await expect(panel).toContainText('WET')
  await expectSynchronized(page)
  await page.screenshot({
    path: testInfo.outputPath('monaco-stints-desktop.png'),
    fullPage: true,
  })
})

test('map cars interpolate on playback and reduce motion remains immediate', async ({
  page,
}) => {
  await page.getByRole('button', { name: 'Jump to race start' }).click()
  const car = page.locator('.map-car').first()
  await expect(car).toBeVisible()
  await page.getByRole('button', { name: 'Play replay' }).click()
  await expect
    .poll(async () =>
      Number(await page.getByTestId('state-clock').getAttribute('data-seconds')),
    )
    .toBeGreaterThan(214.805)
  await expect
    .poll(async () => car.evaluate((element) => getComputedStyle(element).transitionDuration))
    .toBe('0.18s')
  await page.getByRole('button', { name: 'Pause replay' }).click()
  await page
    .getByRole('region', { name: 'Race control feed' })
    .getByRole('button', { name: /SESSION STARTED/ })
    .click()
  await expect(page.getByTestId('state-clock')).toHaveAttribute(
    'data-seconds',
    '214.805',
  )
  await expect(car).toBeVisible()
  await expect(car).toHaveAttribute('style', /transition: none/)
  const slider = page.getByRole('slider', { name: 'Session time' })
  await slider.focus()
  await slider.press('ArrowRight')
  await expect
    .poll(async () =>
      Number(await page.getByTestId('state-clock').getAttribute('data-seconds')),
    )
    .toBeGreaterThan(214.805)
  await expect(car).toHaveAttribute('style', /transition: none/)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await expect
    .poll(async () => car.evaluate((element) => getComputedStyle(element).transitionDuration))
    .toBe('0s')
})

for (const session of [
  { slug: 'monza-2025', name: '2025 Italian Grand Prix', title: '#1 L50 vs #4 L50' },
  { slug: 'monaco-2023', name: '2023 Monaco Grand Prix', title: '#1 L40 vs #31 L40' },
  { slug: 'brazil-2024', name: '2024 São Paulo Grand Prix', title: '#1 L52 vs #31 L52' },
]) {
  test(`${session.slug} six telemetry channels retain one clock and exact seek readouts`, async ({ page, request }, testInfo) => {
    if (session.slug !== 'monza-2025') await chooseSession(page, session.name)
    const panel = page.getByRole('region', { name: 'Telemetry comparison' })
    await expect(panel.getByRole('heading', { name: session.title, exact: true })).toBeVisible()
    const response = await request.get(`/api/v1/replay/${session.slug}/telemetry/lap-comparison`)
    expect(response.status()).toBe(200)
    const comparison = await response.json()
    await panel.getByRole('button', { name: 'Jump to reference lap' }).click()
    const start = await expectSynchronized(page)
    await page.getByRole('button', { name: 'Forward 10 seconds' }).click()
    await expect(page.getByTestId('state-clock')).toHaveAttribute('data-seconds', String(start + 10))
    await expect(panel).toHaveAttribute('data-cursor-visible', 'true')
    const readouts = panel.getByRole('table', { name: 'Canonical telemetry cursor readings' })
    const before = await readouts.innerText()
    const distance = await panel.getAttribute('data-cursor-distance')
    const leftIndex = comparison.samples.findLastIndex((point: { elapsed_a_seconds: number }) => point.elapsed_a_seconds <= 10)
    const left = comparison.samples[leftIndex]
    const right = comparison.samples[leftIndex + 1]
    const fraction = (10 - left.elapsed_a_seconds) / (right.elapsed_a_seconds - left.elapsed_a_seconds)
    const expectedDistance = left.distance_m + fraction * (right.distance_m - left.distance_m)
    expect(Number(distance)).toBeCloseTo(expectedDistance, 2)
    // Discrete channels use the preceding grid value, never fractional source states.
    for (const [id, field] of [['gear', 'gear_a'], ['drs', 'drs_a_code'], ['brake', 'brake_a_source_value']]) {
      await expect(readouts.locator(`tr[data-channel="${id}"] td`).first()).toHaveText(String(left[field]))
    }
    for (const label of ['Speed', 'Throttle', 'Brake', 'RPM', 'Gear', 'DRS']) {
      await panel.getByRole('tab', { name: label, exact: true }).click()
      await expect(panel).toHaveAttribute('data-channel', label.toLowerCase())
      await expect(panel.getByTestId('telemetry-trace-a')).toHaveAttribute('d', /^M/)
      await expect(panel.getByTestId('telemetry-trace-b')).toHaveAttribute('d', /^M/)
      expect(await expectSynchronized(page)).toBe(start + 10)
      expect(await readouts.innerText()).toBe(before)
    }
    await page.getByRole('button', { name: 'Back 10 seconds' }).click()
    await expect(page.getByTestId('state-clock')).toHaveAttribute('data-seconds', String(start))
    await page.getByRole('button', { name: 'Forward 10 seconds' }).click()
    await expect(panel).toHaveAttribute('data-cursor-distance', distance!)
    expect(await readouts.innerText()).toBe(before)
    await panel.screenshot({ path: testInfo.outputPath(`${session.slug}-telemetry-channels.png`) })
    if (session.slug === 'monaco-2023') {
      await page.setViewportSize({ width: 390, height: 844 })
      await expect(panel.getByRole('tab', { name: 'DRS', exact: true })).toBeVisible()
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      await panel.screenshot({ path: testInfo.outputPath('monaco-telemetry-mobile.png') })
    }
  })
}

test('telemetry selection UI shows available drivers and applies a different lap pair', async ({
  page, request,
}, testInfo) => {
  const panel = page.getByRole('region', { name: 'Telemetry comparison' })
  const selector = page.getByRole('group', { name: 'Choose telemetry laps' })
  await expect(selector).toBeVisible()
  // Default pair for Monza is #1 L50 vs #4 L50.
  await expect(panel.getByRole('heading', { name: '#1 L50 vs #4 L50', exact: true })).toBeVisible()
  // Library catalog API: only drivers with cached car_data are available.
  const catalogResponse = await request.get('/api/v1/replay/monza-2025/telemetry/laps')
  expect(catalogResponse.status()).toBe(200)
  const library = await catalogResponse.json()
  expect(library.session_slug).toBe('monza-2025')
  expect(library.drivers.filter((d: { available: boolean }) => d.available).length).toBeGreaterThanOrEqual(2)
  // Change side-A lap using the lap dropdown (second combobox in side-A pair, overall index 1).
  // Structure: [driverA, lapA, driverB, lapB] — four comboboxes in order.
  const combos = selector.getByRole('combobox')
  await combos.nth(1).click()
  await page.getByRole('option').filter({ hasText: /L10/ }).first().click()
  await selector.getByRole('button', { name: 'Compare laps' }).click()
  // Panel attributes and heading update to reflect the new selected pair.
  await expect(panel).toHaveAttribute('data-reference-driver', '1')
  await expect(panel).toHaveAttribute('data-reference-lap', '10')
  await expect(panel).toHaveAttribute('data-comparison-driver', '4')
  await expect(panel).toHaveAttribute('data-comparison-lap', '50')
  await expect(panel.getByRole('heading', { name: '#1 L10 vs #4 L50', exact: true })).toBeVisible()
  // Replay time is unchanged; the cursor jumps to the new reference lap start.
  await panel.getByRole('button', { name: 'Jump to reference lap' }).click()
  await expect(panel).toHaveAttribute('data-cursor-visible', 'true')
  await page.screenshot({ path: testInfo.outputPath('telemetry-selection.png'), fullPage: true })
})

test('race history chart seeks the shared clock and toggles to gap view', async ({ page }) => {
  await page.goto('/')
  const chart = page.getByTestId('position-chart')
  await expect(chart).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Position by session time' })).toBeVisible()
  const box = (await chart.boundingBox())!
  // 50% across the plotted width: padding is 38/1000 left and 46/1000 right.
  await chart.click({ position: { x: box.width * (0.038 + 0.916 * 0.5), y: box.height / 2 } })
  const clock = page.getByTestId('state-clock')
  await expect
    .poll(async () => Number(await clock.getAttribute('data-seconds')))
    .toBeGreaterThan(2000)
  const seconds = Number(await clock.getAttribute('data-seconds'))
  expect(seconds).toBeLessThan(3000) // about half of the 5,014 s Monza pack
  await expectSynchronized(page)
  await page.getByRole('button', { name: 'GAP', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Gap to leader' })).toBeVisible()
})

test('race pace lab shows out-of-fold forecasts, evidence and lap contributions', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /Race Pace/ }).click()
  await expect(page.getByRole('heading', { name: /Race Pace/ })).toBeVisible()
  await expect(page.getByText('ML PREDICTION · NOT LIVE')).toBeVisible()
  await expect(page.getByLabel('Benchmark evidence')).toContainText('LightGBM MAE')
  await expect(page.getByTestId('pace-chart')).toBeVisible()
  const detail = page.getByLabel('Selected lap forecast')
  await expect(detail).toContainText('retrospective')
  await expect(detail.getByLabel('Feature contributions')).toBeVisible()
  const before = await detail.locator('h2').innerText()
  await page.getByLabel('Race').selectOption({ index: 5 })
  await expect(page.getByTestId('pace-chart')).toBeVisible()
  await expect.poll(async () => detail.locator('h2').innerText()).not.toBe(before)
})
