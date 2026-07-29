import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#0d1117", soft: "#161b22", line: "#26303d" },
        accent: { DEFAULT: "#3b82f6", soft: "#60a5fa" },
      },
    },
  },
  plugins: [],
} satisfies Config;
