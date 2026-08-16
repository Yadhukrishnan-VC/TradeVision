import type { Config } from "tailwindcss";

// Tailwind config — default palette per 02_FRONTEND_AND_DESIGN.md.
// The markdown package explicitly forbids custom theme extensions; semantic
// colors (profit/loss, status, regime) are encoded as utility classes in components.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Consolas",
          "Liberation Mono",
          "DejaVu Sans Mono",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
} satisfies Config;
