import { test } from '@playwright/test';
import { expect, gotoApp, resetSession, setClub, simulateShot, withControlSocket } from './helpers';

/** Dismiss the club picker that opens on every load, keeping the default club. */
async function dismissPicker(page: import('@playwright/test').Page) {
  await page.getByRole('button', { name: 'Close Select club' }).click();
}

/** Open the footer menu sheet (units / theme / system / shut down). */
async function openMenu(page: import('@playwright/test').Page) {
  await page.getByRole('button', { name: 'Open menu' }).click();
}

test.beforeEach(async () => {
  await withControlSocket(async (socket) => {
    await resetSession(socket);
    await setClub(socket, 'driver');
  });
});

test('stays usable when websocket upgrade fails and socket.io falls back to polling', async ({ page }) => {
  await gotoApp(page);

  // The club picker is the first thing shown, and it only renders once mounted.
  await expect(page.getByRole('dialog', { name: 'Select club' })).toBeVisible();

  await dismissPicker(page);
  await expect(page.getByLabel('Server connected')).toBeVisible();

  await page.getByLabel('Server connected').click();
  const statusMenu = page.getByRole('dialog', { name: 'System status' });
  await expect(statusMenu).toBeVisible();
  await expect(statusMenu.getByText('Server', { exact: true })).toBeVisible();
  await expect(statusMenu.getByText('Radar', { exact: true })).toBeVisible();
  await expect(statusMenu.getByText('Ball detection', { exact: true })).toBeVisible();
  await expect(statusMenu.getByText('Connected', { exact: true }).first()).toBeVisible();

  await page.getByLabel('Close status').click();
  await expect(statusMenu).toBeHidden();

  await page.getByRole('button', { name: 'Shots' }).click();
  await page.getByLabel('Server connected').click();
  await expect(page.getByRole('dialog', { name: 'System status' })).toBeVisible();
});

test('supports club selection choose and dismiss flows against mock backend', async ({ page }) => {
  await gotoApp(page);

  await page.getByRole('button', { name: 'Irons' }).click();
  await page.getByRole('button', { name: '7i', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Select club' })).toBeHidden();
  await expect(page.locator('.panel-header').getByRole('button', { name: 'Change club' })).toBeVisible();
  await expect(page.locator('.panel-header__club', { hasText: '7 Iron' })).toBeVisible();

  await withControlSocket(async (socket) => {
    await simulateShot(socket);
  });

  await page.getByRole('button', { name: 'Shots' }).click();
  await expect(page.locator('.shots-panel__row')).toHaveCount(1);
  await expect(page.getByText('7-iron')).toBeVisible();

  await page.reload();
  await expect(page.getByRole('dialog', { name: 'Select club' })).toBeVisible();
  await dismissPicker(page);
  // Dismissing keeps whatever the server last reported, not a reset to driver.
  await expect(page.locator('.panel-header').getByRole('button', { name: 'Change club' })).toBeVisible();
  await expect(page.locator('.panel-header__club', { hasText: '7 Iron' })).toBeVisible();
});

test('renders live shot data and mock-mode simulate flow', async ({ page }) => {
  await gotoApp(page);
  await dismissPicker(page);

  await expect(page.getByRole('button', { name: 'Simulate shot' })).toBeVisible();
  await expect(page.getByText('Ready', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Simulate shot' }).click();

  await expect(page.getByText('Ready', { exact: true })).toBeHidden();
  await expect(page.locator('.live-panel__grid .metric-card')).toHaveCount(10);
  await expect(page.locator('.live-panel__spotlight')).toHaveCount(0);
});

test('keeps shutdown visible and asks for confirmation', async ({ page }) => {
  await gotoApp(page);
  await dismissPicker(page);

  await page.getByRole('button', { name: 'Shut down' }).click();

  await expect(page.getByRole('dialog', { name: 'Shut down OpenFlight?' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Shut Down', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible();
});

test('does not keep the previous metric title yellow after selecting a new hero', async ({ page }) => {
  await withControlSocket(async (socket) => {
    await simulateShot(socket);
  });

  await gotoApp(page);
  await dismissPicker(page);

  await page.locator('.metric-card--interactive').filter({ hasText: 'Club speed' }).click();

  await expect(page.locator('.metric-card--selected')).toContainText('Club speed');
  await expect(page.locator('.metric-card--selected .metric-card__label')).toHaveCSS('color', 'rgb(255, 212, 0)');
  await expect(
    page.locator('.metric-card--interactive').filter({ hasText: 'Ball speed' }).locator('.metric-card__label')
  ).not.toHaveCSS('color', 'rgb(255, 212, 0)');
});

test('pins a tapped metric top-left and remembers it', async ({ page }) => {
  await withControlSocket(async (socket) => {
    await simulateShot(socket);
  });

  await gotoApp(page);
  await dismissPicker(page);

  await expect(page.locator('.metric-card--selected')).toContainText('Ball speed');
  await expect(page.locator('.live-panel__spotlight')).toHaveCount(0);

  await page.locator('.metric-card--interactive').filter({ hasText: 'Club speed' }).click();

  await expect(page.locator('.metric-card--selected')).toContainText('Club speed');
  await expect(page.locator('.live-panel__grid .metric-card').first()).toContainText('Club speed');
  await expect(page.locator('.live-panel__grid .metric-card')).toHaveCount(10);
  await expect(page.locator('.live-panel__grid')).toContainText('Ball speed');

  await page.reload();
  await dismissPicker(page);
  await expect(page.locator('.metric-card--selected')).toContainText('Club speed');
  await expect(page.locator('.live-panel__grid .metric-card').first()).toContainText('Club speed');
});

test('switches between primary navigation views', async ({ page }) => {
  await withControlSocket(async (socket) => {
    await simulateShot(socket);
    await setClub(socket, '7-iron');
    await simulateShot(socket);
  });

  await gotoApp(page);
  await dismissPicker(page);

  await expect(page.locator('.panel-footer__units')).toHaveText('mph / yds');
  await expect(page.locator('.panel-footer__count')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Shots' })).toContainText('2');

  await page.getByRole('button', { name: 'Players' }).click();
  await expect(page.getByRole('region', { name: 'Players' })).toBeVisible();
  await expect(page.locator('.panel-header').getByRole('button', { name: 'Add player' })).toBeVisible();
  await expect(page.locator('.panel-footer__units')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Simulate shot' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Change club' })).toHaveCount(0);

  await page.getByRole('button', { name: 'Stats' }).click();
  await expect(page.getByText('Avg ball')).toBeVisible();
  await expect(page.locator('.panel-header').getByRole('button', { name: 'Clear session' })).toBeVisible();
  await expect(page.locator('.panel-footer__units')).toHaveText('mph / yds');
  await expect(page.locator('.panel-footer__count')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Simulate shot' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Change club' })).toHaveCount(0);

  await page.getByRole('button', { name: 'Shots' }).click();
  await expect(page.locator('.shots-panel__row')).toHaveCount(2);
  await expect(page.getByText('7-iron')).toBeVisible();
  await expect(page.locator('.panel-footer__units')).toHaveText('mph / yds');
  await expect(page.locator('.panel-footer__count')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Simulate shot' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Change club' })).toHaveCount(0);

  await page.getByRole('button', { name: 'Camera' }).click();
  await expect(page.getByText('Camera unavailable')).toBeVisible();
  await expect(page.locator('.panel-footer__units')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Simulate shot' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Change club' })).toHaveCount(0);

  await page.getByRole('button', { name: 'Debug' }).click();
  await expect(page.getByRole('heading', { name: 'System Status' })).toBeVisible();
  await expect(page.getByText('mock')).toBeVisible();
  await expect(page.locator('.panel-header').getByRole('button', { name: 'Record' })).toBeVisible();
  await expect(page.locator('.panel-footer__units')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Simulate shot' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Change club' })).toHaveCount(0);

  await page.getByRole('button', { name: 'Live' }).click();
  await expect(page.getByRole('button', { name: 'Simulate shot' })).toBeVisible();
  await expect(page.locator('.panel-header').getByRole('button', { name: 'Change club' })).toBeVisible();
  await expect(page.locator('.panel-footer').getByRole('button', { name: 'Change club' })).toHaveCount(0);
  await expect(page.locator('.panel-footer__units')).toHaveText('mph / yds');
  await expect(page.locator('.panel-footer__count')).toHaveCount(0);
});

test('selecting a player opens Live and does not offer delete on the active player', async ({ page }) => {
  await gotoApp(page);
  await dismissPicker(page);

  await page.getByRole('button', { name: 'Players' }).click();
  await page.getByRole('button', { name: 'Add player' }).click();
  await page.getByPlaceholder('Name').fill('Alex');
  await page.getByRole('dialog', { name: 'Add player' }).getByRole('button', { name: 'Add player' }).click();

  await expect(page.getByLabel('Remove Player 1')).toBeVisible();
  await expect(page.getByLabel('Remove Alex')).toHaveCount(0);

  await page.locator('.players-panel__card').filter({ hasText: 'Player 1' }).click();
  await expect(page.locator('.panel-header__title')).toHaveText('Live');
  await expect(page.locator('.panel-header__subtitle')).toHaveText('Player 1');
});

test('confirms before clearing and only removes that player, then returns to Live', async ({ page }) => {
  await withControlSocket(async (socket) => {
    await simulateShot(socket);
  });

  await gotoApp(page);
  await dismissPicker(page);

  await page.getByRole('button', { name: 'Players' }).click();
  await page.getByRole('button', { name: 'Add player' }).click();
  await page.getByPlaceholder('Name').fill('Alex');
  await page.getByRole('dialog', { name: 'Add player' }).getByRole('button', { name: 'Add player' }).click();
  await expect(page.getByLabel('Remove Alex')).toHaveCount(0);

  await withControlSocket(async (socket) => {
    await simulateShot(socket);
  });

  await page.getByRole('button', { name: 'Stats' }).click();
  await page.locator('.panel-header').getByRole('button', { name: 'Clear session' }).click();

  const dialog = page.getByRole('dialog', { name: "Clear Alex's session?" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("This removes Alex's shots. Other players are kept.");

  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.locator('.panel-header__title')).toHaveText('Stats');

  await page.locator('.panel-header').getByRole('button', { name: 'Clear session' }).click();
  await page.getByRole('dialog', { name: "Clear Alex's session?" }).getByRole('button', { name: 'Clear session' }).click();

  await expect(page.locator('.panel-header__title')).toHaveText('Live');
  await expect(page.locator('.panel-header__subtitle')).toHaveText('Alex');
  await expect(page.getByText('Ready', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Players' }).click();
  await page.locator('.players-panel__card').filter({ hasText: 'Player 1' }).click();
  await page.getByRole('button', { name: 'Shots' }).click();
  await expect(page.locator('.shots-panel__row')).toHaveCount(1);
});

test('scrolls the shots list by dragging on a row', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 600 });

  await withControlSocket(async (socket) => {
    for (let i = 0; i < 16; i += 1) {
      await simulateShot(socket);
    }
  });

  await gotoApp(page);
  await dismissPicker(page);
  await page.getByRole('button', { name: 'Shots' }).click();

  const list = page.getByRole('region', { name: 'Recorded shots' });
  await expect(list.locator('.shots-panel__row')).toHaveCount(16);

  const before = await list.evaluate((node) => node.scrollTop);
  const box = await list.boundingBox();
  expect(box).toBeTruthy();

  await page.mouse.move(box!.x + box!.width / 2, box!.y + 180);
  await page.mouse.down();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + 40, { steps: 12 });
  await page.mouse.up();

  await expect.poll(async () => list.evaluate((node) => node.scrollTop)).toBeGreaterThan(before);
  await expect(page.locator('.shots-panel__validation')).toHaveCount(0);
});

test('scrolls stats club chips by dragging without changing the filter', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 600 });

  const clubs = ['driver', '3-wood', '5-wood', '4-iron', '5-iron', '6-iron', '7-iron', '8-iron', '9-iron', 'pw', 'sw'];
  await withControlSocket(async (socket) => {
    for (const club of clubs) {
      await setClub(socket, club);
      await simulateShot(socket);
    }
  });

  await gotoApp(page);
  await dismissPicker(page);
  await page.getByRole('button', { name: 'Stats' }).click();

  const chips = page.getByRole('group', { name: 'Filter by club' });
  const scroller = chips.locator('.stats-panel__chip-scroll');
  const activeBefore = await chips.locator('.panel-chip--active').innerText();
  const before = await scroller.evaluate((node) => node.scrollLeft);
  const box = await scroller.boundingBox();
  expect(box).toBeTruthy();

  await page.mouse.move(box!.x + box!.width - 40, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(box!.x + 40, box!.y + box!.height / 2, { steps: 12 });
  await page.mouse.up();

  await expect.poll(async () => scroller.evaluate((node) => node.scrollLeft)).toBeGreaterThan(before);
  await expect(chips.locator('.panel-chip--active')).toHaveText(activeBefore);
  await expect(chips.getByRole('button', { name: /All \(/ })).toBeVisible();
});

test('expands a shot row to reveal its validation fields', async ({ page }) => {
  await withControlSocket(async (socket) => {
    await simulateShot(socket);
  });

  await gotoApp(page);
  await dismissPicker(page);
  await page.getByRole('button', { name: 'Shots' }).click();

  // 7b's row has no room for the fields inline, so they live behind a tap.
  await expect(page.locator('.shots-panel__validation')).toHaveCount(0);

  await page.locator('.shots-panel__row-main').first().click();

  await expect(page.locator('.shots-panel__validation')).toBeVisible();
  await expect(page.getByPlaceholder('mph')).toBeVisible();
  await expect(page.getByPlaceholder('notes…')).toBeVisible();
});

test.describe('shots list on a touchscreen', () => {
  test.use({ hasTouch: true, viewport: { width: 1024, height: 600 } });

  test('taps a row to open details', async ({ page }) => {
    await withControlSocket(async (socket) => {
      await simulateShot(socket);
    });

    await gotoApp(page);
    await dismissPicker(page);
    await page.getByRole('button', { name: 'Shots' }).click();

    await expect(page.locator('.shots-panel__validation')).toHaveCount(0);
    await page.locator('.shots-panel__row-main').first().tap();
    await expect(page.locator('.shots-panel__validation')).toBeVisible();
  });
});

test.describe('stats club chips on a touchscreen', () => {
  test.use({ hasTouch: true, viewport: { width: 1024, height: 600 } });

  test('taps a club chip to filter', async ({ page }) => {
    await withControlSocket(async (socket) => {
      await setClub(socket, 'driver');
      await simulateShot(socket);
      await setClub(socket, '7-iron');
      await simulateShot(socket);
    });

    await gotoApp(page);
    await dismissPicker(page);
    await page.getByRole('button', { name: 'Stats' }).click();

    await expect(page.getByRole('button', { name: '7-IRON (1)' })).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { name: 'DRIVER (1)' }).tap();
    await expect(page.getByRole('button', { name: 'DRIVER (1)' })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('button', { name: '7-IRON (1)' })).toHaveAttribute('aria-pressed', 'false');
    await expect(page.locator('.stats-panel__grid .metric-card').first()).toContainText('1');
  });
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

test('unit toggle in the menu sheet updates displayed units', async ({ page }) => {
  await withControlSocket(async (socket) => {
    await simulateShot(socket);
  });

  await gotoApp(page);
  await dismissPicker(page);

  await expect(page.locator('.metric-card--selected .metric-card__unit')).toHaveText('mph');
  await expect(page.locator('.metric-card').filter({ hasText: 'Carry' }).locator('.metric-card__unit')).toHaveText(
    'yds'
  );

  const imperialSpeed = await page.locator('.metric-card--selected .metric-card__value').textContent();

  await openMenu(page);
  await page.getByRole('button', { name: 'KMH / M' }).click();
  await page.getByRole('button', { name: 'Close menu' }).click();

  await expect(page.locator('.metric-card--selected .metric-card__unit')).toHaveText('km/h');
  await expect(page.locator('.metric-card').filter({ hasText: 'Carry' }).locator('.metric-card__unit')).toHaveText('m');
  await expect(page.locator('.metric-card--selected .metric-card__value')).not.toHaveText(imperialSpeed ?? '');
});
