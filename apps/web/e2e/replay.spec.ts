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
