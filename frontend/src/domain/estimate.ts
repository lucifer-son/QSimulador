import { formatCompactCount } from "./format";
import { parseNumber } from "./request";

/** Velocidade medida do simulador (chegadas por segundo); varia com a máquina. */
export const ARRIVALS_PER_SECOND = 80_000;

export interface CostEstimate {
  arrivals: number;
  seconds: number;
}

export function estimateCost(lambda: number, time: number, replications: number): CostEstimate | null {
  const arrivals = lambda * time * replications;
  if (![lambda, time, replications].every(Number.isFinite) || arrivals <= 0) return null;
  return { arrivals, seconds: arrivals / ARRIVALS_PER_SECOND };
}

export function describeSeconds(seconds: number): string {
  if (seconds < 1) return "menos de 1 s";
  if (seconds < 60) return `cerca de ${Math.round(seconds)} s`;
  return `cerca de ${Math.round(seconds / 60)} min`;
}

/** Texto de estimativa a partir dos campos do formulário; null se algum for inválido. */
export function estimateText(lambda: string, time: string, replications: string): string | null {
  const e = estimateCost(parseNumber(lambda), parseNumber(time), parseNumber(replications));
  return e ? `${formatCompactCount(e.arrivals)} chegadas, ${describeSeconds(e.seconds)}` : null;
}
