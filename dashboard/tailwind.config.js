/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0A0E17',
          secondary: '#111827',
          tertiary: '#1F2937',
        },
        accent: {
          green: '#00FF88',
          amber: '#FFB800',
          red: '#FF3366',
          blue: '#3B82F6',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        display: ['Space Grotesk', 'Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
