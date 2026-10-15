import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { fixtures as fx, mockFetch, type FakeHandler } from "./test/helpers";

vi.mock("plotly.js-basic-dist-min", () => ({
  default: { react: vi.fn().mockResolvedValue(undefined), purge: vi.fn() },
}));

afterEach(() => vi.unstubAllGlobals());

const csv = (nome: string, texto = "users,avg_ms,throughput\n1,196,0.8\n") => new File([texto], nome, { type: "text/csv" });

const happy: FakeHandler = (url) => {
  if (url.endsWith("/import/levels")) return { body: fx.realdataLevelsImport };
  if (url.endsWith("/compare-simulated")) return { body: fx.realdataCompareSimulated };
  if (url.endsWith("/api/realdata/compare")) return { body: fx.realdataCompareMmcn };
  if (url.endsWith("/report")) return { body: fx.realdataReport };
  return { body: fx.realdataAnalyzeClosed };
};

async function abrir(handler: FakeHandler = happy) {
  const fetchMock = mockFetch(handler);
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Dados reais" }));
  return { user, fetchMock };
}

const chamadas = (fetchMock: ReturnType<typeof mockFetch>, sufixo: string) =>
  fetchMock.mock.calls.filter((c) => String(c[0]).endsWith(sufixo));
const corpo = (chamada: unknown[]) => JSON.parse(String((chamada[1] as RequestInit).body)) as Record<string, any>;

async function analisarJtl(user: ReturnType<typeof userEvent.setup>) {
  await user.upload(screen.getByLabelText("CSV do JMeter"), csv("jmeter.csv", "timeStamp,elapsed,label,success\n1,1,A,true\n"));
  await user.click(screen.getByRole("button", { name: /Analisar arquivo/ }));
  await screen.findByText(/Modelo recomendado/);
}

function stubDownload() {
  const criados: Blob[] = [];
  vi.stubGlobal("URL", { ...URL, createObjectURL: (b: Blob) => { criados.push(b); return "blob:x"; }, revokeObjectURL: vi.fn() });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const ler = (blob: Blob) => new Promise<string>((resolve) => {
    const reader = new FileReader();                       // o Blob do jsdom não tem .text()
    reader.onload = () => resolve(String(reader.result));
    reader.readAsText(blob);
  });
  return { criados, click, ler };
}

describe("origens dos dados", () => {
  it("a aba tem as duas origens e mantém a do JTL como padrão", async () => {
    await abrir();
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Teste do JMeter (JTL)", "Níveis de carga (CSV agregado)"]);
    expect(screen.getByRole("tab", { name: /JTL/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("form", { name: "Dados do teste do JMeter" })).toBeVisible();
    expect(screen.queryByRole("form", { name: "Níveis de carga do teste" })).toBeNull();     // escondida
  });

  it("alternar não perde o resultado da outra origem", async () => {
    const { user } = await abrir();
    await analisarJtl(user);
    await user.click(screen.getByRole("tab", { name: /Níveis de carga/ }));
    expect(screen.getByText("Nenhum arquivo importado")).toBeVisible();
    await user.click(screen.getByRole("tab", { name: /JTL/ }));
    expect(screen.getByText(/Modelo recomendado/)).toBeVisible();
  });
});

describe("simulação na análise do JTL", () => {
  it("vem desligada: a comparação é só analítica, sem colunas de simulação", async () => {
    const { user, fetchMock } = await abrir();
    await analisarJtl(user);
    expect(screen.getByLabelText(/Simular também/)).not.toBeChecked();
    expect(screen.queryByRole("button", { name: "Simular e comparar" })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: /Simulação/ })).toBeNull();
    expect(chamadas(fetchMock, "/compare-simulated")).toHaveLength(0);
  });

  it("ligada, simula o modelo escolhido e mostra as colunas e o aviso", async () => {
    const { user, fetchMock } = await abrir();
    await analisarJtl(user);
    await user.click(screen.getByLabelText(/Simular também/));
    await user.click(screen.getByRole("button", { name: "Simular e comparar" }));

    await waitFor(() => expect(chamadas(fetchMock, "/compare-simulated")).toHaveLength(1));
    const enviado = corpo(chamadas(fetchMock, "/compare-simulated")[0]);
    expect(enviado).toMatchObject({ model: "mm1n", servers: 1, simulation: { simulation_time: 1000, replications: 10, seed: 2026 } });
    expect(enviado.levels.length).toBeGreaterThan(0);

    expect(await screen.findByRole("columnheader", { name: "Simulação (IC)" })).toBeVisible();
    expect(screen.getByRole("columnheader", { name: "Simulação no IC do medido" })).toBeVisible();
    expect(screen.getByText(/média simulada cai dentro do IC do medido/)).toBeVisible();
  });

  it("com a simulação ligada, trocar de modelo simula em vez de só comparar", async () => {
    const { user, fetchMock } = await abrir();
    await analisarJtl(user);
    await user.click(screen.getByLabelText(/Simular também/));
    await user.selectOptions(screen.getByLabelText("Modelo comparado"), "mmcn");
    await waitFor(() => expect(chamadas(fetchMock, "/compare-simulated")).toHaveLength(1));
    expect(corpo(chamadas(fetchMock, "/compare-simulated")[0]).model).toBe("mmcn");
    expect(chamadas(fetchMock, "/api/realdata/compare")).toHaveLength(0);
  });

  it("confere o formato dos campos antes de chamar a API e mostra o erro da API no campo", async () => {
    const { user, fetchMock } = await abrir((url) => url.endsWith("/compare-simulated")
      ? { status: 422, body: { code: "invalid_parameter", message: "Mínimo 2 réplicas.", fields: [{ field: "replications", message: "Mínimo 2 réplicas." }] } }
      : happy(url, {}));
    await analisarJtl(user);
    await user.click(screen.getByLabelText(/Simular também/));
    const painel = within(screen.getByRole("tabpanel", { name: "Dados reais" }));     // a aba Laboratório também tem "Réplicas"
    await user.clear(painel.getByLabelText("Réplicas"));
    await user.type(painel.getByLabelText("Réplicas"), "x");
    await user.click(screen.getByRole("button", { name: "Simular e comparar" }));
    expect(await screen.findByText("Informe um número inteiro.")).toBeVisible();
    expect(chamadas(fetchMock, "/compare-simulated")).toHaveLength(0);

    await user.clear(painel.getByLabelText("Réplicas"));
    await user.type(painel.getByLabelText("Réplicas"), "1");
    await user.click(screen.getByRole("button", { name: "Simular e comparar" }));
    await waitFor(() => expect(painel.getByLabelText("Réplicas")).toHaveAttribute("aria-invalid", "true"));
    expect(screen.getAllByText("Mínimo 2 réplicas.").length).toBeGreaterThan(0);
  });
});

describe("relatório", () => {
  it("baixa o relatório da análise do JTL gerado pela API", async () => {
    const { criados, click, ler } = stubDownload();
    const { user, fetchMock } = await abrir();
    await analisarJtl(user);
    await user.click(screen.getByRole("button", { name: /Markdown/ }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    const enviado = corpo(chamadas(fetchMock, "/report")[0]);
    expect(enviado.format).toBe("markdown");
    expect(enviado.analysis.recommended.notation).toBe(fx.realdataAnalyzeClosed.recommended?.notation);
    expect("comparison" in enviado).toBe(false);                  // modelo recomendado: a análise já traz a comparação
    expect(await ler(criados[0])).toBe(fx.realdataReport.content);
    click.mockRestore();
  });

  it("inclui a comparação simulada no relatório e oferece HTML", async () => {
    const { click } = stubDownload();
    const { user, fetchMock } = await abrir();
    await analisarJtl(user);
    await user.click(screen.getByLabelText(/Simular também/));
    await user.click(screen.getByRole("button", { name: "Simular e comparar" }));
    await screen.findByRole("columnheader", { name: "Simulação (IC)" });
    await user.click(screen.getByRole("button", { name: /HTML/ }));
    await waitFor(() => expect(chamadas(fetchMock, "/report")).toHaveLength(1));
    const enviado = corpo(chamadas(fetchMock, "/report")[0]);
    expect(enviado.format).toBe("html");
    expect(enviado.comparison.simulation.seed).toBe(fx.realdataCompareSimulated.simulation.seed);
    click.mockRestore();
  });

  it("mostra o erro da API quando o relatório falha", async () => {
    stubDownload();
    const { user } = await abrir((url) => url.endsWith("/report")
      ? { status: 422, body: { code: "invalid_parameter", message: "Nada para relatar.", fields: [] } }
      : happy(url, {}));
    await analisarJtl(user);
    await user.click(screen.getByRole("button", { name: /Markdown/ }));
    expect(await screen.findByText("Nada para relatar.")).toBeVisible();
  });
});

describe("níveis de carga (CSV agregado)", () => {
  async function importar(user: ReturnType<typeof userEvent.setup>, handlerNome = "niveis.csv") {
    await user.click(screen.getByRole("tab", { name: /Níveis de carga/ }));
    await user.upload(screen.getByLabelText("CSV de níveis de carga"), csv(handlerNome));
    await user.click(screen.getByRole("button", { name: "Importar níveis" }));
    await screen.findByRole("region", { name: "Níveis importados" });
  }

  it("importa, mostra a tabela e preenche μ e Z com a calibração do menor nível", async () => {
    const { user, fetchMock } = await abrir();
    await importar(user);
    const [url, init] = chamadas(fetchMock, "/import/levels")[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/realdata/import/levels");
    expect(init.body).toBeInstanceOf(FormData);
    expect(((init.body as FormData).get("file") as File).name).toBe("niveis.csv");

    const s = fx.realdataLevelsImport.suggestions;
    expect(screen.getByLabelText("μ do modelo (req/s)")).toHaveValue(String(Number(s.mu.toPrecision(4))));
    expect(screen.getByLabelText("Reflexão do modelo Z (s)")).toHaveValue(String(Number(s.think_time.toPrecision(4))));
    expect(screen.getByRole("table", { name: /Métricas medidas/ })).toBeVisible();
    expect(screen.getByText(/Calibração sugerida no menor nível \(1 usuário\)/)).toBeVisible();
    expect(screen.getByText(/lei de Little/)).toBeVisible();
  });

  it("compara com o modelo escolhido pelo mesmo /compare da análise do JTL", async () => {
    const { user, fetchMock } = await abrir();
    await importar(user);
    await user.click(screen.getByRole("button", { name: "Comparar com o modelo" }));
    await waitFor(() => expect(chamadas(fetchMock, "/api/realdata/compare")).toHaveLength(1));
    const enviado = corpo(chamadas(fetchMock, "/api/realdata/compare")[0]);
    expect(enviado).toMatchObject({ model: "mm1n", servers: 1 });
    expect(enviado.levels).toHaveLength(fx.realdataLevelsImport.levels.length);
    expect(enviado.mu).toBeCloseTo(fx.realdataLevelsImport.suggestions.mu, 3);
    expect("simulation" in enviado).toBe(false);
    expect(await screen.findByRole("table", { name: /Modelo comparado com a medição/ })).toBeVisible();
  });

  it("com 'Simular também', usa /compare-simulated e mostra a simulação no gráfico e na tabela", async () => {
    const { user, fetchMock } = await abrir();
    await importar(user);
    await user.click(screen.getByLabelText(/Simular também/));
    await user.click(screen.getByRole("button", { name: "Comparar com o modelo" }));
    await waitFor(() => expect(chamadas(fetchMock, "/compare-simulated")).toHaveLength(1));
    expect(corpo(chamadas(fetchMock, "/compare-simulated")[0]).simulation).toMatchObject({ replications: 10, seed: 2026 });
    expect(await screen.findByRole("columnheader", { name: "Simulação (IC)" })).toBeVisible();
    expect(screen.getAllByRole("img", { name: /Tempo médio de resposta/ }).length).toBeGreaterThan(0);
  });

  it("os campos mudam com o modelo: capacidade só para K, Z só para fechado", async () => {
    const { user } = await abrir();
    await importar(user);
    expect(screen.queryByLabelText("Capacidade do modelo (K)")).toBeNull();
    await user.selectOptions(screen.getByLabelText("Modelo dos níveis"), "mmck");
    expect(screen.getByLabelText("Capacidade do modelo (K)")).toBeVisible();
    expect(screen.getByLabelText("Servidores do modelo (c)")).toBeVisible();
    expect(screen.queryByLabelText("Reflexão do modelo Z (s)")).toBeNull();
  });

  it("baixa o relatório com os níveis importados e a comparação", async () => {
    const { click } = stubDownload();
    const { user, fetchMock } = await abrir();
    await importar(user);
    await user.click(screen.getByRole("button", { name: "Comparar com o modelo" }));
    await screen.findByRole("table", { name: /Modelo comparado com a medição/ });
    const grupos = screen.getAllByRole("group", { name: "Relatório experimental" });
    await user.click(within(grupos[grupos.length - 1]).getByRole("button", { name: /Markdown/ }));
    await waitFor(() => expect(chamadas(fetchMock, "/report")).toHaveLength(1));
    const enviado = corpo(chamadas(fetchMock, "/report")[0]);
    expect(enviado.levels_import.levels).toHaveLength(fx.realdataLevelsImport.levels.length);
    expect(enviado.comparison.notation).toBe(fx.realdataCompareMmcn.notation);
    click.mockRestore();
  });

  it("arquivo inválido: erro da API no campo do arquivo, sem mostrar o formulário do modelo", async () => {
    const { user } = await abrir((url) => url.endsWith("/import/levels") ? { status: 422, body: fx.realdataLevelsError } : happy(url, {}));
    await importar(user, "niveis.csv").catch(() => undefined);
    expect(await screen.findByText("Arquivo inválido")).toBeVisible();
    expect(screen.getAllByText(/extensão \.csv/).length).toBeGreaterThan(0);
    expect(screen.queryByRole("form", { name: "Modelo dos níveis de carga" })).toBeNull();
  });

  it("sem arquivo, mostra o erro no campo e não chama a API", async () => {
    const { user, fetchMock } = await abrir();
    await user.click(screen.getByRole("tab", { name: /Níveis de carga/ }));
    await user.click(screen.getByRole("button", { name: "Importar níveis" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Escolha o arquivo CSV");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
