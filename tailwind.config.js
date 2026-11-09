/**
 * Tailwind build config (zamiast Play CDN). Po zmianie klas w szablonach przebuduj CSS:
 *   npx tailwindcss@3.4.17 -c tailwind.config.js -i static/css/tailwind.input.css -o static/css/tailwind.css --minify
 * Zbudowany static/css/tailwind.css jest w repozytorium, więc do uruchomienia aplikacji Node nie jest potrzebny.
 */
module.exports = {
  content: ['./templates/**/*.html', './static/js/**/*.js'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        accent: { DEFAULT: '#6c5ce7', dark: '#5a4bd1', light: '#a29bfe' },
        surface: { DEFAULT: '#1a1a2e', light: '#22223a', dark: '#0f0f1a' },
        border: '#2a2a44',
      },
    },
  },
  plugins: [],
};
