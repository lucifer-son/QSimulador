import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fromCalculate, type CalculateResponse } from "../api/mappers";
import { stateChart, sensitivityChart, tailChart, fitChart } from "../charts/analysis";
import { fitRecord, parseFitRecord, fitTitle } from "../domain/records";
import { clone, colors, fixtures as fx, mockFetch, type FakeHandler } from "../test/helpers";
import { DistributionsTab } from "./DistributionsTab";
import { FitTab } from "./FitTab";
import { RealDataResults } from "./RealDataTab";

vi.mock("plotly.js-basic-dist-min", () => ({
  default: { react: vi.fn().mockResolvedValue(undefined), purge: vi.fn() },
}));

afterEach(() => vi.unstubAllGlobals());

const mmc = fromCalculate("mmc", { lambda: 8, mu: 1, servers: 10 }, fx.mmcCalculate as unknown as CalculateResponse);

describe("gráficos", () => {
  it("P(n): barras com o estado de bloqueio destacado", () => {
    const c = stateChart(fx.analysisDistributionMmck.states!, colors);
    const bar = c.data[0] as { x: number[]; marker: { color: string[] } };
    expect(bar.x).toEqual([0, 1, 2, 3, 4, 5, 6]);
    expect(bar.marker.color.at(-1)).toBe(colors.danger);
    expect(bar.marker.color[0]).toBe(colors.accent);
  });
  it("P(Wq > t): faixa do IC, simulação e fórmula fechada, com escala log opcional", () => {
    const d = fx.analysisDistributionMmc;
    const c = tailChart(d.wait_closed_form, d.wait_simulation, colors, true);
    expect(c.data.map((t) => (t as { name: string }).name)).toEqual(["IC da simulação", "Simulação", "Fórmula fechada"]);
    expect((c.layout.yaxis as Record<string, unknown>).type).toBe("log");
    expect((tailChart(null, d.wait_simulation, colors).layout.yaxis as Record<string, unknown>).range).toEqual([0, 1]);
  });
  it("Wq × λ: marca o ponto atual", () => {
    const c = sensitivityChart(fx.analysisSensitivityMm1 as never, colors);
    const marker = c.data[1] as { x: number[]; y: number[] };
    expect(marker.x).toEqual([40]);
    expect(marker.y[0]).toBeCloseTo(0.08, 6);
  });
  it("histograma com só as curvas escolhidas", () => {
    const result = fx.analysisFitLognormal.at(-1)!.result!;
    const c = fitChart(result as never, colors, ["lognormal", "weibull"]);
    expect(c.data.map((t) => (t as { name: string }).name)).toEqual(["Amostra", "Lognormal", "Weibull"]);
  });
});

describe("aba Distribuições", () => {
  const handler: FakeHandler = (url) =>
    url.endsWith("/api/analysis/sensitivity") ? { body: fx.analysisSensitivityMm1 } : { body: fx.analysisDistributionMmc };

  it("pede distribuição e sensibilidade com a configuração do Laboratório e mostra as três seções", async () => {
    const fetchMock = mockFetch(handler);
    render(<DistributionsTab result={mmc} />);
    expect(await screen.findByRole("heading", { name: /P\(n\)/ })).toBeInTheDocument();
    const calls = fetchMock.mock.calls.map(([url, init]) => [String(url), JSON.parse(String(init!.body))] as const);
    const dist = calls.find(([u]) => u.endsWith("/distribution"))![1];
    expect(dist).toMatchObject({ model: "mmc", lambda: 8, mu: 1, servers: 10, simulate: false });
    expect(calls.find(([u]) => u.endsWith("/sensitivity"))![1]).toMatchObject({ model: "mmc", lambda: 8, servers: 10 });
    expect(screen.getByRole("heading", { name: /P\(Wq > t\)/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Wq × λ/ })).toBeInTheDocument();
    expect(screen.getByText(/espera mediana/)).toBeInTheDocument();
  });

  it("“Conferir com a simulação” refaz o pedido com simulate", async () => {
    const fetchMock = mockFetch(handler);
    const user = userEvent.setup();
    render(<DistributionsTab result={mmc} />);
    await user.click(await screen.findByLabelText("Conferir com a simulação"));
    await waitFor(() => {
      const bodies = fetchMock.mock.calls.map(([, init]) => JSON.parse(String(init!.body)) as Record<string, unknown>);
      expect(bodies.some((b) => b.simulate === true)).toBe(true);
    });
  });

  it("serviço geral não tem P(n): mostra a explicação da API", async () => {
    mockFetch((url) => (url.endsWith("/sensitivity") ? { body: fx.analysisSensitivityMm1 } : { body: fx.analysisDistributionMgc }));
    render(<DistributionsTab result={{ ...mmc, modelKey: "mgc" }} />);
    expect(await screen.findByText(/Allen–Cunneen/)).toBeInTheDocument();
  });

  it("Erlang-B explica que não há fila e não chama a API", () => {
    const fetchMock = mockFetch(handler);
    render(<DistributionsTab result={{ ...mmc, modelKey: "erlangb" }} />);
    expect(screen.getByText(/sistema de perda/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("mostra o erro da API", async () => {
    mockFetch(() => ({ status: 422, body: fx.errorAnalysisErlangb }));
    render(<DistributionsTab result={mmc} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/Erlang-B/);
  });
});

describe("painel Ajustar distribuição", () => {
  const happy: FakeHandler = () => ({ ndjson: true, body: fx.analysisFitLognormal });

  it("não envia amostra com menos de 10 valores", async () => {
    const fetchMock = mockFetch(happy);
    const user = userEvent.setup();
    render(<FitTab />);
    await user.type(screen.getByLabelText("Amostra"), "1 2 3");
    await user.click(screen.getByRole("button", { name: "Ajustar" }));
    expect(screen.getByRole("status", { name: "" })).toHaveTextContent(/pelo menos 10 valores/);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("ajusta, mostra o CV, a sugestão, a tabela e o aviso de AIC da uniforme", async () => {
    const fetchMock = mockFetch(happy);
    const user = userEvent.setup();
    render(<FitTab />);
    await user.click(screen.getByLabelText("Amostra"));
    await user.paste("0,8\n1,1\n0,5\n2,2\n0,9\n1,4\n0,7\n1,6\n3,0\n0,6\n1,0\n1,3");
    await user.type(screen.getByLabelText("Réplicas do p-valor (B)"), "40");
    await user.type(screen.getByLabelText("Semente (opcional)"), "7");
    await user.click(screen.getByRole("button", { name: "Ajustar" }));

    const table = await screen.findByRole("table");
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]!.body)) as Record<string, unknown>;
    expect(body).toMatchObject({ kind: "service", bootstrap: 40, seed: 7 });
    expect((body.sample as number[]).slice(0, 3)).toEqual([0.8, 1.1, 0.5]);
    expect(within(table).getAllByRole("row")).toHaveLength(6);
    expect(within(table).getByRole("row", { name: /Lognormal ★/ })).toBeInTheDocument();
    expect(screen.getByText(/Modelo sugerido: M\/G\/c/)).toBeInTheDocument();
    expect(screen.getByText(/não é diretamente comparável/)).toBeInTheDocument();
    expect(within(table).getByRole("row", { name: /Exponencial.*rejeitada/ })).toBeInTheDocument();
  });

  it("importa CSV e avisa quando passa do limite de 10 MB", async () => {
    mockFetch(happy);
    const user = userEvent.setup();
    render(<FitTab />);
    const input = screen.getByLabelText("Importar arquivo da amostra");
    await user.upload(input, new File(["tempo\n1.5\n2.5\nabc\n"], "t.csv", { type: "text/csv" }));
    expect(await screen.findByText(/2 valores lidos de t\.csv; 1 linha\(s\) ignorada/)).toBeInTheDocument();
    const big = new File(["x"], "grande.csv", { type: "text/csv" });
    Object.defineProperty(big, "size", { value: 10 * 1024 * 1024 + 1 });
    await user.upload(input, big);
    expect(await screen.findByText(/passa do limite de 10 MB/)).toBeInTheDocument();
  });

  it("mostra o erro 422 da API e a amostra constante sem tabela", async () => {
    mockFetch(() => ({ status: 422, body: fx.errorAnalysisFitSample }));
    const user = userEvent.setup();
    render(<FitTab />);
    await user.click(screen.getByLabelText("Amostra"));
    await user.paste("1 2 3 4 5 6 7 8 9 10");
    await user.click(screen.getByRole("button", { name: "Ajustar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Não foi possível ajustar/);

    mockFetch(() => ({ ndjson: true, body: fx.analysisFitConstant }));
    await user.click(screen.getByRole("button", { name: "Ajustar" }));
    expect(await screen.findByText(/Modelo sugerido: M\/D\/c/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("histórico do ajuste", () => {
  const result = fx.analysisFitLognormal.at(-1)!.result as never;
  it("grava como experimento do tipo fit, sem a amostra, e reabre", () => {
    const record = fitRecord({ sample: [1, 2, 3], kind: "service", bootstrap: 40, seed: 7 }, result);
    expect(record.kind).toBe("experiment");
    expect(JSON.stringify(record.params)).not.toContain("sample");
    expect(record.params).toMatchObject({ experiment: "fit", request: { kind: "service", bootstrap: 40, seed: 7, n: 300 } });
    expect(record.title).toBe(fitTitle(result));
    expect(fitTitle(result)).toContain("melhor AIC: Lognormal");
    const back = parseFitRecord({ id: "1", created_at: "", updated_at: "", ...record } as never);
    expect(back?.best).toBe("lognormal");
    expect(parseFitRecord({ params: { origin: "experiment", experiment: "sweep" }, result: {} } as never)).toBeNull();
  });
});

describe("Dados reais: sugestão pelo CV", () => {
  it("mostra a sugestão sem mexer no ranking", () => {
    const hint = fx.realdataAnalyzeHint;
    render(<RealDataResults result={hint as never} />);
    const note = screen.getByTestId("service-hint");
    expect(note).toHaveTextContent("Sugestão pelo CV: M/D/c");
    expect(note).toHaveTextContent(/Não altera o ranking/);
  });
  it("sem service_hint, nada aparece", () => {
    const r = clone(fx.realdataAnalyzeHint) as Record<string, unknown>;
    r.service_hint = null;
    render(<RealDataResults result={r as never} />);
    expect(screen.queryByTestId("service-hint")).not.toBeInTheDocument();
  });
});
