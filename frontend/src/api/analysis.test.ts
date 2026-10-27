import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchDistribution, fetchSensitivityCurve, streamFit, type FitEvent } from "./analysis";
import { fixtures as fx, mockFetch, mockPendingFetch } from "../test/helpers";

afterEach(() => vi.unstubAllGlobals());

describe("/api/analysis", () => {
  it("distribution: devolve P(n) e a curva da simulação como a API gravou", async () => {
    const fetchMock = mockFetch(() => ({ body: fx.analysisDistributionMmc }));
    const body = await fetchDistribution({ model: "mmc", lambda: 8, mu: 1, servers: 10 });
    expect(fetchMock.mock.calls[0][0]).toContain("/api/analysis/distribution");
    expect(body.states!.p.reduce((a, b) => a + b, 0) + body.states!.omitted_mass).toBeCloseTo(1, 10);
    expect(body.wait_closed_form!.t[0]).toBe(0);
    expect(body.wait_simulation!.survival).toHaveLength(body.wait_simulation!.t.length);
  });

  it("sensitivity: o ponto atual está na curva", async () => {
    mockFetch(() => ({ body: fx.analysisSensitivityMm1 }));
    const curve = await fetchSensitivityCurve({ model: "mm1", lambda: 40, mu: 50 });
    expect(curve.points[curve.current_index].value).toBe(40);
    expect(curve.current.wq).toBeCloseTo(0.08, 6);
  });

  it("erro 422 chega com o campo", async () => {
    mockFetch(() => ({ status: 422, body: fx.errorAnalysisErlangb }));
    await expect(fetchDistribution({ model: "erlangb", lambda: 5, mu: 10, servers: 2 })).rejects.toMatchObject({
      code: "invalid_parameter", fields: [{ field: "model" }],
    });
  });
});

describe("streamFit", () => {
  it("lê o NDJSON em pedaços que cortam as linhas ao meio, na ordem", async () => {
    mockFetch(() => ({ ndjson: true, body: fx.analysisFitLognormal }));
    const events: FitEvent[] = [];
    await streamFit({ sample: [1, 2, 3] }, (e) => events.push(e));
    expect(events.map((e) => e.type)).toEqual(["start", "candidate", "candidate", "candidate", "candidate", "candidate", "done"]);
    const result = events.at(-1)!.result!;
    expect(result.best).toBe("lognormal");
    expect(result.candidates.map((c) => c.key)).toEqual(["exponential", "erlang", "lognormal", "weibull", "uniform"]);
    expect(result.seed).toBe(7);
  });

  it("amostra constante termina em done com a sugestão M/D/c", async () => {
    mockFetch(() => ({ ndjson: true, body: fx.analysisFitConstant }));
    const events: FitEvent[] = [];
    await streamFit({ sample: [2.5] }, (e) => events.push(e));
    expect(events.at(-1)!.result!.suggestion.model).toBe("M/D/c");
  });

  it("422 antes do fluxo vira ApiError com o campo", async () => {
    mockFetch(() => ({ status: 422, body: fx.errorAnalysisFitSample }));
    await expect(streamFit({ sample: [1] }, () => undefined)).rejects.toMatchObject({ fields: [{ field: "sample" }] });
  });

  it("evento error no meio do fluxo vira ApiError", async () => {
    mockFetch(() => ({ ndjson: true, body: [{ type: "start", n: 10, total: 5 }, { type: "error", message: "Falha." }] }));
    await expect(streamFit({ sample: [1] }, () => undefined)).rejects.toMatchObject({ message: "Falha." });
  });

  it("cancelar fecha a conexão e devolve aborted", async () => {
    mockPendingFetch();
    const controller = new AbortController();
    const promise = streamFit({ sample: [1] }, () => undefined, controller.signal);
    controller.abort();
    await expect(promise).rejects.toMatchObject({ code: "aborted" });
  });
});
