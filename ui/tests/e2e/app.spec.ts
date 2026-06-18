import { test } from '@playwright/test';
import { expect, gotoApp, setClub, simulateShot, withControlSocket } from './helpers';

test.beforeEach(async () => {
  await withControlSocket(async (socket) => {
    socket.emit('clear_session');
    await new Promise<void>((resolve) => {
      socket.once('session_cleared', () => resolve());
    });
    await setClub(socket, 'driver');
  });
});

test('stays usable when websocket upgrade fails and socket.io falls back to polling', async ({ page }) => {
  await gotoApp(page);

  await expect(page.locator('.connection-status--connected')).toBeVisible();
  await expect(page.locator('.connection-status__text')).toHaveText('Connected');
  await expect(page.getByText('Select your club')).toBeVisible();
});

test('supports club selection choose and dismiss flows against mock backend', async ({ page }) => {
  await gotoApp(page);

  await page.getByRole('button', { name: '7i' }).click();
  await expect(page.getByText('Select your club')).toBeHidden();
  await expect(page.getByRole('button', { name: /Club 7i/i })).toBeVisible();

  await withControlSocket(async (socket) => {
    await simulateShot(socket);
  });

  await page.getByRole('button', { name: 'Shots' }).click();
  await expect(page.locator('.shot-row')).toHaveCount(1);
  await expect(page.getByText('7-iron')).toBeVisible();

  await page.reload();
  await expect(page.getByText('Select your club')).toBeVisible();
  await page.getByRole('button', { name: 'Close club selection' }).click();
  await expect(page.getByRole('button', { name: /Club DR/i })).toBeVisible();
});

test('renders live shot data and mock-mode simulate flow', async ({ page }) => {
  await gotoApp(page);
  await page.getByRole('button', { name: 'Close club selection' }).click();

  await expect(page.getByRole('button', { name: 'Simulate Shot' })).toBeVisible();
  await page.getByRole('button', { name: 'Simulate Shot' }).click();

  await expect(page.getByText('Ready for your shot')).toBeHidden();
  await expect(page.locator('.speed-gauge__value')).not.toHaveText('--');
  await expect(page.locator('.metric-card').filter({ hasText: 'Carry' }).locator('.metric-card__value')).not.toHaveText('--');
});

test('switches between primary navigation views', async ({ page }) => {
  await withControlSocket(async (socket) => {
    await simulateShot(socket);
    await setClub(socket, '7-iron');
    await simulateShot(socket);
  });

  await gotoApp(page);
  await page.getByRole('button', { name: 'Close club selection' }).click();

  await page.getByRole('button', { name: 'Stats' }).click();
  await expect(page.getByText('Avg Ball (mph)')).toBeVisible();

  await page.getByRole('button', { name: 'Shots' }).click();
  await expect(page.locator('.shot-row')).toHaveCount(2);
  await expect(page.getByText('7-iron')).toBeVisible();

  await page.getByRole('button', { name: 'Camera' }).click();
  await expect(page.getByRole('heading', { name: 'Camera Not Available' })).toBeVisible();

  await page.getByRole('button', { name: 'Debug' }).click();
  await expect(page.getByRole('heading', { name: 'System Status' })).toBeVisible();
  await expect(page.getByText('mock')).toBeVisible();

  await page.getByRole('button', { name: 'Live' }).click();
  await expect(page.getByRole('button', { name: 'Simulate Shot' })).toBeVisible();
});

test('display route shows latest shot and recent shots from mock backend session', async ({ page }) => {
  await withControlSocket(async (socket) => {
    await setClub(socket, 'driver');
    await simulateShot(socket);
    await setClub(socket, '7-iron');
    await simulateShot(socket);
    await setClub(socket, 'pw');
    await simulateShot(socket);
  });

  await gotoApp(page, '/display');

  await expect(page.getByText('OpenFlight Display')).toBeVisible();
  await expect(page.getByText('Socket connected')).toBeVisible();
  await expect(page.getByLabel('Recent shots').locator('.display-shot-chip')).toHaveCount(3);
  await expect(page.getByLabel('Recent shots')).toContainText('pw');
  await expect(page.getByLabel('Recent shots')).toContainText('7-iron');
});

test('unit toggle updates displayed units', async ({ page }) => {
  await withControlSocket(async (socket) => {
    await simulateShot(socket);
  });

  await gotoApp(page);
  await page.getByRole('button', { name: 'Close club selection' }).click();

  await expect(page.locator('.speed-gauge__unit')).toHaveText('mph');
  await expect(page.locator('.metric-card').filter({ hasText: 'Carry' }).locator('.metric-card__unit')).toHaveText('yds');

  const imperialSpeed = await page.locator('.speed-gauge__value').textContent();

  await page.getByRole('button', { name: 'KMH/M' }).click();

  await expect(page.locator('.speed-gauge__unit')).toHaveText('km/h');
  await expect(page.locator('.metric-card').filter({ hasText: 'Carry' }).locator('.metric-card__unit')).toHaveText('m');
  await expect(page.locator('.speed-gauge__value')).not.toHaveText(imperialSpeed ?? '');
});
