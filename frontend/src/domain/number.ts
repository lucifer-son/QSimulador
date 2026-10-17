/** Converte texto em número. Aceita vírgula decimal; rejeita vazio e lixo (ex.: "0x10"). */
export function parseNumber(text: string): number {
  const t = text.trim().replace(",", ".");
  if (!/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(t)) return NaN;
  return Number(t);
}
