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
  if (url.endsWith("/api/realdata/compare")) return { body: fx.realdataCompareMmcn };
  return { body: fx.realdataAnalyzeClosed };
};

const arquivo = (nome = "jmeter.csv") => new File(["timeStamp,elapsed,label,success\n1,1,A,true\n"], nome, { type: "text/csv" });

async function abrir(handler: FakeHandler = happy) {
  const fetchMock = mockFetch(handler);
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Dados reais" }));
  return { user, fetchMock };
}

async function analisar(user: ReturnType<typeof userEvent.setup>, file = arquivo()) {
  await user.upload(screen.getByLabelText("CSV do JMeter"), file);
  await user.click(screen.getByRole("button", { name: /Analisar arquivo/ }));
}

describe("aba Dados reais", () => {
  it("abre a aba, antes habilitada só como 'em breve'", async () => {
    await abrir();
    expect(screen.getByRole("button", { name: "Dados reais" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByText(/em breve/i)).toBeNull();
    expect(screen.getByRole("form", { name: "Dados do teste do JMeter" })).toBeVisible();
    expect(screen.getByText("Nenhuma análise ainda")).toBeVisible();
  });

  it("sem arquivo, mostra o erro no campo e não chama a API", async () => {
    const { user, fetchMock } = await abrir();
    await user.click(screen.getByRole("button", { name: /Analisar arquivo/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Escolha o arquivo CSV");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("envia o arquivo e mostra a recomendação, o aviso de sistema fechado e os critérios", async () => {
    const { user, fetchMock } = await abrir();
    await analisar(user);

    expect(await screen.findByText(/Modelo recomendado: M\/M\/1\/\/N\. Confiança alta/)).toBeVisible();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/realdata/analyze");
    expect(init.body).toBeInstanceOf(FormData);
    expect(((init.body as FormData).get("file") as File).name).toBe("jmeter.csv");

    expect(screen.getByText(/O teste de carga é um sistema fechado/)).toBeVisible();
    const matriz = screen.getByRole("table", { name: /Critérios atendidos/ });
    const linha = within(matriz).getByRole("row", { name: /M\/M\/1\/\/N.*Recomendado/ });
    expect(within(linha).getAllByText("atende").length).toBeGreaterThanOrEqual(4);
    const descartado = within(matriz).getByRole("row", { name: /^M\/M\/1 / });
    expect(within(descartado).getAllByText("não atende").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("table", { name: /Métricas medidas/ })).toBeVisible();
    expect(screen.getByText("Verificação dos dados")).toBeVisible();
  });

  it("recompara com outro modelo sem reenviar o arquivo", async () => {
    const { user, fetchMock } = await abrir();
    await analisar(user);
    await screen.findByText(/Modelo recomendado/);

    expect(screen.getByRole("option", { name: /M\/M\/1\/K \(sem rejeições/ })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Modelo comparado"), "mmcn");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect(url).toBe("/api/realdata/compare");
    expect(JSON.parse(String(init.body))).toMatchObject({ model: "mmcn", servers: 1 });
  });

  it("mostra o erro da API para um arquivo inválido, no campo do arquivo", async () => {
    const { user } = await abrir(() => ({ status: 422, body: fx.errorInvalidDataset }));
    await analisar(user);
    expect(await screen.findByText("Arquivo inválido")).toBeVisible();
    expect(screen.getAllByText(/Colunas obrigatórias ausentes/).length).toBeGreaterThanOrEqual(1);
  });
});
