import { render, screen, waitFor, within } from "@testing-library/react";
import Plotly from "plotly.js-basic-dist-min";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  fromCalculate, fromCompare, fromSimulate,
  type CalculateResponse, type CompareResponse, type SimulateResponse,
} from "../api/mappers";
import type { ViewResult } from "../domain/types";
import { clone, fixtures as fx } from "../test/helpers";
import { DeviationChart } from "./DeviationChart";
import { HeadlineCards } from "./HeadlineCards";
import { MetricsTable } from "./MetricsTable";
import { VerdictBanner } from "./VerdictBanner";

vi.mock("plotly.js-basic-dist-min", () => ({
  default: { react: vi.fn().mockResolvedValue(undefined), purge: vi.fn() },
}));

const params = { lambda: 1, mu: 1 };
const compare = (res: unknown = fx.mmckCompare): ViewResult => fromCompare("mmck", params, res as CompareResponse);
const simulate = (): ViewResult => fromSimulate("mmck", params, fx.mmckSimulate as unknown as SimulateResponse);
const calculate = (model: "mm1" | "mmck" = "mmck"): ViewResult =>
  model === "mm1"
    ? fromCalculate("mm1", params, fx.mm1Calculate as unknown as CalculateResponse)
    : fromCalculate("mmck", params, fx.mmckCalculate as unknown as CalculateResponse);

describe("VerdictBanner", () => {
  it("compare com tudo dentro do IC: sucesso, com o erro máximo", () => {
    render(<VerdictBanner result={compare()} />);
    expect(screen.getByRole("status")).toHaveClass("banner-success");
    expect(screen.getByText("As 8 métricas do analítico estão dentro do IC de 95%.")).toBeInTheDocument();
    expect(screen.getByText(/Erro relativo máximo: \d+,\d{2}%\./)).toBeInTheDocument();
  });

  it("compare com métricas fora do IC: aviso com a contagem e uma explicação", () => {
    const res = clone(fx.mmckCompare);
    res.metrics.L.within_ci = false;
    res.metrics.Wq.within_ci = false;
    res.all_within_ci = false;
    render(<VerdictBanner result={compare(res)} />);
    expect(screen.getByRole("status")).toHaveClass("banner-warning");
    expect(screen.getByText("2 de 8 métricas ficaram fora do IC de 95%.")).toBeInTheDocument();
    expect(screen.getByText(/é normal uma ou outra sair do intervalo por acaso/)).toBeInTheDocument();
  });

  it("compare com 1 réplica: informa que não há IC", () => {
    render(<VerdictBanner result={compare(fx.mmckCompare1Rep)} />);
    expect(screen.getByRole("status")).toHaveClass("banner-info");
    expect(screen.getByText("Com 1 réplica não há intervalo de confiança.")).toBeInTheDocument();
  });

  it("só calcular e só simular têm mensagens próprias", () => {
    const { unmount } = render(<VerdictBanner result={calculate()} />);
    expect(screen.getByText("Métricas analíticas em regime estacionário.")).toBeInTheDocument();
    unmount();
    render(<VerdictBanner result={simulate()} />);
    expect(screen.getByText("Simulação concluída: 5 réplicas de 300 s.")).toBeInTheDocument();
  });
});

describe("HeadlineCards", () => {
  it("modelos com fila: utilização, vazão, recusas e espera", () => {
    render(<HeadlineCards result={compare()} />);
    const cards = screen.getByLabelText("Destaques");
    for (const label of ["Utilização (ρ)", "Vazão efetiva", "Chegadas recusadas", "Clientes que esperam"]) {
      expect(within(cards).getByText(label)).toBeInTheDocument();
    }
    expect(within(cards).getByText("74,8%")).toBeInTheDocument();   // ρ analítico
    expect(within(cards).getAllByText(/^simulado: /)).toHaveLength(4);
  });

  it("M/M/1: utilização, L, W e Wq", () => {
    render(<HeadlineCards result={calculate("mm1")} />);
    const cards = screen.getByLabelText("Destaques");
    expect(within(cards).getByText("Utilização (ρ)")).toBeInTheDocument();
    expect(within(cards).getByText("Nº médio no sistema")).toBeInTheDocument();
    expect(within(cards).getByText("Tempo médio de espera")).toBeInTheDocument();
    expect(within(cards).getByText("80,0%")).toBeInTheDocument();
    expect(within(cards).queryByText(/^simulado: /)).toBeNull(); // calculate não tem simulação
  });

  it("só simular mostra o valor simulado como principal", () => {
    render(<HeadlineCards result={simulate()} />);
    expect(screen.queryByText(/^simulado: /)).toBeNull();
    expect(within(screen.getByLabelText("Destaques")).getAllByText(/%|req\/s/).length).toBeGreaterThan(0);
  });
});

describe("MetricsTable", () => {
  it("compare: colunas de analítico, simulação, IC, erro e veredito, uma linha por métrica", () => {
    render(<MetricsTable result={compare()} />);
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Métrica", "Analítico", "Simulação", "IC", "Erro", "No IC?"]);
    expect(screen.getAllByRole("row")).toHaveLength(1 + 8);
    expect(screen.getByRole("rowheader", { name: "Probabilidade de recusa (p_block)" })).toBeInTheDocument();
    expect(screen.getAllByText("sim")).toHaveLength(8);
  });

  it("compare com métrica fora do IC mostra 'não'", () => {
    const res = clone(fx.mmckCompare);
    res.metrics.L.within_ci = false;
    render(<MetricsTable result={compare(res)} />);
    expect(screen.getByText("não")).toBeInTheDocument();
  });

  it("com 1 réplica, IC e veredito aparecem como traço", () => {
    render(<MetricsTable result={compare(fx.mmckCompare1Rep)} />);
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(16);
    expect(screen.queryByText("sim")).toBeNull();
  });

  it("calcular: só a coluna Valor; simular: desvio padrão no lugar de erro", () => {
    const { unmount } = render(<MetricsTable result={calculate()} />);
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Métrica", "Valor"]);
    unmount();
    render(<MetricsTable result={simulate()} />);
    expect(screen.getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Métrica", "Simulação", "IC", "Desvio padrão"]);
  });

  it("intervalos usam o mesmo número de casas nos dois limites", () => {
    render(<MetricsTable result={compare()} />);
    const interval = screen.getAllByText(/^\[/).map((c) => c.textContent!);
    const decimals = (v: string) => (v.split(",")[1] ?? "").replace(/\D/g, "").length;
    expect(interval.length).toBeGreaterThan(0);
    for (const text of interval) {
      const [lo, hi] = text.slice(1, -1).split("; ");
      expect(decimals(lo), text).toBe(decimals(hi));
    }
  });
});

describe("DeviationChart", () => {
  beforeEach(() => vi.mocked(Plotly.react).mockClear());

  it("entrega ao Plotly uma série por categoria e um rótulo acessível", async () => {
    render(<DeviationChart result={compare()} />);
    expect(screen.getByRole("img", { name: /Diferença percentual da simulação/ })).toBeInTheDocument();
    await waitFor(() => expect(Plotly.react).toHaveBeenCalled());
    const [, data] = vi.mocked(Plotly.react).mock.calls[0];
    expect(data).toHaveLength(1); // tudo dentro do IC -> uma série
  });

  it("avisa quais métricas ficaram fora (valor analítico igual a 0)", () => {
    const res = fromCompare("mmc", params, fx.mmcCompare as unknown as CompareResponse);
    render(<DeviationChart result={res} />);
    expect(screen.getByText(/Fora do gráfico \(valor analítico igual a 0\): p_block\./)).toBeInTheDocument();
  });

  it("não desenha nada com 1 réplica (sem IC)", () => {
    const { container } = render(<DeviationChart result={compare(fx.mmckCompare1Rep)} />);
    expect(container).toBeEmptyDOMElement();
  });
});
