/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#fef7ee',
          100: '#fdedd3',
          200: '#f9d7a5',
          300: '#f5ba6d',
          400: '#f09432',
          500: '#ed7b14',
          600: '#de600a',
          700: '#b8470b',
          800: '#933810',
          900: '#773010',
        },
        bakery: {
          cream: '#FFF8F0',
          brown: '#8B4513',
          gold: '#DAA520',
          warm: '#F5E6D3',
        },
      },
    },
  },
  plugins: [],
}
