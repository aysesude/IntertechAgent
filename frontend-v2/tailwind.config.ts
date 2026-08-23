import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // brand/navy/ink/line/surface CSS custom property'lere referans
        // veriyor (bkz. src/index.css :root / .dark) — light/dark tema
        // arasında geçiş bu sayede tek yerden (CSS var'lar) yönetiliyor.
        // danger ve brand'in dark/darker/light alt tonları bilinçli olarak
        // sabit hex kaldı. tint/border ise CSS var'a bağlandı: text-brand
        // (dark modda daha açık bir mavi) sabit bg-brand-tint üzerinde
        // düşük kontrast oluşturuyordu (rozet/kart metinleri) — ikisi de
        // temaya göre birlikte değişsin diye.
        brand: {
          DEFAULT: "var(--color-brand)",
          dark: "#1A3FB0",
          darker: "#122C82",
          light: "#6C93F5",
          tint: "var(--color-brand-tint)",
          border: "var(--color-brand-border)",
          bright: "var(--color-brand-bright)",
        },
        navy: "var(--color-navy)",
        positive: "var(--color-positive)",
        negative: "var(--color-negative)",
        // Koyu tema-only: birincil buton dolgusu + avatar zemini (bkz.
        // Button.tsx, Header.tsx) — tek kaynak src/index.css .dark bloğu.
        "cta-dark": "var(--color-cta-dark)",
        ink: {
          DEFAULT: "var(--color-ink)",
          soft: "var(--color-ink-soft)",
          muted: "var(--color-ink-muted)",
          faint: "var(--color-ink-faint)",
        },
        line: "var(--color-line)",
        line2: "var(--color-line-2)",
        surface: "var(--color-surface)",
        "surface-elevated": "var(--color-surface-elevated)",
        danger: {
          DEFAULT: "#E63946",
          tint: "#FEF2F3",
        },
      },
      fontFamily: {
        sans: ["Manrope", "system-ui", "sans-serif"],
        display: ["Sora", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 6px 20px rgba(37,87,232,.08)",
        pop: "0 14px 34px rgba(11,14,20,.12)",
        widget: "0 18px 50px rgba(11,14,20,.14)",
      },
      keyframes: {
        fadeUp: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "none" },
        },
        pulseDot: {
          "0%, 100%": { opacity: ".35" },
          "50%": { opacity: "1" },
        },
        slideUpPanel: {
          "0%": { transform: "translateY(16px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        sonarPing: {
          "0%": { transform: "scale(1)", opacity: ".9" },
          "16%": { transform: "scale(1.4)", opacity: "0" },
          "100%": { transform: "scale(1.4)", opacity: "0" },
        },
        tipIn: {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        // "VİRA düşünüyor…" noktaları. pulseDot'tan ayrı: o 2 saniyelik
        // sakin bir "çevrimiçi" nabzı, bu ise sıra sıra yanan bir bekleme
        // işareti — aynı ritmi paylaşsalardı ikisi de anlamını yitirirdi.
        thinkingDot: {
          "0%, 80%, 100%": { opacity: ".25", transform: "translateY(0)" },
          "40%": { opacity: "1", transform: "translateY(-2px)" },
        },
      },
      animation: {
        fadeUp: "fadeUp .3s ease-out both",
        pulseDot: "pulseDot 2s infinite",
        thinkingDot: "thinkingDot 1.2s ease-in-out infinite",
        slideUpPanel: "slideUpPanel .2s cubic-bezier(0.4,0,0.2,1)",
        sonarPing: "sonarPing 4.6s ease-out infinite",
        tipIn: "tipIn .15s ease-out both",
      },
    },
  },
  plugins: [],
} satisfies Config;
