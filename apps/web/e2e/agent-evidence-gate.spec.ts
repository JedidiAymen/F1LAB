import { expect, test } from '@playwright/test'

test('gate replay exposes withheld clean cases and observational signals', async ({ page }, testInfo) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Research & reliability' }).click()
  const gate = page.getByRole('region', { name: 'Observational agent evidence gate' })
  await expect(gate).toContainText('withholding every clean proposal')
  await expect(gate).toContainText('not a demonstrated gain in root-cause accuracy')
  await gate.getByLabel('Evidence gate scenario').selectOption('feature_skew-s1')
  await expect(gate.getByLabel('Evidence gate decision')).toContainText('Known feature values differ')
  await gate.getByLabel('Evidence gate scenario').selectOption('regime_shift-s1')
  await expect(gate.getByLabel('Evidence gate decision')).toContainText('insufficient')
  await gate.getByLabel('Evidence gate scenario').selectOption('no_material_discrepancy-s1')
  await expect(gate.getByLabel('Evidence gate decision')).toContainText('abstain')
  await gate.screenshot({ path: testInfo.outputPath('agent-gate-desktop.png') })
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await gate.screenshot({ path: testInfo.outputPath('agent-gate-mobile.png') })
})
