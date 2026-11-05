/** Fase 13.2: 2 a 4 fases, classes de veículos, testes de hipótese, CSV da validação e duas sessões lado a lado. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { SessionsComparison, TrafficResult, VideoValidation } from "./api/traffic";
import { TrafficSessionsView, TrafficSimulationView, TrafficValidationView, validationIds } from "./components/TrafficViews";
import { clone, fixtures as fx, FakeRecords, mockFetch, type FakeHandler } from "./test/helpers";

vi.mock("plotly.js-basic-dist-min", () => ({
  default: { react: vi.fn().mockResolvedValue(undefined), purge: vi.fn() },
}));

afterEach(() => vi.unstubAllGlobals());

const happy: FakeHandler = (url) => {
  if (url.endsWith("/api/traffic/simulate")) return { body: fx.trafficSimulate4Phases };
  if (url.endsWith("/video/estimate")) return { body: fx.trafficVideoEstimateClasses };
  if (url.endsWith("/video/validate")) return { body: fx.trafficVideoValidateClasses };
  if (url.endsWith("/video/validate/export.csv")) return { body: null, text: "resumo,aproximacao\n" };
  if (url.endsWith("/video/sessions/compare")) return { body: fx.trafficSessionsCompare };
  if (url.endsWith("/video/sessions/compare/export.csv")) return { body: null, text: "grupo,grandeza\n" };
  return { body: {}, status: 404 };
};

async function open(handler: FakeHandler = happy, mode = "simulate") {
  const fetchMock = mockFetch(handler, new FakeRecords(false));
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Cruzamento" }));
  if (mode) await user.selectOptions(screen.getByLabelText("O que fazer"), mode);
  return { user, fetchMock };
}
const callsTo = (fetchMock: ReturnType<typeof mockFetch>, suffix: string) => fetchMock.mock.calls.filter(([url]) => String(url).endsWith(suffix));
const csv = (name: string) => new File(["a,b\n1,2\n"], name, { type: "text/csv" });

describe("formulário com 2 a 4 fases e classes", () => {
  it("adiciona e remove fases (uma aproximação por fase), entre 2 e 4", async () => {
    const { user } = await open();
    expect(screen.queryByLabelText("Verde da fase 3 (s)")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Remover a última fase/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Adicionar fase/ }));
    expect(screen.getByLabelText("Verde da fase 3 (s)")).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Aproximação 3" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Adicionar fase/ }));
    expect(screen.getByLabelText("Verde da fase 4 (s)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Adicionar fase/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /Remover a última fase/ }));
    expect(screen.queryByLabelText("Verde da fase 4 (s)")).not.toBeInTheDocument();
  });

  it("simula 4 fases com classes: o corpo leva as 4 fases, as classes e o CV de ℓ; o resultado tem as 4 aproximações", async () => {
    const { user, fetchMock } = await open();
    await user.click(screen.getByRole("button", { name: "Carregar exemplo ilustrativo" }));
    await user.click(screen.getByRole("button", { name: /Adicionar fase/ }));
    await user.click(screen.getByRole("button", { name: /Adicionar fase/ }));
    for (const n of [3, 4]) {
      await user.type(screen.getByLabelText(`Verde da fase ${n} (s)`), "15");
      const card = screen.getByRole("group", { name: `Aproximação ${n}` });
      await user.type(within(card).getByLabelText("Chegada (veículos/min)"), "6");
      await user.type(within(card).getByLabelText("Média h (s)"), "2");
      await user.type(within(card).getByLabelText("CV"), "0,3");
    }
    const first = screen.getByRole("group", { name: "Aproximação 1" });
    await user.click(within(first).getByRole("button", { name: "Adicionar classe" }));
    await user.type(within(first).getByLabelText("Classe 1: nome"), "carro");
    await user.type(within(first).getByLabelText("Classe 1: parcela (0 a 1)"), "0,8");
    await user.type(within(first).getByLabelText("Classe 1: fator (carros equivalentes)"), "1");
    await user.click(within(first).getByRole("button", { name: "Adicionar classe" }));
    await user.type(within(first).getByLabelText("Classe 2: nome"), "ônibus");
    await user.type(within(first).getByLabelText("Classe 2: parcela (0 a 1)"), "0,1");
    expect(within(first).getByText(/As parcelas somam 0,9, e devem somar 1/)).toBeInTheDocument();
    await user.type(within(first).getByLabelText("Classe 2: fator (carros equivalentes)"), "2,2");
    await user.clear(within(first).getByLabelText("Classe 2: parcela (0 a 1)"));
    await user.type(within(first).getByLabelText("Classe 2: parcela (0 a 1)"), "0,2");
    expect(within(first).queryByText(/devem somar 1/)).not.toBeInTheDocument();
    await user.type(within(first).getByLabelText("CV de ℓ entre ciclos"), "0,25");

    await user.click(screen.getByRole("button", { name: "Simular" }));
    const result = await screen.findByText("Atraso médio por veículo");
    expect(result).toBeInTheDocument();
    const body = JSON.parse(String(callsTo(fetchMock, "/api/traffic/simulate")[0][1]!.body));
    expect(body.phases).toHaveLength(4);
    expect(body.approaches).toHaveLength(4);
    expect(body.approaches[0].classes).toEqual([{ name: "carro", share: 0.8, factor: 1 }, { name: "ônibus", share: 0.2, factor: 2.2 }]);
    expect(body.approaches[0].first_vehicle_cv).toBeCloseTo(0.25);
    const table = screen.getByRole("table", { name: /Métricas/i });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(expect.arrayContaining(["Cruzamento"]));
  }, 15000);

  it("a resposta com 4 aproximações mostra uma coluna e um cartão para cada uma", () => {
    const r = fx.trafficSimulate4Phases as unknown as TrafficResult;
    render(<TrafficSimulationView result={r} />);
    for (const a of r.approaches) expect(screen.getAllByText(a.name).length).toBeGreaterThan(0);
    expect(r.approaches).toHaveLength(4);
    expect(screen.getAllByRole("columnheader").filter((h) => /^A[1-4]$/.test(h.textContent ?? ""))).toHaveLength(4);
  });
});

describe("vídeo com classes, replay, testes de hipótese e sessões", () => {
  async function openVideo(handler: FakeHandler = happy) {
    const ctx = await open(handler);
    await ctx.user.selectOptions(screen.getByLabelText("O que fazer"), "video");
    return ctx;
  }
  const upload = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.upload(screen.getByLabelText(/Eventos semafóricos/), csv("sinais.csv"));
    await user.upload(screen.getByLabelText(/Contagens por intervalo/), csv("contagens.csv"));
    await user.upload(screen.getByLabelText(/Cruzamentos da linha de retenção/), csv("cruzamentos.csv"));
  };

  it("manda os fatores de equivalência como JSON e mostra a tabela de classes", async () => {
    const { user, fetchMock } = await openVideo();
    await upload(user);
    await user.type(screen.getByLabelText("Aproximações (na ordem das fases)"), "N,L,E");
    await user.type(screen.getByLabelText("Fatores de equivalência em carros"), "carro=1; moto=0,35; ônibus=2,2");
    await user.click(screen.getByRole("button", { name: "Estimar com o vídeo" }));
    expect(await screen.findByRole("heading", { name: "Classes de veículos" })).toBeInTheDocument();
    const form = callsTo(fetchMock, "/video/estimate")[0][1]!.body as FormData;
    expect(JSON.parse(String(form.get("class_factors")))).toEqual({ carro: 1, moto: 0.35, ônibus: 2.2 });
    expect(form.get("approach_ids")).toBe("N,L,E");
    expect(screen.getByRole("table", { name: /Chegadas por classe/ })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Tempo do primeiro veículo/ })).toBeInTheDocument();
  });

  it("fator inválido é recusado antes de chamar a API", async () => {
    const { user, fetchMock } = await openVideo();
    await upload(user);
    await user.type(screen.getByLabelText("Fatores de equivalência em carros"), "moto=0");
    await user.click(screen.getByRole("button", { name: "Estimar com o vídeo" }));
    expect(screen.getByText(/Fator inválido em “moto=0”/)).toBeInTheDocument();
    expect(callsTo(fetchMock, "/video/estimate")).toHaveLength(0);
  });

  it("'Usar reproduzindo as contagens' preenche 3 fases e leva as contagens observadas", async () => {
    const { user } = await openVideo();
    await upload(user);
    await user.type(screen.getByLabelText("Fatores de equivalência em carros"), "carro=1; moto=0,35; ônibus=2,2");
    await user.click(screen.getByRole("button", { name: "Estimar com o vídeo" }));
    await user.click(await screen.findByRole("button", { name: "Usar reproduzindo as contagens" }));
    expect(screen.getByLabelText("O que fazer")).toHaveValue("compare");
    expect(document.getElementById("traffic-green3")).toHaveValue("16");
    expect(screen.getAllByText(/contagens observadas, reproduzidas/)).toHaveLength(3);
    expect(screen.getByRole("group", { name: "Aproximação 3" })).toBeInTheDocument();
    // as classes vindas do vídeo aparecem no formulário
    const first = screen.getByRole("group", { name: "Aproximação 1" });
    expect(within(first).getByLabelText("Classe 2: nome")).toHaveValue("moto");
    expect(within(first).getByLabelText("Classe 2: fator (carros equivalentes)")).toHaveValue("0.35");
  });

  it("valida com tolerâncias, mostra os testes de hipótese e exporta o CSV com a semente da API", async () => {
    const blob = vi.fn().mockReturnValue("blob:x");
    vi.stubGlobal("URL", { ...URL, createObjectURL: blob, revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const { user, fetchMock } = await openVideo();
    await upload(user);
    await user.type(screen.getByLabelText("Fatores de equivalência em carros"), "carro=1; moto=0,35; ônibus=2,2");
    await user.click(screen.getByRole("button", { name: "Estimar com o vídeo" }));
    await user.click(await screen.findByRole("button", { name: "Usar no formulário" }));
    await user.selectOptions(screen.getByLabelText("O que fazer"), "video");
    await user.click(screen.getByText("Tolerâncias do teste de equivalência (validação)"));
    await user.type(screen.getByLabelText("Atraso médio: ± segundos"), "5");
    await user.type(screen.getByLabelText("Total de saídas: ± % do observado"), "5");
    await user.click(screen.getByRole("button", { name: "Validar o modelo com as contagens" }));

    expect(await screen.findByText("Validação: simulado × observado")).toBeInTheDocument();
    const form = callsTo(fetchMock, "/video/validate")[0][1]!.body as FormData;
    expect(form.get("tolerance_delay")).toBe("5");
    expect(form.get("tolerance_departures")).toBe("0.05");
    expect(JSON.parse(String(form.get("class_factors")))).toEqual({ carro: 1, moto: 0.35, ônibus: 2.2 });
    const config = JSON.parse(String(form.get("config")));
    expect(config.phases).toHaveLength(3);
    expect(config.approaches[0].classes[0].name).toBe("carro");
    expect(config.approaches[0].profile).toBeUndefined();
    expect(screen.getAllByRole("table", { name: /Testes de hipótese da validação/ })).toHaveLength(3);
    expect(screen.getAllByText(/Equivalência do total de saídas/).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /Exportar CSV da validação/ }));
    await waitFor(() => expect(callsTo(fetchMock, "/video/validate/export.csv")).toHaveLength(1));
    const exported = callsTo(fetchMock, "/video/validate/export.csv")[0][1]!.body as FormData;
    expect(exported.get("seed")).toBe(String((fx.trafficVideoValidateClasses as unknown as VideoValidation).settings.seed));
    expect(exported.get("tolerance_departures")).toBe("0.05");
  }, 30000);

  it("tolerância inválida é recusada sem chamar a API", async () => {
    const { user, fetchMock } = await openVideo();
    await upload(user);
    await user.click(screen.getByText("Tolerâncias do teste de equivalência (validação)"));
    await user.type(screen.getByLabelText("Atraso médio: ± segundos"), "-2");
    await user.click(screen.getByRole("button", { name: "Validar o modelo com as contagens" }));
    expect(screen.getByText(/tolerância do atraso deve ser um número maior que zero/)).toBeInTheDocument();
    expect(callsTo(fetchMock, "/video/validate")).toHaveLength(0);
  });

  it("guarda duas sessões, compara e exporta o CSV", async () => {
    const blob = vi.fn().mockReturnValue("blob:x");
    vi.stubGlobal("URL", { ...URL, createObjectURL: blob, revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const { user, fetchMock } = await openVideo();
    await upload(user);
    await user.type(screen.getByLabelText("Fatores de equivalência em carros"), "carro=1; moto=0,35; ônibus=2,2");
    await user.click(screen.getByRole("button", { name: "Estimar com o vídeo" }));
    await user.click(await screen.findByRole("button", { name: "Guardar como sessão A" }));
    expect(screen.getByRole("button", { name: "Comparar as sessões" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Guardar como sessão B" }));
    await user.clear(screen.getByLabelText("Nome da sessão A"));
    await user.type(screen.getByLabelText("Nome da sessão A"), "manhã");
    await user.click(screen.getByRole("button", { name: "Comparar as sessões" }));
    expect(await screen.findByRole("table", { name: /Comparação das sessões/ })).toBeInTheDocument();
    const sent = JSON.parse(String(callsTo(fetchMock, "/video/sessions/compare")[0][1]!.body));
    expect(sent.label_a).toBe("manhã");
    expect(sent.a.approach_ids).toEqual(["N", "L", "E"]);
    await user.click(screen.getByRole("button", { name: /Exportar CSV da comparação/ }));
    await waitFor(() => expect(callsTo(fetchMock, "/video/sessions/compare/export.csv")).toHaveLength(1));
  }, 30000);
});

describe("resultados reabertos (as mesmas telas)", () => {
  it("validação com classes: um bloco por aproximação, com a tabela de testes e a decisão de equivalência", () => {
    const result = fx.trafficVideoValidateClasses as unknown as VideoValidation;
    render(<TrafficValidationView result={result} ids={validationIds(result)} />);
    expect(screen.getAllByRole("table", { name: /Testes de hipótese da validação/ })).toHaveLength(3);
    expect(screen.getAllByText("equivalente").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Viés da fila por intervalo/).length).toBe(3);
    expect(screen.getByText(/não há limite de aprovação/i)).toBeInTheDocument();
  });

  it("validação sem testes (antiga) continua abrindo", () => {
    const old = clone(fx.trafficVideoValidate) as unknown as VideoValidation;
    render(<TrafficValidationView result={old} ids={validationIds(old)} />);
    expect(screen.queryByRole("table", { name: /Testes de hipótese/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole("table", { name: /Erros da simulação/ })).toHaveLength(2);
  });

  it("duas sessões: a razão das taxas com IC e o p-valor", () => {
    const data = fx.trafficSessionsCompare as unknown as SessionsComparison;
    render(<TrafficSessionsView data={data} />);
    const table = screen.getByRole("table", { name: /Comparação das sessões manhã e tarde/ });
    expect(within(table).getAllByText("Taxa de chegada").length).toBe(3);
    expect(screen.getByText(/Tabela descritiva/)).toBeInTheDocument();
  });
});
