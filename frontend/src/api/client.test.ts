import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, postJson } from "./client";

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

describe("postJson", () => {
  it("envia POST com JSON e devolve o corpo da resposta", async () => {
    const fetchMock = vi.fn(async () => json(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(postJson("/api/x", { a: 1 })).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith("/api/x", expect.objectContaining({
      method: "POST", body: JSON.stringify({ a: 1 }), headers: { "Content-Type": "application/json" },
    }));
  });

  it("converte o 422 da API em ApiError com código, mensagem e campos", async () => {
    const body = { code: "invalid_request", message: "ruim", fields: [{ field: "lambda", message: "x" }] };
    vi.stubGlobal("fetch", vi.fn(async () => json(422, body)));
    const e = await failure(postJson("/api/x", {}));
    expect(e).toBeInstanceOf(ApiError);
    expect(e).toMatchObject({ code: "invalid_request", message: "ruim", fields: body.fields });
  });

  it.each(["unstable_system", "invalid_parameter", "insufficient_sample"] as const)(
    "reconhece o código %s", async (code) => {
      vi.stubGlobal("fetch", vi.fn(async () => json(422, { code, message: "m" })));
      expect((await failure(postJson("/api/x", {}))).code).toBe(code);
    },
  );

  it("trata 422 com código desconhecido como erro genérico de HTTP", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(422, { code: "outro", message: "m" })));
    const e = await failure(postJson("/api/x", {}));
    expect(e.code).toBe("http");
    expect(e.message).toContain("422");
  });

  it("trata erro 500, mesmo sem corpo JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("Internal Server Error", { status: 500 })));
    const e = await failure(postJson("/api/x", {}));
    expect(e).toMatchObject({ code: "http" });
    expect(e.message).toContain("500");
  });

  it("só o status 422 conta como erro de domínio, mesmo que o corpo traga um código válido", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(500, { code: "unstable_system", message: "m" })));
    const e = await failure(postJson("/api/x", {}));
    expect(e.code).toBe("http");
    expect(e.message).toContain("500");
  });

  it("falha de rede vira o erro 'network'", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const e = await failure(postJson("/api/x", {}));
    expect(e.code).toBe("network");
    expect(e.message).toMatch(/conectar à API/);
  });

  it("requisição cancelada vira o erro 'aborted'", async () => {
    const controller = new AbortController();
    vi.stubGlobal("fetch", vi.fn(async () => { throw new DOMException("Aborted", "AbortError"); }));
    controller.abort();
    expect((await failure(postJson("/api/x", {}, controller.signal))).code).toBe("aborted");
  });
});
