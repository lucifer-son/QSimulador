import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { fixtures as fx, mockFetch, type FakeHandler } from "./test/helpers";

vi.mock("plotly.js-basic-dist-min", () => ({
  default: { react: vi.fn().mockResolvedValue(undefined), purge: vi.fn() },
}));

afterEach(() => vi.unstubAllGlobals());

const happy: FakeHandler = (url) => {
  if (url.endsWith("/sweep")) return { body: fx.experimentSweepMm1 };
  if (url.endsWith("/servers")) return { body: fx.experimentServersMmc };
  return { body: fx.experimentSensitivityMm1 };
};

/** Abre a aba Experimentos com o Laboratório no M/M/1 (λ = 40, μ = 50). */
async function open(handler: FakeHandler = happy) {
  const fetchMock = mockFetch(handler);
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "M/M/1" }));
  await user.click(screen.getByRole("button", { name: "Experimentos" }));
  return { user, fetchMock };
}
const bodyOf = (fetchMock: ReturnType<typeof mockFetch>, call = 0) =>
  JSON.parse(String(fetchMock.mock.calls[call][1]!.body)) as Record<string, unknown>;
const mode = (name: string) => screen.getByRole("tab", { name });

describe("navegação", () => {
  it("Experimentos mostra os três tipos e esconde o Laboratório", async () => {
    await open();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Varredura de parâmetro", "Comparar servidores", "Sensibilidade",
    ]);
    expect(mode("Varredura de parâmetro")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("button", { name: "Experimentos" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("form", { name: "Parâmetros do modelo" })).toBeNull();   // Laboratório oculto
  });

  it("mostra os parâmetros fixos vindos do Laboratório, sem o que é varrido", async () => {
    await open();
    const fixed = screen.getByRole("form", { name: "Parâmetros da varredura" });
    expect(within(fixed).getByText("μ").nextSibling).toHaveTextContent("50");
    expect(within(fixed).queryByText("λ")).toBeNull();
  });

  it("só oferece como parâmetro varrido o que o modelo tem", async () => {
    await open();
    const select = screen.getByLabelText("Parâmetro varrido");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Chegadas λ", "Serviço μ"]);
  });
});

describe("varredura", () => {
  it("sugere a faixa pelo sistema do Laboratório e chama /sweep", async () => {
    const { user, fetchMock } = await open();
    expect(screen.getByLabelText("Início")).toHaveValue("5");
    expect(screen.getByLabelText("Fim")).toHaveValue("60");
    await user.click(screen.getByRole("button", { name: "Gerar curva" }));
    await screen.findByRole("table");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/experiments/sweep");
    expect(bodyOf(fetchMock)).toEqual({ model: "mm1", variable: "lambda", mu: 50, start: 5, end: 60, step: 5 });
  });

  it("mostra a curva, a tabela com todas as métricas e o aviso do trecho instável", async () => {
    const { user } = await open();
    await user.click(screen.getByRole("button", { name: "Gerar curva" }));
    expect(await screen.findByText(/2 de 6 pontos fora do regime estável/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Tempo médio no sistema (W) em função de Chegadas λ" })).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(7);            // cabeçalho + 6 pontos
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent))
      .toEqual(["Chegadas λ", "λ/(c·μ)", "Situação", "ρ", "L", "Lq", "W", "Wq", "P0", "Vazão"]);
    expect(within(table).getAllByText("instável")).toHaveLength(2);
    expect(within(table).getAllByText("estável")).toHaveLength(4);
  });

  it("trocar a variável sugere outra faixa e muda o que é enviado", async () => {
    const { user, fetchMock } = await open();
    await user.selectOptions(screen.getByLabelText("Parâmetro varrido"), "mu");
    expect(screen.getByLabelText("Início")).toHaveValue("20");   // metade de λ = 40
    await user.click(screen.getByRole("button", { name: "Gerar curva" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(bodyOf(fetchMock)).toMatchObject({ variable: "mu", lambda: 40, start: 20, end: 80, step: 4 });
  });

  it("com simulação, envia os campos de simulação do Laboratório", async () => {
    const { user, fetchMock } = await open();
    await user.click(screen.getByLabelText("Simular também cada ponto"));
    await user.click(screen.getByRole("button", { name: "Gerar curva" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(bodyOf(fetchMock)).toMatchObject({
      simulate: true, simulation_time: 2000, replications: 10, warmup_time: 100, seed: 2026,
    });
  });

  it("formato inválido é recusado na tela, sem chamar a API", async () => {
    const { user, fetchMock } = await open();
    await user.clear(screen.getByLabelText("Início"));
    await user.type(screen.getByLabelText("Início"), "abc");
    await user.click(screen.getByRole("button", { name: "Gerar curva" }));
    expect(await screen.findByText("Informe um número.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("erro da API aparece no painel e no campo indicado", async () => {
    const { user } = await open(() => ({
      status: 422,
      body: {
        code: "invalid_parameter", message: "step deve ser maior que zero.",
        fields: [{ field: "step", message: "step deve ser maior que zero." }],
      },
    }));
    await user.click(screen.getByRole("button", { name: "Gerar curva" }));
    expect(await screen.findByRole("heading", { name: "Parâmetro inválido" })).toBeInTheDocument();
    expect(screen.getAllByText("step deve ser maior que zero.")).toHaveLength(2);   // painel + campo Passo
    expect(screen.getByLabelText("Passo")).toHaveAttribute("aria-invalid", "true");
  });

  it("o resultado sobrevive à troca entre Laboratório e Experimentos", async () => {
    const { user } = await open();
    await user.click(screen.getByRole("button", { name: "Gerar curva" }));
    await screen.findByRole("table");
    await user.click(screen.getByRole("button", { name: "Laboratório" }));
    expect(screen.queryByRole("table")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Experimentos" }));
    expect(screen.getByRole("table")).toBeInTheDocument();
  });
});

describe("comparação de servidores", () => {
  it("sugere o c do Laboratório e vizinhos e chama /servers", async () => {
    const { user, fetchMock } = await open();
    await user.click(mode("Comparar servidores"));
    expect(screen.getByLabelText("Servidores a comparar")).toHaveValue("1, 2");
    await user.click(screen.getByRole("button", { name: "Comparar servidores" }));
    await screen.findByText("c = 1: instável a partir de λ = 10 req/s.");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/experiments/servers");
    expect(bodyOf(fetchMock)).toEqual({ servers_list: [1, 2], mu: 50, start: 10, end: 120, step: 10 });
  });

  it("mostra uma coluna por número de servidores", async () => {
    const { user } = await open();
    await user.click(mode("Comparar servidores"));
    await user.click(screen.getByRole("button", { name: "Comparar servidores" }));
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent))
      .toEqual(["λ (req/s)", "c = 1", "c = 2", "c = 3"]);
    expect(screen.getByRole("img", { name: /por número de servidores/ })).toBeInTheDocument();
  });

  it("lista inválida é recusada na tela", async () => {
    const { user, fetchMock } = await open();
    await user.click(mode("Comparar servidores"));
    await user.clear(screen.getByLabelText("Servidores a comparar"));
    await user.type(screen.getByLabelText("Servidores a comparar"), "um");
    await user.click(screen.getByRole("button", { name: "Comparar servidores" }));
    expect(await screen.findByText("Informe números inteiros separados por vírgula.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("sensibilidade", () => {
  it("chama /sensitivity com o sistema do Laboratório e a perturbação", async () => {
    const { user, fetchMock } = await open();
    await user.click(mode("Sensibilidade"));
    await user.click(screen.getByRole("button", { name: "Analisar sensibilidade" }));
    await screen.findByRole("table");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/experiments/sensitivity");
    expect(bodyOf(fetchMock)).toEqual({ model: "mm1", lambda: 40, mu: 50, delta_pct: 10 });
  });

  it("mostra o gráfico, o ponto base e sinaliza o lado que fica instável", async () => {
    const { user } = await open();
    await user.click(mode("Sensibilidade"));
    await user.click(screen.getByRole("button", { name: "Analisar sensibilidade" }));
    const table = await screen.findByRole("table");
    expect(screen.getByRole("img", { name: /Sensibilidade de Tempo médio no sistema/ })).toBeInTheDocument();
    expect(screen.getByText(/±25%/)).toBeInTheDocument();
    const lambdaRow = within(table).getByRole("row", { name: /Chegadas λ/ });
    expect(within(lambdaRow).getByText("instável")).toBeInTheDocument();      // λ + 25% passa de μ
    expect(within(table).getAllByRole("row")).toHaveLength(3);                // cabeçalho + λ + μ
  });

  it("perturbação inválida é recusada na tela", async () => {
    const { user, fetchMock } = await open();
    await user.click(mode("Sensibilidade"));
    await user.clear(screen.getByLabelText("Variação de λ e μ (%)"));
    await user.type(screen.getByLabelText("Variação de λ e μ (%)"), "dez");
    await user.click(screen.getByRole("button", { name: "Analisar sensibilidade" }));
    expect(await screen.findByText("Informe um número.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
