import type { Preview } from '@storybook/react';
import 'happo/storybook/register';
import happoDecorator from 'happo/storybook/decorator';
import '../src/index.css';
import '../src/App.css';

export const decorators = [happoDecorator];

const preview: Preview = {
  parameters: {
    actions: { argTypesRegex: '^on[A-Z].*' },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/,
      },
    },
  },
};

export default preview;
