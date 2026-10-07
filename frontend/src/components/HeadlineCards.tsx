import { METRIC_INFO } from "../domain/metrics";
import { formatMetric } from "../domain/format";
import type { MetricName, ViewResult } from "../domain/types";

const QUEUE_CARDS: MetricName[] = ["rho", "throughput", "p_block", "p_wait"];
const MM1_CARDS: MetricName[] = ["rho", "L", "W", "Wq"];

const CARD_LABEL: Partial<Record<MetricName, string>> = {
  rho: "Utilização (ρ)",
  throughput: "Vazão efetiva",
  p_block: "Chegadas recusadas",
  p_wait: "Clientes que esperam",
  L: "Nº médio no sistema",
  W: "Tempo médio no sistema",
  Wq: "Tempo médio de espera",
};

export function HeadlineCards({ result }: { result: ViewResult }) {
  const wanted = result.metrics.some((m) => m.name === "p_block") ? QUEUE_CARDS : MM1_CARDS;
  const cards = wanted
    .map((name) => result.metrics.find((m) => m.name === name))
    .filter((m): m is NonNullable<typeof m> => m !== undefined);

  return (
    <div className="cards" aria-label="Destaques">
      {cards.map((m) => {
        const main = m.analytical ?? m.simulated;
        const secondary = m.analytical !== undefined && m.simulated !== undefined ? m.simulated : undefined;
        return (
          <div className="card" key={m.name}>
            <div className="card-label">{CARD_LABEL[m.name] ?? METRIC_INFO[m.name].label}</div>
            <div className="card-value">{main === undefined ? "—" : formatMetric(m.name, main)}</div>
            {secondary !== undefined && (
              <div className="card-sub">simulado: {formatMetric(m.name, secondary)}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
