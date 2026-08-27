import { test } from '@playwright/test';
import {
  expect,
  gotoApp,
  KIOSK_VIEWPORTS,
  liveMetricValueFontSizes,
  overflowingLiveMetricValues,
  simulateShot,
  WIDEST_LIVE_METRIC_VALUE,
  withControlSocket,
} from './helpers';

/** Dismiss the club picker that opens on every load, keeping the default club. */
async function dismissPicker(page: import('@playwright/test').Page) {
  await page.getByRole('button', { name: 'Close Select club' }).click();
}

for (const viewport of KIOSK_VIEWPORTS) {
  test.describe(`live metrics at ${viewport.width}×${viewport.height}`, () => {
    test.use({ hasTouch: true, viewport });

    test('keeps metric value text inside each live tile', async ({ page }) => {
      await withControlSocket(async (socket) => {
        await simulateShot(socket);
      });

      await gotoApp(page);
      await dismissPicker(page);

      await expect(page.locator('.live-panel__grid .metric-card')).toHaveCount(10);

      const sizes = await liveMetricValueFontSizes(page);
      expect(sizes.length).toBe(10);
      expect(new Set(sizes.map((size) => size.toFixed(2))).size).toBe(1);

      await page.locator('.live-panel__grid .metric-card__value').evaluateAll((values, widest) => {
        for (const value of values) {
          value.textContent = widest;
        }
      }, WIDEST_LIVE_METRIC_VALUE);
      await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => resolve())));

      expect(await overflowingLiveMetricValues(page)).toEqual([]);
    });
  });
}
