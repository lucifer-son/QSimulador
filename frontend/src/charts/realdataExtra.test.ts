import { describe, expect, it } from "vitest";
import { levelChart } from "./realdata";
import { clone, colors, fixtures as fx } from "../test/helpers";

const levels = fx.realdataLevelsImport.levels as Parameters<typeof levelChart>[0]["levels"];
const comparison = fx.realdataCompareSimulated.comparison as Parameters<typeof levelChart>[1];

describe("levelChart com simulação", () => {
  it("acrescenta a curva simulada, com barras de IC, depois da do modelo", () => {
    const { data } = levelChart({ levels }, comparison, "W", colors) as { data: Record<string, any>[] };
    expect(data.map((t) => t.name)).toEqual(["Medido (IC 95%)", "Modelo", "Simulação"]);
    expect(data[2].y).toEqual(comparison.map((c) => c.metrics.W.simulated_mean));
    expect(data[2].error_y.array.every((v: number) => v >= 0)).toBe(true);
    expect(data[2].error_y.arrayminus.every((v: number) => v >= 0)).toBe(true);
  });

  it("serve também para a vazão", () => {
    const { data } = levelChart({ levels }, comparison, "throughput", colors) as { data: Record<string, any>[] };
    expect(data[2].y).toEqual(comparison.map((c) => c.metrics.throughput.simulated_mean));
  });

  it("sem simulação, o gráfico é o de antes (medido e modelo)", () => {
    const semSim = clone(comparison).map((c) => {
      for (const m of Object.values(c.metrics)) { m.simulated_mean = null; }
      return c;
    });
    const { data } = levelChart({ levels }, semSim, "W", colors) as { data: Record<string, any>[] };
    expect(data).toHaveLength(2);
  });
});
