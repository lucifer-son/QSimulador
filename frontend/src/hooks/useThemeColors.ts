import { useEffect, useState } from "react";

export interface ThemeColors {
  text: string;
  textSecondary: string;
  textMuted: string;
  border: string;
  accent: string;
  danger: string;
}

const VARS: Record<keyof ThemeColors, string> = {
  text: "--text-primary",
  textSecondary: "--text-secondary",
  textMuted: "--text-muted",
  border: "--border",
  accent: "--chart-accent",
  danger: "--chart-danger",
};

function read(): ThemeColors {
  const style = getComputedStyle(document.documentElement);
  const get = (name: string) => style.getPropertyValue(name).trim() || "#888780";
  return Object.fromEntries(
    (Object.keys(VARS) as (keyof ThemeColors)[]).map((k) => [k, get(VARS[k])]),
  ) as unknown as ThemeColors;
}

/** Os gráficos (canvas/SVG do Plotly) não leem variáveis CSS: lemos o valor e acompanhamos o tema. */
export function useThemeColors(): ThemeColors {
  const [colors, setColors] = useState<ThemeColors>(read);
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setColors(read());
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return colors;
}
