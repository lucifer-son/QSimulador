import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchRuns, runAction } from "./actions";
import { ApiError } from "./client";
import { fixtures as fx, mockFetch } from "../test/helpers";

afterEach(() => vi.unstubAllGlobals());

const params = {
  lambda: 25, mu: 10, servers: 3, capacity: 6,
  simulationTime: 300, replications: 5, warmupTime: 20, seed: 2026,
};

describe("runAction", () => {
  it("compare: chama a rota do modelo com o corpo certo e normaliza a resposta", async () => {
    const fetchMock = mockFetch(() => ({ body: fx.mmckCompare }));
    const r = await runAction("mmck", "compare", params);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/models/mmck/compare");
    expect(JSON.parse(String(init!.body))).toEqual({
      lambda: 25, mu: 10, servers: 3, capacity: 6,
      simulation_time: 300, replications: 5, warmup_time: 20, seed: 2026,
    });
    expect(r).toMatchObject({ action: "compare", modelLabel: "M/M/3/6" });
  });

  it.each([
    ["mm1", "calculate", fx.mm1Calculate],
    ["mmc", "simulate", fx.mmcSimulate],
    ["mm1k", "compare", fx.mmckCompare],
  ] as const)("%s/%s usa a rota %s correspondente", async (model, action, body) => {
    const fetchMock = mockFetch(() => ({ body }));
    await runAction(model, action, params);
    expect(fetchMock.mock.calls[0][0]).toBe(`/api/models/${model}/${action}`);
  });

  it("propaga o erro tipado da API", async () => {
    mockFetch(() => ({ status: 422, body: fx.errorUnstable }));
    await expect(runAction("mmc", "compare", params)).rejects.toMatchObject({
      code: "unstable_system", message: fx.errorUnstable.message,
    });
    await expect(runAction("mmc", "compare", params)).rejects.toBeInstanceOf(ApiError);
  });
});

describe("fetchRuns", () => {
  it("repete a simulação com a mesma semente do resultado e devolve as réplicas", async () => {
    const fetchMock = mockFetch((url) => ({ body: url.endsWith("/compare") ? fx.mmckCompare : fx.mmckSimulate }));
    const compared = await runAction("mmck", "compare", { ...params, seed: undefined });
    const runs = await fetchRuns(compared);
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/models/mmck/simulate");
    expect(JSON.parse(String(init!.body)).seed).toBe(2026); // semente devolvida pelo /compare
    expect(runs).toHaveLength(5);
  });
});
