import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { fromCalculate } from "./api/mappers";
import { labRecord, parseLabRecord } from "./domain/records";
import { clone, fixtures as fx, mockFetch, type FakeHandler } from "./test/helpers";

vi.mock("plotly.js-basic-dist-min", () => ({
  default: { react: vi.fn().mockResolvedValue(undefined), purge: vi.fn() },
}));

afterEach(() => vi.unstubAllGlobals());

const modelSelect = () => screen.getByLabelText("Modelo");
const bodyOf = (fetchMock: ReturnType<typeof mockFetch>, call = 0) =>
  JSON.parse(String(fetchMock.mock.calls[call][1]!.body)) as Record<string, unknown>;

async function openLab(model: string, handler: FakeHandler) {
  const fetchMock = mockFetch(handler);
  const user = userEvent.setup();
  render(<App />);
  await user.selectOptions(modelSelect(), model);
  return { user, fetchMock };
}

// ---------- Experimentos do M/G/1 ----------

const mg1Experiments: FakeHandler = (url) => {
  if (url.endsWith("/sweep")) return { body: fx.experimentSweepMg1 };
  if (url.endsWith("/services")) return { body: fx.experimentServicesMg1 };
  return { body: fx.experimentSensitivityMg1 };
};

async function openMg1Experiments(handler: FakeHandler = mg1Experiments) {
  const ctx = await openLab("mg1", handler);
  await ctx.user.click(screen.getByRole("button", { name: "Experimentos" }));
  return ctx;
}

describe("experimentos do M/G/1", () => {
  it("troca comparar servidores por comparar distribuições", async () => {
    await openMg1Experiments();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Varredura de parâmetro", "Comparar distribuições", "Sensibilidade",
    ]);
    expect(screen.queryByText(/não cobrem o serviço geral/)).toBeNull();
  });

  it("mostra o serviço (e não μ) entre os parâmetros fixos", async () => {
    await openMg1Experiments();
    const fixed = screen.getByRole("form", { name: "Parâmetros da varredura" });
    expect(within(fixed).getByText("Serviço").nextSibling).toHaveTextContent("Lognormal, E[S] = 0.02 s, CV = 0.5");
    expect(within(fixed).queryByText("μ")).toBeNull();
  });

  it("oferece λ, μ e o CV como parâmetros varridos da lognormal", async () => {
    await openMg1Experiments();
    const options = within(screen.getByLabelText("Parâmetro varrido")).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(["Chegadas λ", "Serviço μ", "CV do serviço"]);
  });

  it("varre o CV enviando o serviço e mostra a espera crescendo", async () => {
    const { user, fetchMock } = await openMg1Experiments();
    await user.selectOptions(screen.getByLabelText("Parâmetro varrido"), "cv");
    expect(screen.getByLabelText("Início")).toHaveValue("0.25");
    expect(screen.getByLabelText("Fim")).toHaveValue("3");
    await user.click(screen.getByRole("button", { name: "Gerar curva" }));
    await screen.findByRole("table");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/experiments/sweep");
    expect(bodyOf(fetchMock)).toEqual({
      model: "mg1", variable: "cv", lambda: 25, service: { distribution: "lognormal", mean: 0.02, cv: 0.5 },
      start: 0.25, end: 3, step: 0.25,
    });
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent))
      .toEqual(["CV do serviço", "λ·E[S]", "Situação", "ρ", "L", "Lq", "W", "Wq", "P0", "Vazão"]);
    expect(screen.getByRole("img", { name: /em função de CV do serviço/ })).toBeInTheDocument();
  });

  it("o Erlang oferece k em vez do CV", async () => {
    const { user } = await openLab("mg1", mg1Experiments);
    await user.selectOptions(screen.getByLabelText("Distribuição do serviço"), "erlang");
    await user.click(screen.getByRole("button", { name: "Experimentos" }));
    const options = within(screen.getByLabelText("Parâmetro varrido")).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(["Chegadas λ", "Serviço μ", "Etapas k (Erlang)"]);
  });

  it("distribuição sem parâmetro de forma só varre λ e μ", async () => {
    const { user } = await openLab("mg1", mg1Experiments);
    await user.selectOptions(screen.getByLabelText("Distribuição do serviço"), "deterministic");
    await user.click(screen.getByRole("button", { name: "Experimentos" }));
    const options = within(screen.getByLabelText("Parâmetro varrido")).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(["Chegadas λ", "Serviço μ"]);
  });

  it("compara distribuições com a mesma média e mostra uma curva por distribuição", async () => {
    const { user, fetchMock } = await openMg1Experiments();
    await user.click(screen.getByRole("tab", { name: "Comparar distribuições" }));
    const form = screen.getByRole("form", { name: "Parâmetros da comparação de distribuições" });
    expect(within(form).getByLabelText(/Serviço do Laboratório \(Lognormal, CV 0.5\)/)).toBeChecked();
    expect(within(form).getByLabelText("Determinística (CV 0)")).toBeChecked();
    expect(within(form).getByLabelText("Exponencial (CV 1)")).toBeChecked();
    expect(within(form).getByLabelText("Lognormal (CV 2)")).not.toBeChecked();
    await user.click(within(form).getByRole("button", { name: "Comparar distribuições" }));
    await screen.findByRole("img", { name: /por distribuição de serviço/ });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/experiments/services");
    expect(bodyOf(fetchMock)).toEqual({
      services: [
        { distribution: "lognormal", mean: 0.02, cv: 0.5 },
        { distribution: "deterministic", mean: 0.02 },
        { distribution: "exponential", mean: 0.02 },
      ],
      start: 5, end: 60, step: 5,
    });
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "λ (req/s)", "Determinística (M/D/1) (CV 0)", "Exponencial (CV 1)", "Lognormal (CV 1,5)",
    ]);
    expect(screen.getAllByText(/instável a partir de λ = 50 req\/s/)).toHaveLength(3);   // as três saturam em 1/E[S]
  });

  it("recusa menos de duas distribuições, sem chamar a API", async () => {
    const { user, fetchMock } = await openMg1Experiments();
    await user.click(screen.getByRole("tab", { name: "Comparar distribuições" }));
    await user.click(screen.getByLabelText("Determinística (CV 0)"));
    await user.click(screen.getByLabelText("Exponencial (CV 1)"));
    await user.click(screen.getByRole("button", { name: "Comparar distribuições" }));
    expect(await screen.findByText("Escolha de 2 a 8 distribuições.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a sensibilidade envia o serviço e lista o CV entre os parâmetros", async () => {
    const { user, fetchMock } = await openMg1Experiments();
    await user.click(screen.getByRole("tab", { name: "Sensibilidade" }));
    expect(screen.getByLabelText("Variação de λ, μ e CV (%)")).toHaveValue("10");
    await user.click(screen.getByRole("button", { name: "Analisar sensibilidade" }));
    await screen.findByRole("table");
    expect(bodyOf(fetchMock)).toEqual({
      model: "mg1", lambda: 25, service: { distribution: "lognormal", mean: 0.02, cv: 0.5 }, delta_pct: 10,
    });
    const rows = within(screen.getByRole("table")).getAllByRole("rowheader").map((h) => h.textContent);
    expect(rows).toEqual(expect.arrayContaining(["Chegadas λ", "Serviço μ", "CV do serviço"]));
  });

  it("volta para a varredura se a aba aberta deixa de existir ao trocar de modelo", async () => {
    const { user } = await openMg1Experiments();
    await user.click(screen.getByRole("tab", { name: "Comparar distribuições" }));
    await user.click(screen.getByRole("button", { name: "Laboratório" }));
    await user.selectOptions(modelSelect(), "mm1");
    await user.click(screen.getByRole("button", { name: "Experimentos" }));
    expect(screen.getByRole("tab", { name: "Varredura de parâmetro" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Comparar servidores" })).toBeInTheDocument();
  });
});

// ---------- Erlang-B no Laboratório ----------

const erlangHandler: FakeHandler = (url) => {
  if (url.endsWith("/size")) return { body: fx.erlangbSize };
  if (url.endsWith("/compare")) return { body: fx.erlangbCompare };
  if (url.endsWith("/simulate")) return { body: fx.erlangbSimulate };
  return { body: fx.erlangbCalculate };
};

describe("Erlang-B (perda)", () => {
  it("pede λ, μ e servidores, sem capacidade, com o exemplo da documentação", async () => {
    await openLab("erlangb", erlangHandler);
    expect(screen.getByLabelText(/Chegadas λ/)).toHaveValue("20");
    expect(screen.getByLabelText("Serviço μ (por servidor)")).toHaveValue("1");
    expect(screen.getByLabelText("Servidores c")).toHaveValue("15");
    expect(screen.queryByLabelText("Capacidade K")).toBeNull();
  });

  it("calcula pelo endpoint dedicado e destaca o bloqueio", async () => {
    const { user, fetchMock } = await openLab("erlangb", erlangHandler);
    await user.click(screen.getByRole("button", { name: "Só calcular" }));
    expect(await screen.findByText("Bloqueio (chamadas perdidas)")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/models/erlangb/calculate");
    expect(bodyOf(fetchMock)).toEqual({ lambda: 20, mu: 1, servers: 15 });
    expect(screen.getByText("33%", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("M/M/15/15", { exact: false })).toBeInTheDocument();
  });

  it("os detalhes trazem tráfego oferecido, carregado e perdido", async () => {
    const { user } = await openLab("erlangb", erlangHandler);
    await user.click(screen.getByRole("button", { name: "Só calcular" }));
    await screen.findByText("Bloqueio (chamadas perdidas)");
    await user.click(screen.getByRole("tab", { name: "Detalhes" }));
    expect(screen.getByText("Tráfego oferecido a = λ/μ").nextSibling).toHaveTextContent("20 Erlangs");
    expect(screen.getByText("Tráfego carregado").nextSibling).toHaveTextContent("13,4001 Erlangs");
    expect(screen.getByText("Chegadas perdidas").nextSibling).toHaveTextContent("6,59994 req/s");
  });

  it("compara com a simulação (M/M/c/K com K = c)", async () => {
    const { user, fetchMock } = await openLab("erlangb", erlangHandler);
    await user.click(screen.getByRole("button", { name: "Comparar" }));
    await screen.findByRole("table");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/models/erlangb/compare");
    expect(bodyOf(fetchMock)).toMatchObject({ lambda: 20, mu: 1, servers: 15, seed: 2026 });
  });

  it("sugere o menor c para o bloqueio alvo e aplica ao formulário", async () => {
    const { user, fetchMock } = await openLab("erlangb", erlangHandler);
    await user.click(screen.getByRole("button", { name: /Sugerir c/ }));
    expect(await screen.findByRole("status")).toHaveTextContent(/Com c = 30 o bloqueio é 0,85%; com c = 29 seria 1,28%/);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/models/erlangb/size");
    expect(bodyOf(fetchMock)).toEqual({ lambda: 20, mu: 1, target_blocking: 0.01 });
    await user.click(screen.getByRole("button", { name: "Usar c = 30" }));
    expect(screen.getByLabelText("Servidores c")).toHaveValue("30");
  });

  it("alvo inválido é recusado na tela e erro da API aparece no campo", async () => {
    const { user, fetchMock } = await openLab("erlangb", () => ({
      status: 422,
      body: { code: "invalid_parameter", message: "target_blocking deve ser menor que 1.", fields: [{ field: "target_blocking", message: "x" }] },
    }));
    await user.clear(screen.getByLabelText("Bloqueio alvo (%)"));
    await user.type(screen.getByLabelText("Bloqueio alvo (%)"), "abc");
    await user.click(screen.getByRole("button", { name: /Sugerir c/ }));
    expect(await screen.findByText(/Informe λ, μ e o bloqueio alvo/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText("Bloqueio alvo (%)"));
    await user.type(screen.getByLabelText("Bloqueio alvo (%)"), "150");
    await user.click(screen.getByRole("button", { name: /Sugerir c/ }));
    expect(await screen.findByText("target_blocking deve ser menor que 1.")).toBeInTheDocument();
  });

  it("só aparece no Erlang-B", async () => {
    await openLab("mmc", erlangHandler);
    expect(screen.queryByRole("button", { name: /Sugerir c/ })).toBeNull();
  });
});

// ---------- M/G/c no Laboratório ----------

const mgcHandler: FakeHandler = (url) => {
  if (url.endsWith("/compare")) return { body: fx.mgcCompare };
  if (url.endsWith("/simulate")) return { body: fx.mgcSimulate };
  return { body: fx.mgcCalculate };
};

describe("M/G/c", () => {
  it("pede λ, servidores e a distribuição do serviço, e explica a aproximação", async () => {
    await openLab("mgc", mgcHandler);
    expect(screen.getByLabelText(/Chegadas λ/)).toHaveValue("80");
    expect(screen.getByLabelText("Servidores c")).toHaveValue("10");
    expect(screen.getByLabelText("Distribuição do serviço")).toHaveValue("lognormal");
    expect(screen.getByLabelText("CV")).toHaveValue("1.5");
    expect(screen.queryByLabelText(/Serviço μ/)).toBeNull();
    expect(screen.queryByLabelText("Capacidade K")).toBeNull();
    expect(screen.getByRole("note")).toHaveTextContent(/aproximação de Allen–Cunneen/);
  });

  it("calcula, envia o serviço e marca o resultado como aproximação", async () => {
    const { user, fetchMock } = await openLab("mgc", mgcHandler);
    await user.click(screen.getByRole("button", { name: "Só calcular" }));
    expect(await screen.findByText(/Aproximação de Allen–Cunneen: os valores são aproximados/)).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/models/mgc/calculate");
    expect(bodyOf(fetchMock)).toEqual({ lambda: 80, servers: 10, distribution: "lognormal", mean: 0.1, cv: 1.5 });
    expect(screen.getByText("M/G/10", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Use Comparar para ver o erro da aproximação contra a simulação.")).toBeInTheDocument();
  });

  it("não tem a linha de P0 (a aproximação não a define)", async () => {
    const { user } = await openLab("mgc", mgcHandler);
    await user.click(screen.getByRole("button", { name: "Só calcular" }));
    await screen.findByRole("table");
    const heads = within(screen.getByRole("table")).getAllByRole("rowheader").map((h) => h.textContent);
    expect(heads.some((h) => /vazio|P0/.test(h ?? ""))).toBe(false);
    expect(heads.length).toBe(7);
  });

  it("mostra os avisos de faixa de validade vindos da API", async () => {
    const warned = clone(fx.mgcCalculate) as Omit<typeof fx.mgcCalculate, "warnings"> & { warnings: string[] };
    warned.warnings = ["Utilização alta (ρ = 0,950 > 0,9): a aproximação perde precisão."];
    const { user } = await openLab("mgc", () => ({ body: warned }));
    await user.click(screen.getByRole("button", { name: "Só calcular" }));
    expect(await screen.findByText(/Utilização alta \(ρ = 0,950 > 0,9\)/)).toBeInTheDocument();
  });

  it("diz quando a aproximação é exata", async () => {
    const exact = clone(fx.mgcCalculate);
    exact.exact = true;
    const { user } = await openLab("mgc", () => ({ body: exact }));
    await user.click(screen.getByRole("button", { name: "Só calcular" }));
    expect(await screen.findByText(/Aproximação exata neste caso/)).toBeInTheDocument();
    expect(screen.queryByText(/Use Comparar/)).toBeNull();
  });

  it("comparar mostra o erro da aproximação contra a simulação", async () => {
    const { user, fetchMock } = await openLab("mgc", mgcHandler);
    await user.click(screen.getByRole("button", { name: "Comparar" }));
    await screen.findByText(/Aproximação de Allen–Cunneen/);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/models/mgc/compare");
    expect(bodyOf(fetchMock)).toMatchObject({ servers: 10, distribution: "lognormal", seed: 2026 });
    expect(screen.queryByText(/Use Comparar/)).toBeNull();
  });

  it("sistema instável vira mensagem na tela", async () => {
    const { user } = await openLab("mgc", () => ({ status: 422, body: fx.errorMgcUnstable }));
    await user.click(screen.getByRole("button", { name: "Só calcular" }));
    expect(await screen.findByText("Sistema instável")).toBeInTheDocument();
    expect(screen.getAllByText(/ρ = λ·E\[S\]\/c < 1/).length).toBeGreaterThan(0);
  });
});

// ---------- histórico ----------

describe("histórico dos modelos novos", () => {
  it("M/G/c salvo volta com a distribuição, os servidores e a aproximação", () => {
    const params = { lambda: 80, mu: 10, servers: 10, service: { distribution: "lognormal" as const, values: { mean: 0.1, cv: 1.5 } } };
    const result = fromCalculate("mgc", params, fx.mgcCalculate as never);
    expect(result.approximation).toEqual({ exact: false, warnings: [] });
    const saved = labRecord(result);
    const back = parseLabRecord({ ...saved, id: "1", app_version: null, size_bytes: 1, created_at: "", updated_at: "" } as never);
    expect(back?.model).toBe("mgc");
    expect(back?.parameters.service?.values).toEqual({ mean: 0.1, cv: 1.5 });
    expect(back?.result.approximation?.exact).toBe(false);
  });

  it("M/G/c sem a distribuição não pode ser reaberto", () => {
    const params = { lambda: 80, mu: 10, servers: 10 };
    const saved = labRecord(fromCalculate("mgc", params, fx.mgcCalculate as never));
    expect(parseLabRecord({ ...saved, id: "1", app_version: null, size_bytes: 1, created_at: "", updated_at: "" } as never)).toBeNull();
  });

  it("Erlang-B salvo guarda o tráfego oferecido", () => {
    const result = fromCalculate("erlangb", { lambda: 20, mu: 1, servers: 15 }, fx.erlangbCalculate as never);
    expect(result.extras).toEqual({ offered_load: 20, carried_load: expect.closeTo(13.4, 3), lost_rate: expect.closeTo(6.6, 3) });
    const saved = labRecord(result);
    const back = parseLabRecord({ ...saved, id: "1", app_version: null, size_bytes: 1, created_at: "", updated_at: "" } as never);
    expect(back?.model).toBe("erlangb");
    expect(back?.parameters.servers).toBe(15);
  });
});

