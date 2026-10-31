import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { CompareResult, SweepResult, TrafficResult, VideoValidation } from "./api/traffic";
import { TrafficCompareView, TrafficSimulationView, TrafficSweepView, TrafficValidationView } from "./components/TrafficViews";
import { clone, fixtures as fx, FakeRecords, mockFetch, type FakeHandler } from "./test/helpers";

vi.mock("plotly.js-basic-dist-min", () => ({
  default: { react: vi.fn().mockResolvedValue(undefined), purge: vi.fn() },
}));

afterEach(() => vi.unstubAllGlobals());

type Event = { type: string; result?: unknown };
const doneOf = <R,>(events: unknown) => (events as Event[]).find((e) => e.type === "done")!.result as R;

const happy: FakeHandler = (url) => {
  if (url.endsWith("/api/traffic/simulate")) return { body: fx.trafficSimulate };
  if (url.endsWith("/api/traffic/compare")) return { body: fx.trafficCompare, ndjson: true };
  if (url.endsWith("/api/traffic/sweep")) return { body: fx.trafficSweep, ndjson: true };
  if (url.endsWith("/sweep/export.csv")) return { body: null, text: fx.trafficExportSweep.text };
  if (url.endsWith("/video/estimate")) return { body: fx.trafficVideoEstimate };
  if (url.endsWith("/video/validate")) return { body: fx.trafficVideoValidate };
  return { body: {}, status: 404 };
};

async function open(handler: FakeHandler = happy, records = new FakeRecords(false), mode = "simulate") {
  const fetchMock = mockFetch(handler, records);
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Cruzamento" }));
  if (mode) await user.selectOptions(screen.getByLabelText("O que fazer"), mode);
  return { user, fetchMock, records };
}
const bodyOf = (fetchMock: ReturnType<typeof mockFetch>, suffix: string) => {
  const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith(suffix));
  return call ? (JSON.parse(String(call[1]!.body)) as Record<string, any>) : null;
};
const callsTo = (fetchMock: ReturnType<typeof mockFetch>, suffix: string) =>
  fetchMock.mock.calls.filter(([url]) => String(url).endsWith(suffix));

describe("aba Cruzamento", () => {
  it("abre vazia, sem valores medidos preenchidos, e avisa que o exemplo é hipotético", async () => {
    const { user } = await open(happy, new FakeRecords(false), "");
    expect(screen.getByLabelText("O que fazer")).toHaveValue("");
    expect(screen.getByRole("option", { name: "Escolha uma opção" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Escolha uma opção" })).toBeInTheDocument();
    expect(screen.getByText(/Simular:/)).toBeInTheDocument();
    expect(screen.getByText(/Comparar planos:/)).toBeInTheDocument();
    expect(screen.getByText(/Varrer o verde:/)).toBeInTheDocument();
    expect(screen.getByText(/Dados do vídeo:/)).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("O que fazer"), "simulate");
    expect(screen.getByText("Simule o cruzamento")).toBeInTheDocument();
    expect(screen.getByLabelText("Verde da fase 1 (s)")).toHaveValue("");
    expect(screen.getByLabelText("Média h (s)", { selector: "#traffic-a1-hm" })).toHaveValue("");
    expect(screen.getByText(/não são medições de nenhum cruzamento/)).toBeInTheDocument();
  });

  it("sem os dados obrigatórios, não chama a API e marca os campos", async () => {
    const { user, fetchMock } = await open();
    await user.click(screen.getByRole("button", { name: "Simular" }));
    expect(callsTo(fetchMock, "/api/traffic/simulate")).toHaveLength(0);
    expect(screen.getByText("Informe o verde da fase 1.")).toBeInTheDocument();
    expect(screen.getAllByText(/Informe o intervalo médio entre veículos/)).toHaveLength(2);
  });

  it("simula o exemplo: envia veículos/s, mostra resumo, métricas com IC e a conferência de Webster", async () => {
    const { user, fetchMock } = await open();
    await user.click(screen.getByRole("button", { name: "Carregar exemplo ilustrativo" }));
    await user.click(screen.getByRole("button", { name: "Simular" }));
    expect(await screen.findByText("Atraso médio por veículo")).toBeInTheDocument();

    const sent = bodyOf(fetchMock, "/api/traffic/simulate")!;
    expect(sent.approaches[0].lambda).toBeCloseTo(0.2, 10);
    expect(sent.approaches[0].headway).toEqual({ distribution: "lognormal", mean: 2, cv: 0.3 });
    expect(sent.phases[1]).toEqual({ green: 25, amber: 3, all_red: 2 });
    expect(sent.simulation_time).toBe(3600);
    expect(sent.seed).toBe(2026);

    const table = screen.getByRole("table", { name: /Métricas simuladas do cruzamento/ });
    expect(within(table).getByText(/Atraso médio \(com pendentes\)/)).toBeInTheDocument();
    expect(within(table).getAllByRole("row").length).toBeGreaterThan(7);
    expect(screen.getByRole("table", { name: /aproximação analítica/ })).toBeInTheDocument();
    expect(screen.getByText(/Conferência com a fórmula de Webster \(aproximação\)/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Tamanho médio da fila/ })).toBeInTheDocument();
  });

  it("um erro 422 da API cai no campo certo, com a mensagem do servidor", async () => {
    const { user } = await open((url) => (url.endsWith("/simulate") ? { body: fx.errorTrafficHeadway, status: 422 } : { body: {}, status: 404 }));
    await user.click(screen.getByRole("button", { name: "Carregar exemplo ilustrativo" }));
    await user.click(screen.getByRole("button", { name: "Simular" }));
    expect(await screen.findByRole("heading", { name: "Parâmetro inválido" }).catch(() => screen.findByText(/Corrija os campos destacados/))).toBeInTheDocument();
    const message = fx.errorTrafficHeadway.fields[0].message;
    await waitFor(() => expect(screen.getAllByText(message).length).toBeGreaterThan(0));
  });

  it("mostra os avisos de parâmetros não informados vindos da API", async () => {
    const withAlerts = clone(fx.trafficSimulate) as unknown as TrafficResult;
    withAlerts.alerts = [{ code: "not_informed", level: "warning", approach: "a1", field: "first_vehicle_time", message: "Aproximação 1: tempo até o 1º veículo cruzar (assumido 0 s) não foi informado." }];
    withAlerts.approaches[0].not_informed = ["first_vehicle_time"];
    const { user } = await open((url) => (url.endsWith("/simulate") ? { body: withAlerts } : { body: {}, status: 404 }));
    await user.click(screen.getByRole("button", { name: "Carregar exemplo ilustrativo" }));
    await user.click(screen.getByRole("button", { name: "Simular" }));
    const list = await screen.findByRole("list", { name: "Avisos" });
    expect(within(list).getByText(/não foi informado/)).toBeInTheDocument();
    expect(screen.getByText(/sem medição: tempo do 1º veículo \(ℓ\)/)).toBeInTheDocument();
  });

  it("compara planos: envia só o que foi trocado e mostra o veredito pareado de cada plano", async () => {
    const { user, fetchMock } = await open();
    await user.click(screen.getByRole("button", { name: "Carregar exemplo ilustrativo" }));
    await user.selectOptions(screen.getByLabelText("O que fazer"), "compare");
    const plan = screen.getByRole("group", { name: "Plano 1" });
    await user.type(within(plan).getByLabelText("Nome do plano 1"), "Mais verde na 1");
    await user.type(within(plan).getByLabelText("Verde da fase 1 (s)"), "38");
    await user.type(within(plan).getByLabelText("Verde da fase 2 (s)"), "22");
    await user.click(screen.getByRole("button", { name: "Comparar planos" }));

    const table = await screen.findByRole("table", { name: /Planos semafóricos comparados/ });
    const sent = bodyOf(fetchMock, "/api/traffic/compare")!;
    expect(sent.scenarios).toHaveLength(1);
    expect(sent.scenarios[0].name).toBe("Mais verde na 1");
    expect(sent.scenarios[0].phases[0]).toEqual({ green: 38 });
    expect(sent.bonferroni).toBe(false);
    expect(within(table).getByText("Referência")).toBeInTheDocument();
    expect(within(table).getByText("Mais verde na 1")).toBeInTheDocument();
    expect(within(table).getAllByText("reduz").length).toBeGreaterThan(0);
    expect(within(table).getAllByText("aumenta").length).toBeGreaterThan(0);
    expect(screen.getByText(/ICs individuais/)).toBeInTheDocument();
  });

  it("não deixa comparar sem trocar nenhum tempo", async () => {
    const { user, fetchMock } = await open();
    await user.click(screen.getByRole("button", { name: "Carregar exemplo ilustrativo" }));
    await user.selectOptions(screen.getByLabelText("O que fazer"), "compare");
    await user.click(screen.getByRole("button", { name: "Comparar planos" }));
    expect(screen.getByText("Troque ao menos um tempo do plano.")).toBeInTheDocument();
    expect(callsTo(fetchMock, "/api/traffic/compare")).toHaveLength(0);
  });

  it("varredura: exige o verde mínimo de cada fase e depois mostra o melhor ponto e o que não se distingue", async () => {
    const { user, fetchMock } = await open();
    await user.click(screen.getByRole("button", { name: "Carregar exemplo ilustrativo" }));
    await user.selectOptions(screen.getByLabelText("O que fazer"), "sweep");
    await user.click(screen.getByRole("button", { name: "Varrer o verde" }));
    expect(screen.getByText("Informe o verde mínimo da fase 1.")).toBeInTheDocument();
    expect(callsTo(fetchMock, "/api/traffic/sweep")).toHaveLength(0);

    await user.type(screen.getByLabelText("Verde mínimo da fase 1 (s)"), "10");
    await user.type(screen.getByLabelText("Verde mínimo da fase 2 (s)"), "10");
    await user.click(screen.getByRole("button", { name: "Varrer o verde" }));
    expect(await screen.findByText(/Menor atraso médio: verde/)).toBeInTheDocument();
    expect(bodyOf(fetchMock, "/api/traffic/sweep")!.min_green).toEqual([10, 10]);
    expect(screen.getByRole("table", { name: /Pontos da varredura/ })).toBeInTheDocument();
    expect(screen.getByText("menor atraso")).toBeInTheDocument();
  });

  it("exporta o CSV da varredura com a semente que a API usou", async () => {
    const urls = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL: urls.mockReturnValue("blob:x"), revokeObjectURL: vi.fn() });
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    const { user, fetchMock } = await open();
    await user.click(screen.getByRole("button", { name: "Carregar exemplo ilustrativo" }));
    await user.selectOptions(screen.getByLabelText("O que fazer"), "sweep");
    await user.type(screen.getByLabelText("Verde mínimo da fase 1 (s)"), "10");
    await user.type(screen.getByLabelText("Verde mínimo da fase 2 (s)"), "10");
    await user.click(screen.getByRole("button", { name: "Varrer o verde" }));
    await screen.findByText(/Menor atraso médio: verde/);
    await user.click(screen.getByRole("button", { name: "Exportar CSV" }));
    await waitFor(() => expect(callsTo(fetchMock, "/api/traffic/sweep/export.csv")).toHaveLength(1));
    const seed = doneOf<SweepResult>(fx.trafficSweep).settings.seed;
    expect(bodyOf(fetchMock, "/api/traffic/sweep/export.csv")!.seed).toBe(seed);
  });
});

describe("dados do vídeo", () => {
  const csv = (name: string) => new File(["a,b\n1,2\n"], name, { type: "text/csv" });

  async function openVideo(handler: FakeHandler = happy) {
    const ctx = await open(handler);
    await ctx.user.selectOptions(screen.getByLabelText("O que fazer"), "video");
    return ctx;
  }

  it("pede os dois arquivos obrigatórios antes de chamar a API", async () => {
    const { user, fetchMock } = await openVideo();
    expect(screen.getByText("Com cabeçalho: timestamp, approach_id, signal_state")).toBeInTheDocument();
    expect(screen.getByText("Com cabeçalho: interval_start, interval_end, approach_id, arrivals, departures, queue_count")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Estimar com o vídeo" }));
    expect(screen.getByText("Escolha o CSV dos eventos semafóricos.")).toBeInTheDocument();
    expect(callsTo(fetchMock, "/video/estimate")).toHaveLength(0);
    await user.upload(screen.getByLabelText(/Eventos semafóricos/), csv("sinais.csv"));
    await user.click(screen.getByRole("button", { name: "Estimar com o vídeo" }));
    expect(screen.getByText("Escolha o CSV das contagens por intervalo.")).toBeInTheDocument();
  });

  it("estima, mostra plano, chegadas e descarga, e preenche o formulário com o que foi medido", async () => {
    const { user, fetchMock } = await openVideo();
    await user.upload(screen.getByLabelText(/Eventos semafóricos/), csv("sinais.csv"));
    await user.upload(screen.getByLabelText(/Contagens por intervalo/), csv("contagens.csv"));
    await user.upload(screen.getByLabelText(/Cruzamentos da linha de retenção/), csv("cruzamentos.csv"));
    await user.click(screen.getByRole("button", { name: "Estimar com o vídeo" }));

    expect(await screen.findByText("Plano semafórico observado")).toBeInTheDocument();
    const call = callsTo(fetchMock, "/video/estimate")[0];
    const form = call[1]!.body as FormData;
    expect([...form.keys()]).toEqual(expect.arrayContaining(["signal_events", "counts", "crossings", "max_headway", "min_run", "core", "profile_block"]));
    expect(form.get("max_headway")).toBe("4");
    expect(screen.getByRole("table", { name: /Tempo do primeiro veículo/ })).toBeInTheDocument();
    expect(screen.getAllByText(/critérios do método/i).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Usar no formulário" }));
    expect(screen.getByLabelText("O que fazer")).toHaveValue("simulate");
    expect(screen.getByLabelText("Verde da fase 1 (s)")).toHaveValue("30");
    expect(screen.getByLabelText("Offset no instante inicial (s)")).toHaveValue("17");
    expect(screen.getAllByText(/Chegadas por blocos vindas do vídeo: 4 blocos/)).toHaveLength(2);
  });

  it("valida o modelo com as contagens e mostra erros e cobertura", async () => {
    const { user, fetchMock } = await openVideo();
    await user.upload(screen.getByLabelText(/Eventos semafóricos/), csv("sinais.csv"));
    await user.upload(screen.getByLabelText(/Contagens por intervalo/), csv("contagens.csv"));
    await user.upload(screen.getByLabelText(/Cruzamentos da linha de retenção/), csv("cruzamentos.csv"));
    await user.click(screen.getByRole("button", { name: "Estimar com o vídeo" }));
    await user.click(await screen.findByRole("button", { name: "Usar no formulário" }));
    await user.selectOptions(screen.getByLabelText("O que fazer"), "video");
    await user.click(screen.getByRole("button", { name: "Validar o modelo com as contagens" }));

    expect(await screen.findByText("Validação: simulado × observado")).toBeInTheDocument();
    const form = callsTo(fetchMock, "/video/validate")[0][1]!.body as FormData;
    const config = JSON.parse(String(form.get("config"))) as Record<string, any>;
    expect(config.phases[0].green).toBe(30);
    expect(config.approaches[0].lambda).toBeUndefined();
    expect(config.approaches[0].profile).toBeUndefined();
    expect(config.approaches[0].headway.distribution).toBeDefined();
    expect(screen.getAllByRole("table", { name: /Erros da simulação contra o observado/ })).toHaveLength(2);
    expect(screen.getByText(/não há limite de aprovação/i)).toBeInTheDocument();
  });

  it("validar sem o modelo completo explica o que fazer, sem chamar a API", async () => {
    const { user, fetchMock } = await openVideo();
    await user.upload(screen.getByLabelText(/Eventos semafóricos/), csv("sinais.csv"));
    await user.upload(screen.getByLabelText(/Contagens por intervalo/), csv("contagens.csv"));
    await user.click(screen.getByRole("button", { name: "Validar o modelo com as contagens" }));
    expect(screen.getByText(/o modelo precisa estar completo/)).toBeInTheDocument();
    expect(callsTo(fetchMock, "/video/validate")).toHaveLength(0);
  });

  it("arquivo inválido: mostra o erro da API sem preencher nada", async () => {
    const { user } = await openVideo((url) => (url.endsWith("/video/estimate") ? { body: fx.errorTrafficVideo, status: 422 } : { body: {}, status: 404 }));
    await user.upload(screen.getByLabelText(/Eventos semafóricos/), csv("sinais.csv"));
    await user.upload(screen.getByLabelText(/Contagens por intervalo/), csv("contagens.csv"));
    await user.click(screen.getByRole("button", { name: "Estimar com o vídeo" }));
    expect(await screen.findByText(fx.errorTrafficVideo.message)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Arquivo inválido" })).toBeInTheDocument();
  });
});

describe("resultados reabertos do histórico (as mesmas telas)", () => {
  it("simulação", () => {
    render(<TrafficSimulationView result={fx.trafficSimulate as unknown as TrafficResult} />);
    expect(screen.getByText("Atraso médio por veículo")).toBeInTheDocument();
    expect(screen.getAllByText(/Agamenon/).length).toBeGreaterThan(0);
  });

  it("comparação de planos: dois planos, um reduz e outro aumenta o atraso", () => {
    render(<TrafficCompareView data={doneOf<CompareResult>(fx.trafficCompare)} />);
    expect(screen.getByRole("table", { name: /Planos semafóricos comparados/ })).toBeInTheDocument();
    expect(screen.getAllByText("reduz").length).toBeGreaterThan(0);
  });

  it("varredura", () => {
    render(<TrafficSweepView data={doneOf<SweepResult>(fx.trafficSweep)} />);
    expect(screen.getByText(/Menor atraso médio: verde/)).toBeInTheDocument();
    expect(screen.getAllByRole("row")).toHaveLength(6);
  });

  it("validação", () => {
    const result = fx.trafficVideoValidate as unknown as VideoValidation;
    render(<TrafficValidationView result={result} ids={{ a1: result.approaches.a1.approach_id, a2: result.approaches.a2.approach_id }} />);
    expect(screen.getAllByRole("table")).toHaveLength(2);
  });
});
