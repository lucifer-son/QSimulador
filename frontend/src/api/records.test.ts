import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import { createRecord, deleteRecord, getRecord, getRecordsStatus, listRecords, renameRecord } from "./records";

const ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

const reply = (status: number, body?: unknown) =>
  new Response(status === 204 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function stub(response: Response) {
  const fn = vi.fn(async (_url: string, _init?: RequestInit) => response);
  vi.stubGlobal("fetch", fn);
  return fn;
}
const initOf = (fn: ReturnType<typeof stub>) => fn.mock.calls[0][1] as RequestInit;
const headersOf = (fn: ReturnType<typeof stub>) => initOf(fn).headers as Record<string, string>;

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try { await promise; } catch (e) { return e as ApiError; }
  throw new Error("era esperado um erro");
}

describe("histórico: pedidos", () => {
  it("status não envia identificador", async () => {
    const fn = stub(reply(200, { enabled: true, max_record_bytes: 1, max_records_per_client: 2 }));
    await expect(getRecordsStatus()).resolves.toMatchObject({ enabled: true });
    expect(fn.mock.calls[0][0]).toBe("/api/records/status");
    expect(initOf(fn).headers).toBeUndefined();
  });

  it("listar monta a query e envia o X-Client-Id", async () => {
    const fn = stub(reply(200, { items: [], total: 0, limit: 5, offset: 10 }));
    await listRecords({ kind: "experiment", limit: 5, offset: 10 });
    expect(fn.mock.calls[0][0]).toBe("/api/records?kind=experiment&limit=5&offset=10");
    expect(headersOf(fn)["X-Client-Id"]).toBe(window.localStorage.getItem("qsimulador-client-id"));
  });

  it("listar sem filtros não deixa '?' na URL", async () => {
    const fn = stub(reply(200, { items: [], total: 0, limit: 20, offset: 0 }));
    await listRecords();
    expect(fn.mock.calls[0][0]).toBe("/api/records");
  });

  it("abrir busca um registro pelo id", async () => {
    const fn = stub(reply(200, { id: ID }));
    await getRecord(ID);
    expect(fn.mock.calls[0][0]).toBe(`/api/records/${ID}`);
  });

  it("salvar envia POST com JSON", async () => {
    const fn = stub(reply(201, { id: ID }));
    const record = { kind: "simulation" as const, title: "t", params: { a: 1 }, result: { b: 2 } };
    await createRecord(record);
    expect(initOf(fn).method).toBe("POST");
    expect(JSON.parse(String(initOf(fn).body))).toEqual(record);
    expect(headersOf(fn)["Content-Type"]).toBe("application/json");
    expect(headersOf(fn)["X-Client-Id"]).toBeTruthy();
  });

  it("renomear envia PATCH só com o título", async () => {
    const fn = stub(reply(200, { id: ID, title: "novo" }));
    await renameRecord(ID, "novo");
    expect(initOf(fn).method).toBe("PATCH");
    expect(JSON.parse(String(initOf(fn).body))).toEqual({ title: "novo" });
  });

  it("excluir aceita a resposta 204, sem corpo", async () => {
    const fn = stub(reply(204));
    await expect(deleteRecord(ID)).resolves.toBeUndefined();
    expect(initOf(fn).method).toBe("DELETE");
  });
});

describe("histórico: erros", () => {
  it.each([
    [503, "persistence_disabled"],
    [503, "database_unavailable"],
    [404, "record_not_found"],
    [409, "record_limit_reached"],
    [413, "record_too_large"],
    [422, "invalid_client_id"],
    [422, "invalid_record"],
  ] as const)("HTTP %s com %s vira ApiError com o código", async (status, code) => {
    stub(reply(status, { code, message: "mensagem da API" }));
    const e = await failure(listRecords());
    expect(e).toBeInstanceOf(ApiError);
    expect(e).toMatchObject({ code, message: "mensagem da API" });
  });

  it("um código do histórico em status que não é o dele continua sendo erro genérico", async () => {
    stub(reply(500, { code: "record_not_found", message: "x" }));
    expect((await failure(listRecords())).code).toBe("http");
  });
});
