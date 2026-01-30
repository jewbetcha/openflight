import { defineConfig } from 'happo';

export default defineConfig({
  targets: {
    "chrome-kiosk": {
      viewport: '1024x600',
      type: 'chrome',
    },
  },
  integration: {
    type: 'storybook',
  },
});
