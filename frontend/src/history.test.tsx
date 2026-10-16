import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { fixtures as fx, FakeRecords, mockFetch, type FakeHandler } from "./test/helpers";

vi.mock("plotly.js-basic-dist-min", () => ({
  default: { react: vi.fn().mockResolvedValue(undefined), purge: vi.fn() },
}));

beforeEach(() => window.localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

const happy: FakeHandler = (url) => {
  if (url.endsWith("/api/realdata/analyze")) return { body: fx.realdataAnalyzeClosed };
  if (url.endsWith("/sweep")) return { body: fx.experimentSweepMm1 };
  if (url.endsWith("/compare")) return { body: fx.mmckCompare };
  if (url.endsWith("/simulate")) return { body: fx.mmckSimulate };
  return { body: fx.mmckCalculate };
};

async function setup(records = new FakeRecords(true), handler: FakeHandler = happy) {
  const fetchMock = mockFetch(handler, records);
  const user = userEvent.setup();
  const view = render(<App />);
  return { user, fetchMock, records, view };
}
const button = (name: string | RegExp) => screen.getByRole("button", { name });
const nav = (name: string) => screen.getByRole("button", { name, hidden: false });
type User = ReturnType<typeof userEvent.setup>;

/** Roda a comparação no Laboratório (M/M/c/K, λ = 25). */
async function compare(user: User) {
  await user.click(button("Comparar"));
  await screen.findByRole("tablist", { name: "Seções do resultado" });
}
async function saveLab(user: User, title?: string) {
  await user.click(await screen.findByRole("button", { name: "Salvar no histórico" }));
  if (title !== undefined) {
    const input = screen.getByLabelText("Título");
    await user.clear(input);
    await user.type(input, title);
  }
  await user.click(screen.getByRole("button", { name: "Salvar" }));
  await screen.findByText(/Salvo\./);
}

describe("histórico desativado", () => {
  it("não oferece Salvar e a aba explica que o servidor não tem banco", async () => {
    const { user, fetchMock } = await setup(new FakeRecords(false));
    await compare(user);
    expect(screen.queryByRole("button", { name: "Salvar no histórico" })).toBeNull();
    await user.click(nav("Histórico"));
    expect(await screen.findByText("Histórico indisponível")).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(1); // só o cálculo; o histórico não conta
  });

  it("se a API de status falha, o resto do app continua funcionando", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.startsWith("/api/records")) throw new TypeError("Failed to fetch");
      return new Response(JSON.stringify(fx.mmckCompare), { status: 200 });
    }));
    const user = userEvent.setup();
    render(<App />);
    await compare(user);
    expect(screen.queryByRole("button", { name: "Salvar no histórico" })).toBeNull();
  });
});

describe("salvar no Laboratório", () => {
  it("grava o resultado com o título sugerido e o identificador do navegador", async () => {
    const { user, records } = await setup();
    await compare(user);
    await user.click(await screen.findByRole("button", { name: "Salvar no histórico" }));
    expect(screen.getByLabelText("Título")).toHaveValue("M/M/3/6 · Comparação (λ=25, μ=10)");
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByText(/Salvo\./)).toBeVisible();

    expect(records.store).toHaveLength(1);
    const saved = records.store[0];
    expect(saved).toMatchObject({ kind: "comparison", title: "M/M/3/6 · Comparação (λ=25, μ=10)" });
    expect(saved.params).toMatchObject({ origin: "lab", model: "mmck", action: "compare" });
    expect(saved.result).toMatchObject({ modelKey: "mmck", action: "compare" });
    const post = records.calls.find((c) => c.method === "POST")!;
    expect(post.clientId).toBe(window.localStorage.getItem("qsimulador-client-id"));
  });

  it("deixa o usuário trocar o título; título vazio não salva", async () => {
    const { user, records } = await setup();
    await compare(user);
    await user.click(await screen.findByRole("button", { name: "Salvar no histórico" }));
    await user.clear(screen.getByLabelText("Título"));
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Informe um título.");
    expect(records.store).toHaveLength(0);
    await user.type(screen.getByLabelText("Título"), "Meu teste");
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    await screen.findByText(/Salvo\./);
    expect(records.store[0].title).toBe("Meu teste");
  });

  it("cancelar não grava nada", async () => {
    const { user, records } = await setup();
    await compare(user);
    await user.click(await screen.findByRole("button", { name: "Salvar no histórico" }));
    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(records.store).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Salvar no histórico" })).toBeVisible();
  });

  it.each([
    ["record_limit_reached", 409, /limite de registros/i],
    ["database_unavailable", 503, /acessar o banco de dados/i],
    ["record_too_large", 413, /grande demais/i],
  ])("mostra uma mensagem clara quando o servidor responde %s", async (code, status, text) => {
    const { user, records } = await setup();
    await compare(user);
    await user.click(await screen.findByRole("button", { name: "Salvar no histórico" }));
    records.failNext = { status, code, message: "Não foi possível acessar o banco de dados." };
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
    expect(screen.queryByText(/Salvo\./)).toBeNull();
    expect(records.store).toHaveLength(0);
    // o formulário continua aberto: dá para tentar de novo
    expect(screen.getByLabelText("Título")).toBeVisible();
  });

  it("depois de salvar, 'Ver no Histórico' abre a aba com o registro", async () => {
    const { user } = await setup();
    await compare(user);
    await saveLab(user);
    await user.click(button("Ver no Histórico"));
    expect(nav("Histórico")).toHaveAttribute("aria-current", "page");
    expect(await screen.findByText("M/M/3/6 · Comparação (λ=25, μ=10)")).toBeVisible();
  });
});

describe("aba Histórico", () => {
  it("lista do mais recente para o mais antigo, com tipo e tamanho", async () => {
    const records = new FakeRecords(true);
    records.add({ kind: "simulation", title: "Primeiro", params: {}, result: { a: 1 } });
    records.add({ kind: "experiment", title: "Segundo", params: {}, result: { a: 1 } });
    const { user } = await setup(records);
    await user.click(nav("Histórico"));
    const items = await within(await screen.findByRole("list", { name: "Resultados salvos" })).findAllByRole("listitem");
    expect(items.map((li) => within(li).getByRole("strong", {} as never).textContent)).toEqual(["Segundo", "Primeiro"]);
    expect(items[0]).toHaveTextContent("Experimento");
    expect(items[1]).toHaveTextContent("Simulação");
  });

  it("mostra o aviso de lista vazia", async () => {
    const { user } = await setup();
    await user.click(nav("Histórico"));
    expect(await screen.findByText(/Nenhum resultado salvo/)).toBeVisible();
  });

  it("informa o limite por navegador", async () => {
    const records = new FakeRecords(true);
    records.limits = { max_record_bytes: 1000, max_records_per_client: 7 };
    const { user } = await setup(records);
    await user.click(nav("Histórico"));
    expect(await screen.findByText(/até 7 resultados/)).toBeVisible();
  });

  it("filtra por tipo", async () => {
    const records = new FakeRecords(true);
    records.add({ kind: "simulation", title: "S1", params: {}, result: {} });
    records.add({ kind: "experiment", title: "E1", params: {}, result: {} });
    const { user } = await setup(records);
    await user.click(nav("Histórico"));
    await screen.findByText("S1");
    await user.selectOptions(screen.getByLabelText("Tipo"), "experiment");
    await waitFor(() => expect(screen.queryByText("S1")).toBeNull());
    expect(screen.getByText("E1")).toBeVisible();
    expect(records.calls.at(-1)!.url).toContain("kind=experiment");
  });

  it("carrega mais registros por páginas", async () => {
    const records = new FakeRecords(true);
    for (let i = 1; i <= 25; i++) records.add({ kind: "simulation", title: `R${i}`, params: {}, result: {} });
    const { user } = await setup(records);
    await user.click(nav("Histórico"));
    await screen.findByText("R25");
    expect(screen.getAllByRole("listitem")).toHaveLength(20);
    await user.click(screen.getByRole("button", { name: /Carregar mais \(20 de 25\)/ }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(25));
    expect(screen.queryByRole("button", { name: /Carregar mais/ })).toBeNull();
  });

  it("renomeia um registro", async () => {
    const records = new FakeRecords(true);
    records.add({ kind: "simulation", title: "Antigo", params: {}, result: {} });
    const { user } = await setup(records);
    await user.click(nav("Histórico"));
    await screen.findByText("Antigo");
    await user.click(button("Renomear"));
    const input = screen.getByLabelText("Novo título");
    await user.clear(input);
    await user.type(input, "Novo nome");
    await user.click(button("Salvar título"));
    expect(await screen.findByText("Novo nome")).toBeVisible();
    expect(screen.queryByText("Antigo")).toBeNull();
    expect(records.store[0].title).toBe("Novo nome");
  });

  it("exclui só depois de confirmar", async () => {
    const records = new FakeRecords(true);
    records.add({ kind: "simulation", title: "Apagar", params: {}, result: {} });
    const { user } = await setup(records);
    await user.click(nav("Histórico"));
    await screen.findByText("Apagar");
    await user.click(button("Excluir"));
    expect(records.store).toHaveLength(1); // ainda não excluiu
    await user.click(button("Cancelar"));
    expect(records.store).toHaveLength(1);
    await user.click(button("Excluir"));
    await user.click(button("Confirmar exclusão"));
    await waitFor(() => expect(records.store).toHaveLength(0));
    expect(screen.queryByText("Apagar")).toBeNull();
  });

  it("mostra o erro quando o banco está indisponível", async () => {
    const records = new FakeRecords(true);
    records.add({ kind: "simulation", title: "X", params: {}, result: {} });
    const { user } = await setup(records);
    records.failNext = { status: 503, code: "database_unavailable", message: "Não foi possível acessar o banco de dados." };
    await user.click(nav("Histórico"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/acessar o banco de dados/i);
  });

  it("um registro de formato desconhecido não derruba a tela", async () => {
    const records = new FakeRecords(true);
    records.add({ kind: "model", title: "Estranho", params: { origin: "futuro" }, result: { qualquer: true } });
    const { user } = await setup(records);
    await user.click(nav("Histórico"));
    await user.click(await screen.findByRole("button", { name: "Abrir" }));
    expect(await screen.findByText(/formato dos dados não é reconhecido/)).toBeVisible();
  });
});

describe("reabrir no Laboratório", () => {
  it("numa sessão nova, devolve formulário e resultado sem chamar a API de cálculo", async () => {
    const { user, fetchMock, view } = await setup();
    // valores diferentes dos padrões, para provar que voltam do registro e não do formulário
    const lambda = screen.getByLabelText(/Chegadas λ/);
    await user.clear(lambda);
    await user.type(lambda, "30");
    await user.clear(screen.getByLabelText("Semente"));
    await user.type(screen.getByLabelText("Semente"), "77");
    await compare(user);
    await saveLab(user);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // nova sessão: formulário nos padrões e nenhum resultado na tela
    view.unmount();
    window.localStorage.removeItem("qsimulador-theme");
    render(<App />);
    expect(screen.getByLabelText(/Chegadas λ/)).toHaveValue("25");
    expect(screen.getByText("Compare o analítico com a simulação")).toBeVisible();

    await user.click(nav("Histórico"));
    await user.click(await screen.findByRole("button", { name: "Abrir" }));
    await user.click(await screen.findByRole("button", { name: "Reabrir no Laboratório" }));

    expect(nav("Laboratório")).toHaveAttribute("aria-current", "page");
    expect(button("M/M/c/K")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText(/Chegadas λ/)).toHaveValue("30");
    expect(screen.getByLabelText("Servidores c")).toHaveValue("3");
    expect(screen.getByLabelText("Capacidade K")).toHaveValue("6");
    expect(screen.getByLabelText("Semente")).toHaveValue("77");
    expect(screen.queryByText("Compare o analítico com a simulação")).toBeNull();
    expect(screen.getByRole("tablist", { name: "Seções do resultado" })).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(1); // nada foi recalculado
  });

  it("troca de modelo ao reabrir um registro de outro modelo", async () => {
    const records = new FakeRecords(true);
    const { user } = await setup(records);
    await user.click(button("M/M/1"));
    await compare(user);       // a fixture é do M/M/c/K, mas o registro guarda M/M/1 + o resultado recebido
    await saveLab(user);
    await user.click(button("M/M/c/K"));
    await user.click(nav("Histórico"));
    await user.click(await screen.findByRole("button", { name: "Abrir" }));
    await user.click(await screen.findByRole("button", { name: "Reabrir no Laboratório" }));
    expect(button("M/M/1")).toHaveAttribute("aria-pressed", "true");
  });
});

describe("experimentos e dados reais", () => {
  it("salva uma varredura e a mostra de novo no Histórico", async () => {
    const { user, records } = await setup();
    await user.click(button("M/M/1"));
    await user.click(nav("Experimentos"));
    await user.click(screen.getByRole("button", { name: "Gerar curva" }));
    await user.click(await screen.findByRole("button", { name: "Salvar no histórico" }));
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    await screen.findByText(/Salvo\./);

    const saved = records.store[0];
    expect(saved.kind).toBe("experiment");
    expect(saved.title).toMatch(/^Varredura de .+ · M\/M\/1$/);
    expect(saved.params).toMatchObject({ origin: "experiment", experiment: "sweep", model: "mm1" });
    expect(saved.params.request).toMatchObject({ model: "mm1" });

    await user.click(nav("Histórico"));
    await user.click(await screen.findByRole("button", { name: "Abrir" }));
    const view = await screen.findByLabelText("Registro aberto");
    expect(within(view).getByRole("table")).toBeVisible();
    expect(within(view).queryByRole("button", { name: "Reabrir no Laboratório" })).toBeNull();
  });

  it("salva a análise do JMeter e a mostra de novo no Histórico", async () => {
    const { user, records } = await setup();
    await user.click(nav("Dados reais"));
    await user.upload(screen.getByLabelText("CSV do JMeter"), new File(["timeStamp,elapsed,label,success\n1,1,A,true\n"], "j.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: /Analisar arquivo/ }));
    await user.click(await screen.findByRole("button", { name: "Salvar no histórico" }));
    await user.click(screen.getByRole("button", { name: "Salvar" }));
    await screen.findByText(/Salvo\./);

    expect(records.store[0].kind).toBe("realdata");
    expect(records.store[0].params).toMatchObject({ origin: "realdata", source: "jtl" });

    await user.click(nav("Histórico"));
    await user.click(await screen.findByRole("button", { name: "Abrir" }));
    const view = await screen.findByLabelText("Registro aberto");
    expect(within(view).getByText(/amostras analisadas/)).toBeVisible();
  });
});
