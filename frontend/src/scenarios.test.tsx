import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { clone, fixtures as fx, FakeRecords, mockFetch, mockPendingFetch, type FakeHandler } from "./test/helpers";

vi.mock("plotly.js-basic-dist-min", () => ({
  default: { react: vi.fn().mockResolvedValue(undefined), purge: vi.fn() },
}));

afterEach(() => vi.unstubAllGlobals());

const happy: FakeHandler = (url) => {
  if (url.endsWith("/export.csv")) return { body: null, text: fx.scenariosExportMmc.text };
  return { body: fx.scenariosCompareMmc, ndjson: true };
};

/** Abre Cenários com o Laboratório no M/M/c (λ = 8, μ = 1, c = 10; T = 2000, 10 réplicas, warm-up 100, semente 2026). */
async function open(handler: FakeHandler = happy, records = new FakeRecords(false)) {
  const fetchMock = mockFetch(handler, records);
  const user = userEvent.setup();
  render(<App />);
  await user.selectOptions(screen.getByLabelText("Modelo"), "mmc");
  await user.click(screen.getByRole("button", { name: "Cenários" }));
  return { user, fetchMock, records };
}
const bodyOf = (fetchMock: ReturnType<typeof mockFetch>, call = 0) =>
  JSON.parse(String(fetchMock.mock.calls[call][1]!.body)) as Record<string, unknown>;
const compareCalls = (fetchMock: ReturnType<typeof mockFetch>) =>
  fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/compare"));

/** Cria o terceiro cenário (λ +50%), o mesmo que gerou a fixture. */
async function addOverload(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Adicionar cenário" }));
  const card = screen.getByRole("group", { name: "Cenário 3" });
  await user.type(within(card).getByLabelText("Nome"), "Sobrecarga");
  await user.type(within(card).getByLabelText("λ"), "+50%");
}

describe("aba Cenários", () => {
  it("abre com dois cenários de exemplo e herda a base do Laboratório", async () => {
    await open();
    const form = screen.getByRole("form", { name: "Parâmetros da comparação de cenários" });
    expect(within(form).getByText(/M\/M\/c, com os valores e a simulação do Laboratório/)).toBeInTheDocument();
    const first = within(form).getByRole("group", { name: "Cenário 1" });
    expect(within(first).getByLabelText("Nome")).toHaveValue("+20% de λ");
    expect(within(first).getByLabelText("λ")).toHaveValue("+20%");
    expect(within(form).getByRole("group", { name: "Cenário 2" })).toBeInTheDocument();
    expect(within(form).getByText(/T = 2000 s, 10 réplicas, warm-up 100 s, semente 2026/)).toBeInTheDocument();
    expect(within(form).getByText(/Estimativa: .*chegadas no total \(3 simulações\)/)).toBeInTheDocument();
    expect(screen.getByText("Compare cenários")).toBeInTheDocument();
  });

  it("executa todos: envia a base, os cenários e a simulação do Laboratório e mostra a comparação", async () => {
    const { user, fetchMock } = await open();
    await addOverload(user);
    await user.click(screen.getByRole("button", { name: "Executar todos" }));
    const table = await screen.findByRole("table");

    expect(compareCalls(fetchMock)).toHaveLength(1);
    expect(bodyOf(fetchMock)).toEqual({
      base: { model: "mmc", lambda: 8, mu: 1, servers: 10 },
      scenarios: [
        { name: "+20% de λ", lambda: { mode: "relative", value: 20 } },
        { name: "+1 servidor", servers: { mode: "relative", value: 1 } },
        { name: "Sobrecarga", lambda: { mode: "relative", value: 50 } },
      ],
      bonferroni: false, simulation_time: 2000, replications: 10, warmup_time: 100, seed: 2026,
    });

    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(5);                                  // cabeçalho + base + 3 cenários
    const [, base, pico, servidor, sobrecarga] = rows;
    expect(within(base).getByText(/M\/M\/c · base/)).toBeInTheDocument();
    expect(within(pico).getByText("Aumento significativo ↑")).toBeInTheDocument();
    expect(within(pico).getByText("em risco")).toBeInTheDocument();
    expect(within(pico).getByText(/λ 8 → 9,6/)).toBeInTheDocument();
    expect(within(servidor).getByText("Redução significativa ↓")).toBeInTheDocument();
    expect(within(servidor).getByText(/c 10 → 11/)).toBeInTheDocument();
    expect(sobrecarga).toHaveClass("row-bad");
    expect(within(sobrecarga).getByText("instável")).toBeInTheDocument();
    expect(within(sobrecarga).getAllByText("—", { selector: "td" }).length).toBeGreaterThanOrEqual(4);   // não simulado: sem valores
  });

  it("mostra o aviso 'ICs individuais', a semente e a explicação do inconclusivo", async () => {
    const { user } = await open();
    await user.click(screen.getByRole("button", { name: "Executar todos" }));
    await screen.findByRole("table");
    const note = screen.getByText("ICs individuais.", { exact: false }).closest("[role=note]")!;
    expect(note).toHaveTextContent(/Inconclusivo.*não significa igual/);
    expect(screen.getByText(/Semente 2026 · 10 réplicas · T = 2000 s · warm-up 100 s/)).toBeInTheDocument();
  });

  it("lista os avisos de instável e de risco, e a troca de métrica atualiza a tabela", async () => {
    const { user } = await open();
    await user.click(screen.getByRole("button", { name: "Executar todos" }));
    await screen.findByRole("table");
    const alerts = screen.getByRole("list", { name: "Avisos dos cenários" });
    const items = within(alerts).getAllByRole("listitem");
    expect(items).toHaveLength(2);                                          // em risco (+20% de λ) e instável (Sobrecarga)
    expect(items[0]).toHaveTextContent(/\+20% de λ.*ρ = 0\.96/);
    expect(items[1]).toHaveTextContent(/Sobrecarga.*não foi simulado/);

    await user.selectOptions(screen.getByLabelText("Métrica"), "rho");
    const table = screen.getByRole("table");
    expect(within(table).getByRole("caption", { hidden: true } as never)).toHaveTextContent(/Utilização/);
    expect(within(table).getAllByText(/p\.p\./).length).toBeGreaterThan(0);
  });

  it("o gráfico das diferenças é desenhado com o Plotly", async () => {
    const { user } = await open();
    await user.click(screen.getByRole("button", { name: "Executar todos" }));
    await screen.findByRole("table");
    expect(screen.getByRole("img", { name: /Diferença de Tempo médio de espera contra a base/ })).toBeInTheDocument();
    const Plotly = (await import("plotly.js-basic-dist-min")).default as unknown as { react: ReturnType<typeof vi.fn> };
    await waitFor(() => expect(Plotly.react).toHaveBeenCalled());
    const [, data] = Plotly.react.mock.calls.at(-1)!;
    expect(data[0].error_x.array).toHaveLength(2);                          // um IC por cenário simulado
  });

  it("Bonferroni vai no corpo e o aviso muda", async () => {
    const { user, fetchMock } = await open(() => ({ body: fx.scenariosCompareMmcBonferroni, ndjson: true }));
    await user.click(screen.getByLabelText(/Correção de Bonferroni/));
    await user.click(screen.getByRole("button", { name: "Executar todos" }));
    await screen.findByRole("table");
    expect(bodyOf(fetchMock).bonferroni).toBe(true);
    expect(screen.getByText(/Correção de Bonferroni: cada IC/)).toBeInTheDocument();
    expect(screen.queryByText("ICs individuais.", { exact: false })).not.toBeInTheDocument();
    expect(screen.getByText(/IC das diferenças 97,5%/)).toBeInTheDocument();
  });

  it("validação local: valor mal formado não chama a API", async () => {
    const { user, fetchMock } = await open();
    const card = screen.getByRole("group", { name: "Cenário 1" });
    await user.clear(within(card).getByLabelText("λ"));
    await user.type(within(card).getByLabelText("λ"), "+2");
    await user.click(screen.getByRole("button", { name: "Executar todos" }));
    expect(await within(card).findByText(/Para variar em relação à base use %/)).toBeInTheDocument();
    expect(compareCalls(fetchMock)).toHaveLength(0);
  });

  it("erro 422 da API cai no campo do cenário certo", async () => {
    const { user } = await open(() => ({ status: 422, body: fx.errorScenariosCapacity }));
    const card = screen.getByRole("group", { name: "Cenário 1" });
    await user.selectOptions(within(card).getByLabelText("Modelo"), "mmck");
    await user.click(screen.getByRole("button", { name: "Executar todos" }));
    expect(await within(card).findByText(/capacity é obrigatório/)).toBeInTheDocument();
    expect(screen.getByText("Parâmetro inválido")).toBeInTheDocument();
  });

  it("trocar o modelo do cenário para M/M/c/K mostra o campo K", async () => {
    const { user } = await open();
    const card = screen.getByRole("group", { name: "Cenário 1" });
    expect(within(card).queryByLabelText("K (capacidade)")).not.toBeInTheDocument();
    await user.selectOptions(within(card).getByLabelText("Modelo"), "mmck");
    expect(within(card).getByLabelText("K (capacidade)")).toBeInTheDocument();
  });

  it("adiciona até 10 cenários e remove", async () => {
    const { user } = await open();
    const add = screen.getByRole("button", { name: "Adicionar cenário" });
    for (let i = 0; i < 8; i++) await user.click(add);
    expect(screen.getAllByRole("group", { name: /^Cenário \d+$/ })).toHaveLength(10);
    expect(add).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Remover cenário 10" }));
    expect(add).toBeEnabled();
    expect(screen.getAllByRole("group", { name: /^Cenário \d+$/ })).toHaveLength(9);
  });

  it("cancelar durante a execução volta ao estado inicial", async () => {
    mockPendingFetch();
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Cenários" }));
    await user.click(screen.getByRole("button", { name: "Executar todos" }));
    expect(await screen.findByText("Comparando os cenários…")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(await screen.findByText("Compare cenários")).toBeInTheDocument();
  });

  it("mostra o progresso e as linhas prontas enquanto o resto roda", async () => {
    const partial = fx.scenariosCompareMmc.slice(0, 3);          // start, base e o 1º cenário; o fluxo não termina
    const hanging = (_url: string, init?: RequestInit) => {
      const bytes = new TextEncoder().encode(partial.map((e) => JSON.stringify(e)).join("\n") + "\n");
      const stream = new ReadableStream<Uint8Array>({
        start(controller) { controller.enqueue(bytes); },
        cancel() { /* conexão fechada */ },
      });
      init?.signal?.addEventListener("abort", () => undefined);
      return Promise.resolve(new Response(stream, { status: 200, headers: { "Content-Type": "application/x-ndjson" } }));
    };
    vi.stubGlobal("fetch", vi.fn(hanging));
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Cenários" }));
    await user.click(screen.getByRole("button", { name: "Executar todos" }));
    const bar = await screen.findByRole("progressbar", { name: "Progresso da comparação" });
    expect(bar).toHaveAttribute("aria-valuenow", "2");
    expect(bar).toHaveAttribute("aria-valuemax", "4");
    expect(screen.getByText(/2 de 4 simulações concluídas/)).toBeInTheDocument();
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(3);   // cabeçalho + base + 1 cenário
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeInTheDocument();
  });
});

describe("exportar CSV e histórico", () => {
  it("exporta o CSV refazendo o pedido com a semente usada", async () => {
    const createUrl = vi.fn(() => "blob:csv");
    const revoke = vi.fn();
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: revoke }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const { user, fetchMock } = await open();
    await user.click(screen.getByRole("button", { name: "Executar todos" }));
    await screen.findByRole("table");
    await user.click(screen.getByRole("button", { name: "Exportar CSV" }));
    await waitFor(() => expect(click).toHaveBeenCalled());

    const csvCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/export.csv"))!;
    expect(JSON.parse(String(csvCall[1]!.body))).toMatchObject({ seed: 2026, simulation_time: 2000 });
    expect(createUrl).toHaveBeenCalledTimes(1);
    expect(revoke).toHaveBeenCalledWith("blob:csv");
    click.mockRestore();
  });

  it("salva no histórico como experimento do tipo scenarios e reabre", async () => {
    const records = new FakeRecords(true);
    const { user } = await open(happy, records);
    await user.click(screen.getByRole("button", { name: "Executar todos" }));
    await screen.findByRole("table");
    await user.click(await screen.findByRole("button", { name: "Salvar no histórico" }));
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    await screen.findByText(/Salvo\./);

    const saved = records.store[0];
    expect(saved).toMatchObject({ kind: "experiment", title: "Cenários · M/M/c" });
    expect(saved.params).toMatchObject({ origin: "experiment", experiment: "scenarios", model: "mmc" });
    expect((saved.params.request as Record<string, unknown>).seed).toBe(2026);

    await user.click(screen.getByRole("button", { name: "Histórico" }));
    await user.click(await screen.findByRole("button", { name: "Abrir" }));
    const view = await screen.findByLabelText("Registro aberto");
    expect(within(view).getByRole("table")).toBeInTheDocument();
    expect(screen.getAllByText("Aumento significativo ↑").length).toBeGreaterThan(0);
  });

  it("registro de cenários malformado não derruba o histórico", async () => {
    const records = new FakeRecords(true);
    records.add({ kind: "experiment", title: "Quebrado", params: { origin: "experiment", experiment: "scenarios", model: "mmc" }, result: clone({ x: 1 }) });
    const { user } = await open(happy, records);
    await user.click(screen.getByRole("button", { name: "Histórico" }));
    await user.click(await screen.findByRole("button", { name: "Abrir" }));
    const view = await screen.findByLabelText("Registro aberto");
    expect(within(view).queryByRole("table")).not.toBeInTheDocument();
  });
});
