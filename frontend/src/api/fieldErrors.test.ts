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
  });

  it("invalid_request: traduz os nomes de campo da API para os do formulário", () => {
    const e = new ApiError("invalid_request", "m", [
      { field: "simulation_time", message: "x" }, { field: "warmup_time", message: "x" },
      { field: "replications", message: "x" }, { field: "seed", message: "x" },
      { field: "campo_desconhecido", message: "x" },
    ]);
    expect(Object.keys(fieldErrorsFromApi(e)).sort())
      .toEqual(["replications", "seed", "simulationTime", "warmupTime"]);
  });

  it("unstable_system: mostra a mensagem da API em λ", () => {
    const e = fromFixture(fixtures.errorUnstable);
    expect(fieldErrorsFromApi(e)).toEqual({ lambda: fixtures.errorUnstable.message });
  });

  it("insufficient_sample: pede mais tempo simulado", () => {
    const e = new ApiError("insufficient_sample", "m");
    expect(fieldErrorsFromApi(e)).toEqual({ simulationTime: "Aumente o tempo simulado." });
  });

  it("invalid_parameter: acha o campo pelo início da mensagem", () => {
    const e = fromFixture(fixtures.errorInvalidParameter);
    expect(fieldErrorsFromApi(e)).toEqual({ capacity: fixtures.errorInvalidParameter.message });
    const cases: [string, string][] = [
      ["λ deve ser maior que zero.", "lambda"], ["μ deve ser um número finito.", "mu"],
      ["servers deve estar entre 1 e 1000.", "servers"], ["simulation_time deve ser maior que zero.", "simulationTime"],
      ["warmup_time deve ser menor que simulation_time.", "warmupTime"], ["replications deve ser pelo menos 1.", "replications"],
      ["seed deve ser um inteiro entre 0 e 9007199254740991.", "seed"],
    ];
    for (const [message, field] of cases) {
      expect(Object.keys(fieldErrorsFromApi(new ApiError("invalid_parameter", message)))).toEqual([field]);
    }
  });

  it("invalid_parameter sem campo reconhecível não marca nenhum campo", () => {
    const e = new ApiError("invalid_parameter", "Simulação grande demais (~5.000.000 chegadas esperadas).");
    expect(fieldErrorsFromApi(e)).toEqual({});
  });

  it("erros de rede e HTTP não marcam campos", () => {
    expect(fieldErrorsFromApi(new ApiError("network", "m"))).toEqual({});
    expect(fieldErrorsFromApi(new ApiError("http", "m"))).toEqual({});
  });
});
