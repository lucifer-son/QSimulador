import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

const setup = (handler: FakeHandler = happyPath, model: string | null = "mmck") => {
  const fetchMock = mockFetch(handler);
  const user = userEvent.setup();
  render(<App />);
  if (model) fireEvent.change(modelSelect(), { target: { value: model } });
  return { user, fetchMock };
};
const button = (name: string) => screen.getByRole("button", { name });
const lambda = () => screen.getByLabelText(/Chegadas λ/);
const modelSelect = () => screen.getByLabelText("Modelo");

describe("estrutura da página", () => {
  it("tem um título de nível 1 com o nome do produto", () => {
    setup();
    expect(screen.getByRole("heading", { level: 1, name: "QSimulador" })).toBeInTheDocument();
  });
});

describe("formulário", () => {
  it("começa no M/M/1 com os valores de exemplo", () => {
    setup(happyPath, null);
    expect(modelSelect()).toHaveValue("mm1");
    expect(lambda()).toHaveValue("40");
    expect(screen.queryByLabelText("Servidores c")).toBeNull();
    expect(screen.queryByLabelText("Capacidade K")).toBeNull();
    expect(screen.getByLabelText("Semente")).toHaveValue("2026");
    expect(screen.getByText(/800\smil chegadas/)).toBeInTheDocument();
    expect(screen.getByText("Compare o analítico com a simulação")).toBeInTheDocument();
  });

  it("oferece todos os modelos em um único seletor", () => {
    setup();
    expect(within(modelSelect()).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "M/M/1", "M/M/c", "M/M/1/K", "M/M/c/K", "M/G/1", "Erlang-B (perda)", "M/G/c",
    ]);
  });

  it("mostra servidores e capacidade só nos modelos que usam", async () => {
    const { user } = setup();
    await user.selectOptions(modelSelect(), "mm1");
    expect(screen.queryByLabelText("Servidores c")).toBeNull();
    expect(screen.queryByLabelText("Capacidade K")).toBeNull();
    await user.selectOptions(modelSelect(), "mmc");
    expect(screen.getByLabelText("Servidores c")).toBeInTheDocument();
    expect(screen.queryByLabelText("Capacidade K")).toBeNull();
    await user.selectOptions(modelSelect(), "mm1k");
    expect(screen.queryByLabelText("Servidores c")).toBeNull();
    expect(screen.getByLabelText("Capacidade K")).toBeInTheDocument();
  });

  it("cada modelo guarda os próprios valores ao trocar de modelo", async () => {
    const { user } = setup();
    await user.clear(lambda());
    await user.type(lambda(), "30");
    await user.selectOptions(modelSelect(), "mm1");
    expect(lambda()).toHaveValue("40"); // exemplo do M/M/1
    await user.selectOptions(modelSelect(), "mmck");
    expect(lambda()).toHaveValue("30"); // voltou o que foi digitado
  });

  it("os campos de simulação são compartilhados entre os modelos", async () => {
    const { user } = setup();
    await user.clear(screen.getByLabelText("Réplicas"));
    await user.type(screen.getByLabelText("Réplicas"), "7");
    await user.selectOptions(modelSelect(), "mm1");
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
    await user.selectOptions(modelSelect(), "mm1k");
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
    await user.selectOptions(modelSelect(), "mm1");
    expect(lambda()).not.toHaveAttribute("aria-invalid");
  });
});

describe("execução em andamento", () => {
  it("mostra o progresso e permite cancelar, voltando ao estado inicial", async () => {
    mockPendingFetch();
    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions(modelSelect(), "mmck");
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

  it("expõe as cinco abas com Resultados selecionada", async () => {
    await compared();
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Resultados", "Gráficos", "Distribuições", "Réplicas", "Detalhes"]);
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

describe("serviço geral (M/G/1)", () => {
  const mg1Handler: FakeHandler = (url) => {
    if (url.endsWith("/compare")) return { body: fx.mg1Compare };
    if (url.endsWith("/simulate")) return { body: fx.mg1Simulate };
    return { body: fx.mg1Calculate };
  };
  const openMg1 = async (handler: FakeHandler = mg1Handler) => {
    const ctx = setup(handler);
    await ctx.user.selectOptions(modelSelect(), "mg1");
    return ctx;
  };
  const distribution = () => screen.getByLabelText("Distribuição do serviço");

  it("troca μ, servidores e capacidade pela distribuição do serviço", async () => {
    await openMg1();
    expect(modelSelect()).toHaveValue("mg1");
    expect(lambda()).toHaveValue("25");
    expect(distribution()).toHaveValue("lognormal");
    expect(screen.getByLabelText("Tempo médio E[S] (s)")).toHaveValue("0.02");
    expect(screen.getByLabelText("CV")).toHaveValue("0.5");
    expect(screen.queryByLabelText(/Serviço μ/)).toBeNull();
    expect(screen.queryByLabelText("Servidores c")).toBeNull();
    expect(screen.queryByLabelText("Capacidade K")).toBeNull();
    expect(screen.getByLabelText("Resumo do serviço")).toHaveTextContent("E[S] = 0,02 s · desvio = 0,01 s · CV = 0,5 · μ = 50 req/s · ρ = 0,5");
    expect(screen.getByRole("note")).toHaveTextContent(/deixa de ser markoviano/);
  });

  it("os campos mudam conforme a distribuição e o resumo acompanha", async () => {
    const { user } = await openMg1();
    await user.selectOptions(distribution(), "uniform");
    expect(screen.getByLabelText("Mínimo (s)")).toHaveValue("0.01");
    expect(screen.getByLabelText("Máximo (s)")).toHaveValue("0.03");
    expect(screen.queryByLabelText("CV")).toBeNull();
    expect(screen.getByLabelText("Resumo do serviço")).toHaveTextContent("E[S] = 0,02 s");
    await user.selectOptions(distribution(), "erlang");
    expect(screen.getByLabelText("Etapas k")).toHaveValue("4");
    await user.selectOptions(distribution(), "triangular");
    expect(screen.getByLabelText("Moda (s)")).toBeInTheDocument();
    await user.selectOptions(distribution(), "truncated_normal");
    expect(screen.getByLabelText("Desvio da normal (s)")).toBeInTheDocument();
    await user.selectOptions(distribution(), "deterministic");
    expect(screen.getByLabelText("Resumo do serviço")).toHaveTextContent("CV = 0");
    await user.selectOptions(distribution(), "exponential");
    expect(screen.queryByRole("note")).toBeNull();           // exponencial é markoviano: sem aviso
  });

  it("Comparar: chama /api/models/mg1/compare com a distribuição e mostra o resultado", async () => {
    const { user, fetchMock } = await openMg1();
    await user.click(button("Comparar"));
    expect(await screen.findByText(/As 7 métricas do analítico estão dentro do IC de 95%/)).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/models/mg1/compare");
    expect(JSON.parse(String(init!.body))).toEqual({
      lambda: 25, distribution: "lognormal", mean: 0.02, cv: 0.5,
      simulation_time: 2000, replications: 10, warmup_time: 100, seed: 2026,
    });
    expect(screen.getAllByRole("row")).toHaveLength(8);
    await user.click(screen.getByRole("tab", { name: "Detalhes" }));
    const details = within(screen.getByRole("tabpanel"));
    expect(details.getByText("Distribuição do serviço")).toBeInTheDocument();
    expect(details.getByText("Lognormal")).toBeInTheDocument();
    expect(details.getByText("CV do serviço")).toBeInTheDocument();
    expect(details.getByText("Serviço μ = 1/E[S]")).toBeInTheDocument();
    expect(details.queryByText("Servidores c")).toBeNull();
  });

  it("Só calcular não envia campos de simulação", async () => {
    const { user, fetchMock } = await openMg1();
    await user.selectOptions(distribution(), "deterministic");
    await user.click(button("Só calcular"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/models/mg1/calculate");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]!.body))).toEqual({ lambda: 25, distribution: "deterministic", mean: 0.02 });
  });

  it("campo inválido do serviço é marcado antes de chamar a API", async () => {
    const { user, fetchMock } = await openMg1();
    await user.selectOptions(distribution(), "erlang");
    await user.clear(screen.getByLabelText("Etapas k"));
    await user.type(screen.getByLabelText("Etapas k"), "2,5");
    await user.click(button("Comparar"));
    expect(await screen.findByText("Informe um número inteiro.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("erro de domínio da API aparece no campo certo", async () => {
    const { user } = await openMg1(() => ({ status: 422, body: fx.errorMg1InvalidParameter }));
    await user.selectOptions(distribution(), "triangular");
    await user.click(button("Só calcular"));
    const alerts = await screen.findAllByRole("alert");
    expect(alerts.some((a) => /mode deve estar entre min e max/.test(a.textContent ?? ""))).toBe(true);
    expect(screen.getByLabelText("Moda (s)")).toHaveAttribute("aria-invalid", "true");
  });

  it("sistema instável mostra a mensagem da API", async () => {
    const { user } = await openMg1(() => ({ status: 422, body: fx.errorMg1Unstable }));
    await user.click(button("Só calcular"));
    expect(await screen.findByRole("heading", { name: "Sistema instável" })).toBeInTheDocument();
    expect(screen.getAllByText(/ρ = λ·E\[S\] < 1/).length).toBeGreaterThan(0);
  });

  it("M/G/1 guarda os próprios valores ao trocar de modelo", async () => {
    const { user } = await openMg1();
    await user.selectOptions(distribution(), "weibull");
    await user.selectOptions(modelSelect(), "mm1");
    expect(lambda()).toHaveValue("40");
    await user.selectOptions(modelSelect(), "mg1");
    expect(distribution()).toHaveValue("weibull");
  });

  it("a aba Experimentos cobre o M/G/1: oferece comparar distribuições em vez de servidores", async () => {
    const { user } = await openMg1();
    await user.click(screen.getByRole("button", { name: "Experimentos" }));
    expect(await screen.findByRole("tab", { name: "Comparar distribuições" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Comparar servidores" })).toBeNull();
    expect(screen.queryByText(/não cobrem o serviço geral/)).toBeNull();
  });

  it("a aba Experimentos cobre o Erlang-B: varredura, comparar servidores e sensibilidade, sem aviso", async () => {
    const { user } = setup();
    await user.selectOptions(modelSelect(), "erlangb");
    await user.click(screen.getByRole("button", { name: "Experimentos" }));
    expect(await screen.findByRole("tab", { name: "Comparar servidores" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Varredura de parâmetro", "Comparar servidores", "Sensibilidade",
    ]);
    expect(screen.queryByText(/ainda não têm experimentos/)).toBeNull();
  });

  it("a aba Experimentos cobre o M/G/c: compara servidores e também distribuições", async () => {
    const { user } = setup();
    await user.selectOptions(modelSelect(), "mgc");
    await user.click(screen.getByRole("button", { name: "Experimentos" }));
    expect(await screen.findByRole("tab", { name: "Comparar distribuições" })).toBeInTheDocument();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Varredura de parâmetro", "Comparar servidores", "Comparar distribuições", "Sensibilidade",
    ]);
    expect(screen.queryByText(/ainda não têm experimentos/)).toBeNull();
  });
});
