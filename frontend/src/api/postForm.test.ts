import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, postForm } from "./client";

afterEach(() => vi.unstubAllGlobals());

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (e) {
    return e as ApiError;
  }
  throw new Error("era esperado um erro");
}

describe("postForm", () => {
  it("envia o FormData sem fixar o Content-Type (o navegador define o separador)", async () => {
    const fetchMock = vi.fn(async () => json(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData();
    form.append("file", new File(["a"], "a.csv"));
    await expect(postForm("/api/x", form)).resolves.toEqual({ ok: true });
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.method).toBe("POST");
    expect(init.body).toBe(form);
    expect(init.headers).toBeUndefined();
  });

  it.each([
    [422, "invalid_dataset"], [422, "insufficient_sample"], [413, "file_too_large"],
  ] as const)("converte %i %s em ApiError com o código da API", async (status, code) => {
    vi.stubGlobal("fetch", vi.fn(async () => json(status, { code, message: "m", fields: [{ field: "file", message: "m" }] })));
    const e = await failure(postForm("/api/x", new FormData()));
    expect(e).toMatchObject({ code, message: "m", fields: [{ field: "file", message: "m" }] });
  });

  it("não confunde um 413 de outro servidor (sem código da API) com erro do arquivo", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(413, { detail: "Request Entity Too Large" })));
    expect((await failure(postForm("/api/x", new FormData()))).code).toBe("http");
  });
});
