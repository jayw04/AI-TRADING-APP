import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: {
          50: "#fffbeb",
          400: "#facc15",
          500: "#eab308",
          600: "#ca8a04",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
