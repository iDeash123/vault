import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    borderRadius: {
      none: "0px",
      DEFAULT: "0px",
    },
    extend: {
      colors: {
        obsidian: "var(--ub-obsidian)",
        concrete: "var(--ub-concrete)",
        slate: "var(--ub-slate)",
        mist: "var(--ub-mist)",
        carbon: "var(--ub-carbon)",
        alabaster: "var(--ub-alabaster)",
        ub: {
          obsidian: "var(--ub-obsidian)",
          concrete: "var(--ub-concrete)",
          slate: "var(--ub-slate)",
          mist: "var(--ub-mist)",
          carbon: "var(--ub-carbon)",
          alabaster: "var(--ub-alabaster)",
        },
      },
      fontFamily: {
        display: ["var(--font-display)"],
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
    },
  },
  plugins: [],
};

export default config;
