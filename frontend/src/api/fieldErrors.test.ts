import { describe, expect, it } from "vitest";
import { ApiError, type ApiErrorCode } from "./client";
import { fieldErrorsFromApi } from "./fieldErrors";
import { fixtures } from "../test/helpers";

const fromFixture = (f: { code: string; message: string; fields?: { field: string; message: string }[] }) =>
  new ApiError(f.code as ApiErrorCode, f.message, f.fields);

describe("fieldErrorsFromApi", () => {
  it("invalid_request: marca cada campo listado, com os nomes do formulário", () => {
    const errors = fieldErrorsFromApi(fromFixture(fixtures.errorInvalidRequest));
    expect(Object.keys(errors).sort()).toEqual(["lambda", "servers"]);
    expect(Object.values(errors).every((m) => m === "Valor inválido para este campo.")).toBe(true);
  });

  it("traduz os nomes de campo da API para os do formulário", () => {
    const e = new ApiError("invalid_request", "m", [
      { field: "simulation_time", message: "x" }, { field: "warmup_time", message: "x" },
      { field: "replications", message: "x" }, { field: "seed", message: "x" },
      { field: "campo_desconhecido", message: "x" },
    ]);
    expect(Object.keys(fieldErrorsFromApi(e)).sort())
      .toEqual(["replications", "seed", "simulationTime", "warmupTime"]);
  });

  describe("erros de regra: o campo vem da API, sem adivinhar pelo texto", () => {
    it("unstable_system: a mensagem da API aparece em λ", () => {
      expect(fieldErrorsFromApi(fromFixture(fixtures.errorUnstable))).toEqual({ lambda: fixtures.errorUnstable.message });
    });

    it("invalid_parameter: capacity < servers aparece em capacidade", () => {
      expect(fieldErrorsFromApi(fromFixture(fixtures.errorInvalidParameter))).toEqual({ capacity: fixtures.errorInvalidParameter.message });
    });

    it("menos de 2 réplicas aparece no campo de réplicas", () => {
      const errors = fieldErrorsFromApi(fromFixture(fixtures.errorReplications));
      expect(errors).toEqual({ replications: fixtures.errorReplications.message });
      expect(errors.replications).toMatch(/entre 2 e 100/);
    });

    it.each([
      ["lambda", "lambda"], ["mu", "mu"], ["servers", "servers"], ["capacity", "capacity"],
      ["simulation_time", "simulationTime"], ["warmup_time", "warmupTime"], ["replications", "replications"], ["seed", "seed"],
    ])("o campo %s da API vira %s no formulário", (apiField, formField) => {
      const e = new ApiError("invalid_parameter", "msg", [{ field: apiField, message: "msg do campo" }]);
      expect(fieldErrorsFromApi(e)).toEqual({ [formField]: "msg do campo" });
    });

    it("insufficient_sample: pede mais tempo simulado", () => {
      const e = new ApiError("insufficient_sample", "m", [{ field: "simulation_time", message: "m" }]);
      expect(fieldErrorsFromApi(e)).toEqual({ simulationTime: "Aumente o tempo simulado." });
    });

    it("erro sem campo (ex.: o texto cita um campo, mas a API não o informou) não marca nada", () => {
      expect(fieldErrorsFromApi(new ApiError("invalid_parameter", "capacity deve ser maior ou igual a servers."))).toEqual({});
      expect(fieldErrorsFromApi(new ApiError("unstable_system", "λ < μ"))).toEqual({});
    });
  });

  it("erros de rede e HTTP não marcam campos", () => {
    expect(fieldErrorsFromApi(new ApiError("network", "m"))).toEqual({});
    expect(fieldErrorsFromApi(new ApiError("http", "m"))).toEqual({});
  });
});
