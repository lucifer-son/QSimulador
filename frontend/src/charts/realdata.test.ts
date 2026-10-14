import { describe, expect, it } from "vitest";
import { levelChart } from "./realdata";
import type { AnalysisResponse, LevelComparison } from "../api/realdata";
import { colors, fixtures as fx } from "../test/helpers";

const result = fx.realdataAnalyzeClosed as AnalysisResponse;
const comparison = result.comparison as LevelComparison[];

describe("levelChart", () => {
  it("compara a medição com o modelo por número de usuários", () => {
    const { data, layout } = levelChart(result, comparison, "W", colors) as {
      data: Record<string, any>[]; layout: any;
    };
    expect(data.map((trace) => trace.name)).toEqual(["Medido (IC 95%)", "Modelo"]);
    expect(data[0].x).toEqual(result.levels.map((level) => level.users));
    expect(data[0].y).toEqual(result.levels.map((level) => level.metrics.mean_response));
    expect(data[1].y).toEqual(comparison.map((level) => level.metrics.W.model));
    expect(layout.xaxis.title.text).toBe("Usuários simultâneos");
  });

  it("seleciona a vazão e mantém só a medição se não houver comparação", () => {
    const { data, layout } = levelChart(result, [], "throughput", colors) as {
      data: Record<string, any>[]; layout: any;
    };
    expect(data).toHaveLength(1);
    expect(data[0].y).toEqual(result.levels.map((level) => level.metrics.throughput));
    expect(layout.yaxis.title.text).toBe("Vazão (req/s)");
  });
});
