import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import { exportScenariosCsv, streamScenarios, type ScenarioEvent } from "./scenarios";
import { clone, fixtures as fx, mockFetch, readBlobArrayBuffer, readBlobText } from "../test/helpers";

afterEach(() => vi.unstubAllGlobals());

const events = fx.scenariosCompareMmc as ScenarioEvent[];
const collect = async (body: unknown = {}, signal?: AbortSignal) => {
  const got: ScenarioEvent[] = [];
  await streamScenarios(body, (e) => got.push(e), signal);
  return got;
};

describe("streamScenarios", () => {
  it("lê o NDJSON na ordem, mesmo com linhas cortadas entre os pedaços", async () => {
    const fetchMock = mockFetch(() => ({ body: events, ndjson: true }));
    const got = await collect({ x: 1 });
    expect(got.map((e) => e.type)).toEqual(["start", "base", "scenario", "scenario", "scenario", "done"]);
    expect(got).toEqual(events);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/scenarios/compare");
    expect(fetchMock.mock.calls[0][1]!.method).toBe("POST");
  });

  it("um evento error no meio do fluxo vira ApiError", async () => {
    mockFetch(() => ({
      body: [events[0], { type: "error", code: "insufficient_sample", message: "Aumente simulation_time." }], ndjson: true,
    }));
    const got: string[] = [];
    await expect(streamScenarios({}, (e) => got.push(e.type))).rejects.toMatchObject({
      code: "insufficient_sample", message: "Aumente simulation_time.",
    });
    expect(got).toEqual(["start"]);
  });

  it("erro 422 antes do fluxo traz o código e os campos", async () => {
    mockFetch(() => ({ status: 422, body: fx.errorScenariosCapacity }));
    const error = await collect().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ code: "invalid_parameter", fields: [{ field: "scenarios[0].capacity" }] });
  });

  it("cancelar o sinal vira ApiError 'aborted' e para de ler", async () => {
    mockFetch(() => ({ body: clone(events), ndjson: true }));
    const controller = new AbortController();
    const seen: string[] = [];
    const promise = streamScenarios({}, (e) => { seen.push(e.type); controller.abort(); }, controller.signal);
    await expect(promise).rejects.toMatchObject({ code: "aborted" });
    expect(seen).toEqual(["start"]);
  });

  it("sem conexão: erro de rede", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fail")));
    await expect(collect()).rejects.toMatchObject({ code: "network" });
  });
});

describe("exportScenariosCsv", () => {
  it("devolve o CSV como Blob e envia o mesmo corpo", async () => {
    const fetchMock = mockFetch(() => ({ body: null, text: fx.scenariosExportMmc.text }));
    const blob = await exportScenariosCsv({ seed: 2026 });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/scenarios/export.csv");
    // Blob.text() descarta o BOM ao decodificar; o arquivo baixado mantém os bytes dele.
    expect(await readBlobText(blob)).toBe(fx.scenariosExportMmc.text.replace(/^\ufeff/, ""));
    expect(new Uint8Array(await readBlobArrayBuffer(blob)).slice(0, 3)).toEqual(new Uint8Array([0xef, 0xbb, 0xbf]));
  });
  it("erro 422", async () => {
    mockFetch(() => ({ status: 422, body: fx.errorScenariosCapacity }));
    await expect(exportScenariosCsv({})).rejects.toMatchObject({ code: "invalid_parameter" });
  });
});
