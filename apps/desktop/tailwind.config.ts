import type { Config } from 'tailwindcss';
import preset from '@arac-hasar/ui/tailwind-preset';

const config: Config = {
  presets: [preset],
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
    '../../packages/ui/src/**/*.{ts,tsx}',
  ],
  plugins: [],
};

export default config;
