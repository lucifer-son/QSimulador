import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { fixtures as fx, mockFetch, type FakeHandler } from "../test/helpers";

vi.mock("plotly.js-basic-dist-min", () => ({
  default: { react: vi.fn().mockResolvedValue(undefined), purge: vi.fn() },
}));

afterEach(() => vi.unstubAllGlobals());

const happy: FakeHandler = (url) => {
  if (url.endsWith("/api/sizing/sla")) return { body: fx.sizingSlaMmc };
  if (url.endsWith("/api/sizing/cost")) return { body: fx.sizingCostMmc };
  return { body: fx.sizingTableMmc };
};

/** Abre Dimensionamento com o Laboratório no M/M/c (λ = 8, μ = 1, c = 10). */
async function open(model = "mmc", handler: FakeHandler = happy) {
  const fetchMock = mockFetch(handler);
  const user = userEvent.setup();
  render(<App />);
  await user.selectOptions(screen.getByLabelText("Modelo"), model);
  await user.click(screen.getByRole("button", { name: "Dimensionamento" }));
  return { user, fetchMock };
}
const bodyOf = (fetchMock: ReturnType<typeof mockFetch>, call = 0) =>
  JSON.parse(String(fetchMock.mock.calls[call][1]!.body)) as Record<string, unknown>;

describe("aba Dimensionamento", () => {
  it("abre com o formulário e herda modelo e valores do Laboratório", async () => {
    await open();
    const form = screen.getByRole("form", { name: "Parâmetros do dimensionamento" });
    expect(within(form).getByText(/M\/M\/c, com os valores do Laboratório/)).toBeInTheDocument();
    expect(within(form).getByLabelText("Tempo-limite t (s)")).toHaveValue("20");
    expect(within(form).getByLabelText("Meta P(Wq ≤ t) (%)")).toHaveValue("80");
    expect(screen.getByText("Dimensione o sistema")).toBeInTheDocument();
  });

  it("gera a tabela: chama /api/sizing/table com o sistema, a meta e os custos por segundo", async () => {
    const { user, fetchMock } = await open();
    await user.click(screen.getByRole("button", { name: "Gerar tabela" }));
    const table = await screen.findByRole("table");
    expect(fetchMock.mock.calls[0][0]).toContain("/api/sizing/table");
    const body = bodyOf(fetchMock);
    expect(body).toMatchObject({ model: "mmc", lambda: 8, mu: 1, servers: 10, t: 20, target: 0.8 });
    expect(body.server_cost).toBeCloseTo(35 / 3600, 10);
    expect(within(table).getAllByRole("row").length).toBe(fx.sizingTableMmc.rows.length + 1);
    expect(screen.getByRole("status")).toHaveTextContent(/menor c da tabela que atinge a meta/i);
  });

  it("menor c pela meta: chama /sla e anuncia o resultado, sem enviar custos", async () => {
    const { user, fetchMock } = await open();
    await user.click(screen.getByRole("button", { name: "Menor c pela meta" }));
    expect(await screen.findByText(/Menor c que atinge a meta: /)).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toContain("/api/sizing/sla");
    expect("server_cost" in bodyOf(fetchMock)).toBe(false);
  });

  it("custo mínimo: chama /cost, mostra o c ótimo e o custo na unidade escolhida", async () => {
    const { user, fetchMock } = await open();
    await user.click(screen.getByRole("button", { name: "Custo mínimo" }));
    expect(await screen.findByText(/c ótimo: /)).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toContain("/api/sizing/cost");
    expect(screen.getAllByText(/por hora/).length).toBeGreaterThan(0);
    expect(screen.getByRole("columnheader", { name: "Custo total" })).toBeInTheDocument();
  });

  it("validação local: custo mínimo sem custos não chama a API", async () => {
    const { user, fetchMock } = await open();
    await user.clear(screen.getByLabelText("Servidor hₛ"));
    await user.click(screen.getByRole("button", { name: "Custo mínimo" }));
    expect(await screen.findByText("Informe o custo do servidor.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("Erlang-B: pede o bloqueio alvo (sem t) e o custo da perda", async () => {
    const { user, fetchMock } = await open("erlangb", () => ({ body: fx.sizingSlaErlangb }));
    expect(screen.getByLabelText("Bloqueio máximo B (%)")).toBeInTheDocument();
    expect(screen.queryByLabelText("Tempo-limite t (s)")).toBeNull();
    expect(screen.getByLabelText("Perda h_perda")).toBeInTheDocument();
    expect(screen.queryByLabelText("Espera hₑ")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Menor c pela meta" }));
    expect(await screen.findByText(/Menor c que atinge o bloqueio alvo: 30 servidores/)).toBeInTheDocument();
    expect(bodyOf(fetchMock)).toMatchObject({ model: "erlangb", target_blocking: 0.01 });
  });

  it("M/M/1: avisa que dimensiona pelo M/M/c com c = 1", async () => {
    await open("mm1");
    expect(screen.getByText(/O M\/M\/1 não tem c para dimensionar/)).toBeInTheDocument();
  });

  it("M/G/c: mostra o aviso de aproximação vindo da API", async () => {
    const { user } = await open("mgc", () => ({ body: fx.sizingTableMgc }));
    await user.click(screen.getByRole("button", { name: "Gerar tabela" }));
    expect(await screen.findByText(/cauda exponencial/)).toBeInTheDocument();
  });

  it("erro da API aparece no painel de resultados", async () => {
    const { user } = await open("mmc", () => ({
      status: 422, body: { code: "invalid_parameter", message: "t inválido.", fields: [{ field: "t", message: "t inválido." }] },
    }));
    await user.click(screen.getByRole("button", { name: "Gerar tabela" }));
    expect(await screen.findByText("t inválido.", { selector: "p" })).toBeInTheDocument();
  });
});
