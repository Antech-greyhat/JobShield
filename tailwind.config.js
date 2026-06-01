/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    "./popup/**/*.{html,js}",
    "./pages/**/*.{html,js}",
    "./content/**/*.{html,js}",
    "./scripts/**/*.js"
  ],
  theme: {
    extend: {
      colors: {
        primary: "var(--primary)",
        "primary-dark": "var(--primary-dark)",
        secondary: "var(--secondary)",
        danger: "var(--danger)",
        warning: "var(--warning)",
        success: "var(--success)",
        background: "var(--background)",
        surface: "var(--surface)",
        text: "var(--text)",
        "text-muted": "var(--text-muted)",
        border: "var(--border)"
      }
    },
  },
  plugins: [],
}
