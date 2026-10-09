import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/** Garante o contraste WCAG AA dos pares de cores definidos em styles.css (RNF-15). */
// O Vitest está com `css: false` (CSS vira vazio), então o arquivo é lido direto do disco.
// O `npm test` sempre roda a partir de frontend/.
const css = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

function tokens(block: string): Record<string, string> {
  return Object.fromEntries([...block.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})/g)].map((m) => [m[1], m[2]]));
}
const lightBlock = /:root \{([\s\S]*?)\n\}/.exec(css)![1];
const darkBlock = /@media \(prefers-color-scheme: dark\) \{\s*:root \{([\s\S]*?)\n  \}/.exec(css)![1];
const light = tokens(lightBlock);
const dark = { ...light, ...tokens(darkBlock) };

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT_PAIRS: [string, string][] = [
  ...(["text-primary", "text-secondary", "text-muted"] as const).flatMap((t) =>
    (["bg", "surface", "surface-2"] as const).map((bg): [string, string] => [t, bg])),
  ["accent-text", "accent-bg"], ["on-accent", "accent"], ["accent-text", "surface"], ["danger-text", "surface"],
  ["success-text", "success-bg"], ["warning-text", "warning-bg"], ["info-text", "info-bg"], ["danger-text", "danger-bg"],
];
// WCAG 1.4.11: bordas de campos e elementos gráficos precisam de 3:1 contra o fundo.
const UI_PAIRS: [string, string][] = [
  ["border-strong", "surface"], ["chart-accent", "surface"], ["chart-danger", "surface"], ["accent", "surface"],
];

describe.each([["tema claro", light], ["tema escuro", dark]] as const)("contraste no %s", (_name, theme) => {
  it.each(TEXT_PAIRS)("texto %s sobre %s tem pelo menos 4,5:1", (fg, bg) => {
    expect(contrast(theme[fg], theme[bg]), `${fg} (${theme[fg]}) sobre ${bg} (${theme[bg]})`).toBeGreaterThanOrEqual(4.5);
  });
  it.each(UI_PAIRS)("%s sobre %s tem pelo menos 3:1 (elementos de interface)", (fg, bg) => {
    expect(contrast(theme[fg], theme[bg]), `${fg} (${theme[fg]}) sobre ${bg} (${theme[bg]})`).toBeGreaterThanOrEqual(3);
  });
});

describe("o próprio cálculo de contraste", () => {
  it("preto sobre branco é 21:1 e cor igual é 1:1", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21, 5);
    expect(contrast("#777777", "#777777")).toBeCloseTo(1, 5);
  });
});
