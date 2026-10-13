import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { fixtures as fx, mockFetch, mockPendingFetch, type FakeHandler } from "./test/helpers";

vi.mock("plotly.js-basic-dist-min", () => ({
  default: { react: vi.fn().mockResolvedValue(undefined), purge: vi.fn() },
}));

afterEach(() => vi.unstubAllGlobals());

/** API de mentira: devolve a fixture da ação pedida, ou o que o teste sobrescrever. */
const happyPath: FakeHandler = (url) => {
  if (url.endsWith("/compare")) return { body: fx.mmckCompare };
  if (url.endsWith("/simulate")) return { body: fx.mmckSimulate };
  return { body: fx.mmckCalculate };
};

const setup = (handler: FakeHandler = happyPath) => {
  const fetchMock = mockFetch(handler);
  const user = userEvent.setup();
  render(<App />);
  return { user, fetchMock };
};
const button = (name: string) => screen.getByRole("button", { name });
const lambda = () => screen.getByLabelText(/Chegadas λ/);

describe("estrutura da página", () => {
  it("tem um título de nível 1 com o nome do produto", () => {
    setup();
    expect(screen.getByRole("heading", { level: 1, name: "QSimulador" })).toBeInTheDocument();
  });
});

describe("formulário", () => {
  it("começa no M/M/c/K com os exemplos da documentação e a estimativa de custo", () => {
    setup();
    expect(button("M/M/c/K")).toHaveAttribute("aria-pressed", "true");
    expect(lambda()).toHaveValue("25");
    expect(screen.getByLabelText("Servidores c")).toHaveValue("3");
    expect(screen.getByLabelText("Capacidade K")).toHaveValue("6");
    expect(screen.getByLabelText("Semente")).toHaveValue("2026");
    expect(screen.getByText(/500\smil chegadas, cerca de 6 s/)).toBeInTheDocument();
    expect(screen.getByText("Compare o analítico com a simulação")).toBeInTheDocument();
  });

  it("mostra servidores e capacidade só nos modelos que usam", async () => {
    const { user } = setup();
    await user.click(button("M/M/1"));
    expect(screen.queryByLabelText("Servidores c")).toBeNull();
    expect(screen.queryByLabelText("Capacidade K")).toBeNull();
    await user.click(button("M/M/c"));
    expect(screen.getByLabelText("Servidores c")).toBeInTheDocument();
    expect(screen.queryByLabelText("Capacidade K")).toBeNull();
    await user.click(button("M/M/1/K"));
    expect(screen.queryByLabelText("Servidores c")).toBeNull();
    expect(screen.getByLabelText("Capacidade K")).toBeInTheDocument();
  });

  it("cada modelo guarda os próprios valores ao trocar de modelo", async () => {
    const { user } = setup();
    await user.clear(lambda());
    await user.type(lambda(), "30");
    await user.click(button("M/M/1"));
    expect(lambda()).toHaveValue("40"); // exemplo do M/M/1
    await user.click(button("M/M/c/K"));
    expect(lambda()).toHaveValue("30"); // voltou o que foi digitado
  });

  it("os campos de simulação são compartilhados entre os modelos", async () => {
    const { user } = setup();
    await user.clear(screen.getByLabelText("Réplicas"));
    await user.type(screen.getByLabelText("Réplicas"), "7");
    await user.click(button("M/M/1"));
    expect(screen.getByLabelText("Réplicas")).toHaveValue("7");
  });

  it("atualiza a estimativa conforme os campos mudam", async () => {
    const { user } = setup();
    await user.clear(screen.getByLabelText("Tempo (s)"));
    await user.type(screen.getByLabelText("Tempo (s)"), "20000");
    expect(screen.getByText(/5\smi chegadas, cerca de 1 min/)).toBeInTheDocument();
  });

  it("Enter no formulário executa a comparação", async () => {
    const { user, fetchMock } = setup();
    await user.type(lambda(), "{Enter}");
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/models/mmck/compare");
  });
});

describe("ações", () => {
  it("Comparar: chama /compare com os parâmetros e mostra veredito, destaques, gráfico e tabela", async () => {
    const { user, fetchMock } = setup();
    await user.click(button("Comparar"));
    expect(await screen.findByText("As 9 métricas do analítico estão dentro do IC de 95%.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/models/mmck/compare");
    expect(JSON.parse(String(init!.body))).toEqual({
      lambda: 25, mu: 10, servers: 3, capacity: 6,
      simulation_time: 2000, replications: 10, warmup_time: 100, seed: 2026,
    });
    expect(screen.getByLabelText("Destaques")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Diferença percentual/ })).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(10);
  });

  it("o P0 aparece na tabela e entre as métricas do gráfico por réplica", async () => {
    const { user } = setup();
    await user.click(button("Comparar"));
    expect(await screen.findByRole("rowheader", { name: "Probabilidade de sistema vazio (P0)" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Gráficos" }));
    await user.click(button("Carregar réplicas"));
    const select = await screen.findByLabelText("Métrica");
    expect(within(select).getByRole("option", { name: /Probabilidade de sistema vazio/ })).toBeInTheDocument();
    await user.selectOptions(select, "p0");
    expect(screen.getByRole("img", { name: /Valor de Probabilidade de sistema vazio \(P0\) em cada réplica/ })).toBeInTheDocument();
  });

  it("Só calcular: chama /calculate sem campos de simulação", async () => {
    const { user, fetchMock } = setup();
    await user.click(button("Só calcular"));
    expect(await screen.findByText("Métricas analíticas em regime estacionário.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/models/mmck/calculate");
    expect(JSON.parse(String(init!.body))).toEqual({ lambda: 25, mu: 10, servers: 3, capacity: 6 });
    expect(screen.getByRole("columnheader", { name: "Valor" })).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Diferença percentual/ })).toBeNull();
  });

  it("Só simular: chama /simulate e mostra o desvio padrão", async () => {
    const { user, fetchMock } = setup();
    await user.click(button("Só simular"));
    expect(await screen.findByText("Simulação concluída: 5 réplicas de 300 s.")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/models/mmck/simulate");
    expect(screen.getByRole("columnheader", { name: "Desvio padrão" })).toBeInTheDocument();
  });

  it("usa a rota do modelo escolhido", async () => {
    const { user, fetchMock } = setup();
    await user.click(button("M/M/1/K"));
    await user.click(button("Só calcular"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/models/mm1k/calculate");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]!.body))).toEqual({ lambda: 12, mu: 10, capacity: 5 });
  });

  it("semente em branco não é enviada (a API sorteia)", async () => {
    const { user, fetchMock } = setup();
    await user.clear(screen.getByLabelText("Semente"));
    await user.click(button("Comparar"));
    await screen.findByText(/As 9 métricas/);
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]!.body))).not.toHaveProperty("seed");
  });
});

describe("erros", () => {
  it("formato inválido é recusado na tela, sem chamar a API", async () => {
    const { user, fetchMock } = setup();
    await user.clear(lambda());
    await user.type(lambda(), "abc");
    await user.click(button("Comparar"));
    expect(await screen.findByText("Informe um número.")).toBeInTheDocument();
    expect(lambda()).toHaveAttribute("aria-invalid", "true");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("o erro some do campo quando o usuário o edita", async () => {
    const { user } = setup();
    await user.clear(lambda());
    await user.type(lambda(), "abc");
    await user.click(button("Comparar"));
    await screen.findByText("Informe um número.");
    await user.clear(lambda());
    await user.type(lambda(), "2");
    expect(screen.queryByText("Informe um número.")).toBeNull();
  });

  it("sistema instável: mostra a mensagem da API no painel e no campo λ", async () => {
    const { user } = setup(() => ({ status: 422, body: fx.errorUnstable }));
    await user.click(button("Comparar"));
    expect(await screen.findByText("Sistema instável")).toBeInTheDocument();
    expect(screen.getAllByText(fx.errorUnstable.message)).toHaveLength(2); // painel + campo
    expect(lambda()).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/Com capacidade finita \(K\), o sistema é sempre estável/)).toBeInTheDocument();
  });

  it("parâmetro inválido: o erro aparece no campo indicado pela mensagem", async () => {
    const { user } = setup(() => ({ status: 422, body: fx.errorInvalidParameter }));
    await user.click(button("Comparar"));
    await screen.findByText("Parâmetro inválido");
    expect(screen.getByLabelText("Capacidade K")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Servidores c")).not.toHaveAttribute("aria-invalid");
  });

  it("requisição inválida: destaca os campos listados pela API", async () => {
    const { user } = setup(() => ({ status: 422, body: fx.errorInvalidRequest }));
    await user.click(button("Comparar"));
    await screen.findByText("Requisição inválida");
    expect(lambda()).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Servidores c")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Corrija os campos destacados à esquerda.")).toBeInTheDocument();
  });

  it("menos de 2 réplicas: o erro da API aparece no campo Réplicas", async () => {
    const { user, fetchMock } = setup(() => ({ status: 422, body: fx.errorReplications }));
    await user.clear(screen.getByLabelText("Réplicas"));
    await user.type(screen.getByLabelText("Réplicas"), "1");
    await user.click(button("Comparar"));
    await screen.findByText("Parâmetro inválido");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]!.body)).replications).toBe(1);
    expect(screen.getByLabelText("Réplicas")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getAllByText(fx.errorReplications.message)).toHaveLength(2); // painel + campo
    expect(screen.getByLabelText("Servidores c")).not.toHaveAttribute("aria-invalid");
  });

  it("o campo Réplicas informa o intervalo permitido", () => {
    setup();
    expect(screen.getByText("De 2 a 100")).toBeInTheDocument();
  });

  it("API fora do ar: mensagem de conexão", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const user = userEvent.setup();
    render(<App />);
    await user.click(button("Comparar"));
    expect(await screen.findByText("Sem conexão com a API")).toBeInTheDocument();
  });

  it("limpa o erro ao trocar de modelo", async () => {
    const { user } = setup(() => ({ status: 422, body: fx.errorUnstable }));
    await user.click(button("Comparar"));
    await screen.findByText("Sistema instável");
    await user.click(button("M/M/1"));
    expect(lambda()).not.toHaveAttribute("aria-invalid");
  });
});

describe("execução em andamento", () => {
  it("mostra o progresso e permite cancelar, voltando ao estado inicial", async () => {
    mockPendingFetch();
    const user = userEvent.setup();
    render(<App />);
    await user.click(button("Comparar"));
    const status = await screen.findByRole("status");
    expect(within(status).getByText("Comparando…")).toBeInTheDocument();
    expect(status).toHaveTextContent(/0 s \(500\smil chegadas, cerca de 6 s\)/);
    await user.click(button("Cancelar"));
    expect(await screen.findByText("Compare o analítico com a simulação")).toBeInTheDocument();
    expect(button("Comparar")).toBeInTheDocument(); // o botão voltou
  });
});

describe("abas", () => {
  const compared = async () => {
    const ctx = setup();
    await ctx.user.click(button("Comparar"));
    await screen.findByText(/As 9 métricas/);
    return ctx;
  };

  it("expõe as quatro abas com Resultados selecionada", async () => {
    await compared();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Resultados", "Gráficos", "Réplicas", "Detalhes"]);
    expect(screen.getByRole("tab", { name: "Resultados" })).toHaveAttribute("aria-selected", "true");
  });

  it("Réplicas: o /compare não traz as réplicas, então carrega repetindo a simulação com a mesma semente", async () => {
    const { user, fetchMock } = await compared();
    await user.click(screen.getByRole("tab", { name: "Réplicas" }));
    expect(screen.getByText(/A comparação não traz as réplicas individuais/)).toBeInTheDocument();
    await user.click(button("Carregar réplicas"));
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(1 + 5));
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/models/mmck/simulate");
    expect(JSON.parse(String(init!.body)).seed).toBe(2026);
  });

  it("Gráficos: depois de carregar as réplicas, permite escolher a métrica", async () => {
    const { user } = await compared();
    await user.click(screen.getByRole("tab", { name: "Gráficos" }));
    await user.click(button("Carregar réplicas"));
    const select = await screen.findByLabelText("Métrica");
    expect(within(select).getAllByRole("option")).toHaveLength(9);
    await user.selectOptions(select, "L");
    expect(screen.getByRole("img", { name: /Valor de Nº médio no sistema \(L\) em cada réplica/ })).toBeInTheDocument();
  });

  it("erro ao carregar as réplicas mostra aviso e permite tentar de novo", async () => {
    let fail = true;
    const { user } = setup((url) => {
      if (url.endsWith("/compare")) return { body: fx.mmckCompare };
      return fail ? { status: 500, body: {} } : { body: fx.mmckSimulate };
    });
    await user.click(button("Comparar"));
    await screen.findByText(/As 9 métricas/);
    await user.click(screen.getByRole("tab", { name: "Réplicas" }));
    await user.click(button("Carregar réplicas"));
    expect(await screen.findByText("Não foi possível carregar as réplicas. Tente de novo.")).toBeInTheDocument();
    fail = false;
    await user.click(button("Carregar réplicas"));
    await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(6));
  });

  it("Gráficos e Réplicas pedem uma simulação quando só se calculou", async () => {
    const { user } = setup();
    await user.click(button("Só calcular"));
    await screen.findByText("Métricas analíticas em regime estacionário.");
    await user.click(screen.getByRole("tab", { name: "Gráficos" }));
    expect(screen.getByText("Disponível depois de Comparar ou Só simular.")).toBeInTheDocument();
  });

  it("Só simular já traz as réplicas (sem botão de carregar)", async () => {
    const { user } = setup();
    await user.click(button("Só simular"));
    await screen.findByText(/Simulação concluída/);
    await user.click(screen.getByRole("tab", { name: "Réplicas" }));
    expect(screen.queryByRole("button", { name: "Carregar réplicas" })).toBeNull();
    expect(screen.getAllByRole("row")).toHaveLength(6);
  });

  it("Detalhes: parâmetros usados, semente e resposta completa da API", async () => {
    const { user } = await compared();
    await user.click(screen.getByRole("tab", { name: "Detalhes" }));
    // "Semente" e "Capacidade K" também são rótulos do formulário: procura o termo da lista (<dt>).
    const term = (text: string) => screen.getAllByText(text).find((e) => e.tagName === "DT")!;
    expect(screen.getByText("M/M/3/6")).toBeInTheDocument();
    expect(term("Semente").nextElementSibling).toHaveTextContent("2026");
    expect(term("Capacidade K").nextElementSibling).toHaveTextContent("6");
    expect(term("Servidores c").nextElementSibling).toHaveTextContent("3");
    expect(screen.getByText("Resposta completa da API")).toBeInTheDocument();
  });

  it("uma nova execução volta para a aba Resultados", async () => {
    const { user } = await compared();
    await user.click(screen.getByRole("tab", { name: "Detalhes" }));
    expect(screen.getByRole("tab", { name: "Detalhes" })).toHaveAttribute("aria-selected", "true");
    await user.click(button("Comparar"));
    expect(await screen.findByText(/As 9 métricas/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Resultados" })).toHaveAttribute("aria-selected", "true");
  });
});
