import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getClientId } from "./clientId";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("getClientId", () => {
  it("cria um UUID e guarda no navegador", () => {
    const id = getClientId();
    expect(id).toMatch(UUID);
    expect(window.localStorage.getItem("qsimulador-client-id")).toBe(id);
  });

  it("devolve sempre o mesmo identificador", () => {
    expect(getClientId()).toBe(getClientId());
  });

  it("reaproveita o que já estava guardado", () => {
    window.localStorage.setItem("qsimulador-client-id", "11111111-2222-4333-8444-555555555555");
    expect(getClientId()).toBe("11111111-2222-4333-8444-555555555555");
  });

  it("troca um valor guardado que não é UUID", () => {
    window.localStorage.setItem("qsimulador-client-id", "lixo");
    const id = getClientId();
    expect(id).toMatch(UUID);
    expect(window.localStorage.getItem("qsimulador-client-id")).toBe(id);
  });

  it("com o armazenamento bloqueado, mantém um identificador estável até recarregar", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("bloqueado"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("bloqueado"); });
    const id = getClientId();
    expect(id).toMatch(UUID);
    expect(getClientId()).toBe(id);
  });
});
