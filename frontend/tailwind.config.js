/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      colors: {
        ink: {
          950: "#070a13",
          900: "#0b0f1a",
          850: "#0f1422",
          800: "#141a2b",
          700: "#1c2438",
          600: "#293349",
        },
        brand: {
          50: "#eef2ff",
          100: "#e0e7ff",
          200: "#c7d2fe",
          300: "#a5b4fc",
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
          800: "#3730a3",
          900: "#312e81",
        },
        accent: {
          cyan: "#22d3ee",
          violet: "#a855f7",
          fuchsia: "#e879f9",
        },
      },
      backgroundImage: {
        "brand-gradient":
          "linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #22d3ee 100%)",
        "radial-glow":
          "radial-gradient(60% 60% at 50% 0%, rgba(99,102,241,0.25) 0%, rgba(99,102,241,0) 70%)",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(99,102,241,0.25), 0 20px 60px -15px rgba(99,102,241,0.5)",
        "glow-sm": "0 0 30px -10px rgba(99,102,241,0.6)",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-12px)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
      },
      animation: {
        float: "float 6s ease-in-out infinite",
        "pulse-ring": "pulse-ring 1.8s cubic-bezier(0.22,1,0.36,1) infinite",
      },
    },
  },
  plugins: [],
};
