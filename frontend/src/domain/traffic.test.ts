import { describe, expect, it } from "vitest";
import type { VideoEstimate } from "../api/traffic";
import { fixtures as fx } from "../test/helpers";
import { parseTrafficRecord, trafficRecord } from "./records";
import {
  applyEstimate, blankClass, blankPlan, blankSweep, blankTraffic, buildComparisonBody, buildSweepBody, buildTrafficBody,
  exampleTraffic, formatDelta, formatMetricValue, formatSummary, parseClassFactors, resizePhases, trafficErrors, trafficFieldKey,
  verdictTone, type TrafficText,
} from "./traffic";

const body = (f: TrafficText) => {
  const built = buildTrafficBody(f);
  if (!built.ok) throw new Error(JSON.stringify(built.errors));
  return built.body as Record<string, any>;
};

describe("buildTrafficBody", () => {
  it("converte veículos/min em veículos/s e deixa vazio o que não foi medido (null = não informado)", () => {
    const b = body({ ...exampleTraffic(), offset: "" });
    expect(b.approaches[0].lambda).toBeCloseTo(0.2, 10);
    expect(b.approaches[1].lambda).toBeCloseTo(0.16, 10);
    expect(b.phases[0]).toEqual({ green: 30, amber: 3, all_red: 2 });
    expect(b.offset).toBeNull();
    const blank = { ...exampleTraffic() };
    blank.approaches = [{ ...blank.approaches[0], firstVehicle: "", amberUsable: "", initialQueue: "" }, blank.approaches[1]];
    const a0 = body(blank).approaches[0];
    expect(a0.first_vehicle_time).toBeNull();
    expect(a0.amber_usable).toBeNull();
    expect(a0.initial_queue).toBeNull();
  });

  it("aceita vírgula decimal e monta o intervalo conforme a distribuição", () => {
    const f = exampleTraffic();
    f.approaches[0] = { ...f.approaches[0], rate: "7,5", distribution: "erlang", headwayK: "4", headwayMean: "2,2" };
    f.approaches[1] = { ...f.approaches[1], distribution: "deterministic" };
    const b = body(f);
    expect(b.approaches[0].lambda).toBeCloseTo(0.125, 10);
    expect(b.approaches[0].headway).toEqual({ distribution: "erlang", mean: 2.2, k: 4 });
    expect(b.approaches[1].headway).toEqual({ distribution: "deterministic", mean: 2 });
  });

  it("formulário vazio: pede os dados medidos, com a chave de cada campo", () => {
    const built = buildTrafficBody(blankTraffic());
    expect(built.ok).toBe(false);
    if (built.ok) return;
    expect(Object.keys(built.errors)).toEqual(expect.arrayContaining([
      "green1", "green2", "a1.rate", "a2.rate", "a1.headwayMean", "a2.headwayMean", "a1.headwayCv",
    ]));
    expect(built.errors["a1.headwayMean"]).toMatch(/intervalo médio/);
  });

  it("recusa números inválidos e negativos, com a mensagem do campo", () => {
    const f = exampleTraffic();
    f.phases[0].green = "abc";
    f.phases[0].amber = "-1";
    f.approaches[0].initialQueue = "2,5";
    f.replications = "0";
    const built = buildTrafficBody(f);
    expect(built.ok).toBe(false);
    if (built.ok) return;
    expect(built.errors.green1).toMatch(/número/);
    expect(built.errors.amber1).toMatch(/negativo/);
    expect(built.errors["a1.initialQueue"]).toMatch(/inteiro/);
    expect(built.errors.replications).toMatch(/maior que zero/);
  });

  it("usa o perfil por blocos (vídeo) em vez da taxa constante, convertendo veíc./min", () => {
    const f = exampleTraffic();
    f.approaches[0] = { ...f.approaches[0], rate: "", profile: [{ duration: "900", rate: "6" }, { duration: "900", rate: "12" }] };
    const a = body(f).approaches[0];
    expect(a.lambda).toBeUndefined();
    expect(a.profile).toEqual([{ duration: 900, lambda: 0.1 }, { duration: 900, lambda: 0.2 }]);
  });
});

describe("planos e varredura", () => {
  it("monta os planos só com o que foi trocado e exige ao menos uma troca", () => {
    const plan = { ...blankPlan(7, "Mais verde"), phases: [{ green: "38", amber: "", allRed: "" }, { green: "22", amber: "", allRed: "" }] };
    const built = buildComparisonBody(exampleTraffic(), [plan], true);
    expect(built.ok).toBe(true);
    if (!built.ok) return;
    expect(built.body.bonferroni).toBe(true);
    expect(built.body.scenarios).toEqual([{ name: "Mais verde", phases: [{ green: 38 }, { green: 22 }].map((p) => ({ ...p, amber: undefined, all_red: undefined })) }]);

    const empty = buildComparisonBody(exampleTraffic(), [blankPlan(8)], false);
    expect(empty.ok).toBe(false);
    if (!empty.ok) expect(empty.errors["plan.8.green1"]).toMatch(/ao menos um tempo/);
    const none = buildComparisonBody(exampleTraffic(), [], false);
    expect(none.ok).toBe(false);
    if (!none.ok) expect(none.errors.plans).toBeDefined();
  });

  it("a varredura exige o verde mínimo de cada fase (sem valor padrão)", () => {
    const missing = buildSweepBody(exampleTraffic(), blankSweep());
    expect(missing.ok).toBe(false);
    if (!missing.ok) expect(Object.keys(missing.errors)).toEqual(expect.arrayContaining(["minGreen1", "minGreen2"]));
    const ok = buildSweepBody(exampleTraffic(), { ...blankSweep(), minGreen1: "10", minGreen2: "10", step: "5" });
    expect(ok.ok && ok.body.min_green).toEqual([10, 10]);
  });
});

describe("campos de erro da API", () => {
  it("traduz o caminho da API para a chave do campo", () => {
    expect(trafficFieldKey("approaches.1.headway.cv")).toBe("a2.headwayCv");
    expect(trafficFieldKey("approaches.0.lambda")).toBe("a1.rate");
    expect(trafficFieldKey("approaches.0.first_vehicle_time")).toBe("a1.firstVehicle");
    expect(trafficFieldKey("phases.1.all_red")).toBe("allRed2");
    expect(trafficFieldKey("scenarios.1.phases.0.green", [5, 9])).toBe("plan.9.green1");
    expect(trafficFieldKey("min_green")).toBe("minGreen1");
    expect(trafficFieldKey("simulation_time")).toBe("simulationTime");
    expect(trafficErrors([{ field: "approaches.1.headway.cv", message: "x" }])).toEqual({ "a2.headwayCv": "x" });
  });

  it("a fixture real de erro cai no campo certo", () => {
    expect(trafficErrors(fx.errorTrafficHeadway.fields)).toEqual({ "a2.headwayCv": expect.any(String) });
  });
});

describe("formatação", () => {
  it("vazão em veíc./min e frações em %", () => {
    expect(formatMetricValue("throughput", 0.2)).toBe("12,0");
    expect(formatMetricValue("overflow_cycles", 0.25)).toBe("25,0");
    expect(formatMetricValue("delay", null)).toBe("—");
    expect(formatSummary("delay", { mean: 20, ci_low: 18, ci_high: 22.5, n: 5 })).toBe("20,0 [18,0; 22,5]");
    expect(formatDelta("delay", { mean: -3.2, n: 5 })).toBe("−3,20");
  });

  it("o veredito é bom, ruim ou neutro conforme o sentido da métrica", () => {
    expect(verdictTone("lower", "lower")).toBe("good");
    expect(verdictTone("higher", "lower")).toBe("bad");
    expect(verdictTone("higher", "higher")).toBe("good");
    expect(verdictTone("inconclusive", "lower")).toBe("neutral");
    expect(verdictTone(null, "lower")).toBe("neutral");
  });
});

describe("estimativas do vídeo → formulário", () => {
  const estimate = fx.trafficVideoEstimate as unknown as VideoEstimate;

  it("preenche plano, offset, perfil em blocos e o que foi medido", () => {
    const f = applyEstimate(blankTraffic(), estimate);
    expect(f.phases[0].green).toBe("30");
    expect(f.phases[0].amber).toBe("3");
    expect(f.phases[1].allRed).toBe("2");
    expect(f.offset).toBe("17");
    const a = f.approaches[0];
    expect(a.profile).toHaveLength(4);
    expect(a.profile![0].duration).toBe("900");
    expect(Number(a.profile![0].rate)).toBeGreaterThan(8);
    expect(Number(a.headwayMean)).toBeGreaterThan(1.8);
    expect(Number(a.headwayMean)).toBeLessThan(2.2);
    expect(a.initialQueue).toBe("5");
    expect(f.approaches[1].initialQueue).toBe("0");
    expect(f.simulationTime).toBe("3600");
    expect(buildTrafficBody(f).ok).toBe(true);
  });

  it("o que o vídeo não estimou fica vazio (não informado)", () => {
    const partial = JSON.parse(JSON.stringify(estimate)) as VideoEstimate;
    partial.suggested.approaches[0].headway = null;
    partial.suggested.approaches[0].first_vehicle_time = null;
    partial.suggested.approaches[0].amber_usable = null;
    partial.suggested.approaches[0].initial_queue = null;
    const a = applyEstimate(blankTraffic(), partial).approaches[0];
    expect([a.headwayMean, a.firstVehicle, a.amberUsable, a.initialQueue]).toEqual(["", "", "", ""]);
  });
});

describe("registros do histórico", () => {
  const record = (mode: string, result: object) => ({
    id: "1", kind: "traffic" as const, title: "t", created_at: "", updated_at: "", size_bytes: 1, params: { origin: "traffic", mode, request: {} },
    result: result as Record<string, unknown>,
  });

  it("guarda o tipo do resultado e o reabre", () => {
    const saved = trafficRecord("simulate", { simulation_time: 10 }, fx.trafficSimulate);
    expect(saved.kind).toBe("traffic");
    expect(saved.params).toEqual({ origin: "traffic", mode: "simulate", request: { simulation_time: 10 } });
    expect(parseTrafficRecord(record("simulate", fx.trafficSimulate))?.type).toBe("simulate");
    const done = (fx.trafficSweep as { type: string; result?: object }[]).find((e) => e.type === "done")!.result!;
    expect(parseTrafficRecord(record("sweep", done))?.type).toBe("sweep");
    const compare = (fx.trafficCompare as { type: string; result?: object }[]).find((e) => e.type === "done")!.result!;
    expect(parseTrafficRecord(record("compare", compare))?.type).toBe("compare");
    expect(parseTrafficRecord(record("validation", fx.trafficVideoValidate))?.type).toBe("validation");
  });

  it("recusa registro de outra origem ou com resultado que não é o esperado", () => {
    expect(parseTrafficRecord({ ...record("simulate", fx.trafficSimulate), params: { origin: "lab" } })).toBeNull();
    expect(parseTrafficRecord(record("simulate", { foo: 1 }))).toBeNull();
    expect(parseTrafficRecord(record("outro", fx.trafficSimulate))).toBeNull();
  });
});

describe("Fase 13.2: 2 a 4 fases", () => {
  it("resizePhases acrescenta e remove fase e aproximação juntas, entre 2 e 4", () => {
    const f3 = resizePhases(exampleTraffic(), 3);
    expect(f3.phases).toHaveLength(3);
    expect(f3.approaches.map((a) => a.name)).toEqual(["Aproximação 1", "Aproximação 2", "Aproximação 3"]);
    expect(f3.phases[2]).toEqual({ green: "", amber: "", allRed: "" });
    expect(resizePhases(f3, 9).phases).toHaveLength(4);
    expect(resizePhases(f3, 1).phases).toHaveLength(2);
    expect(resizePhases(f3, 2).approaches).toHaveLength(2);
  });

  it("monta o corpo com 3 fases e aponta o campo que falta", () => {
    const f = resizePhases(exampleTraffic(), 3);
    const built = buildTrafficBody(f);
    expect(built.ok).toBe(false);
    if (!built.ok) expect(Object.keys(built.errors)).toEqual(expect.arrayContaining(["green3", "a3.rate", "a3.headwayMean"]));
    const ok = {
      ...f, phases: [...f.phases.slice(0, 2), { green: "18", amber: "3", allRed: "2" }],
      approaches: [...f.approaches.slice(0, 2), { ...f.approaches[0], name: "Esquerda" }],
    };
    const b = body(ok);
    expect(b.phases).toHaveLength(3);
    expect(b.approaches.map((a: any) => a.name)).toEqual(["Aproximação 1", "Aproximação 2", "Esquerda"]);
  });

  it("os planos trocam só o que mudou, uma entrada por fase; a varredura escolhe o par de fases", () => {
    const f = resizePhases(exampleTraffic(), 3);
    f.phases[2] = { green: "18", amber: "3", allRed: "2" };
    f.approaches[2] = { ...f.approaches[0], name: "C" };
    const plan = { ...blankPlan(1, "P", 3), phases: [{ green: "", amber: "", allRed: "" }, { green: "", amber: "", allRed: "" }, { green: "22", amber: "", allRed: "" }] };
    const built = buildComparisonBody(f, [plan], false);
    expect(built.ok).toBe(true);
    if (built.ok) expect((built.body.scenarios as any[])[0].phases).toEqual([null, null, { green: 22, amber: undefined, all_red: undefined }]);
    const sw = buildSweepBody(f, { ...blankSweep(), pair1: "2", pair2: "3", minGreen1: "10", minGreen2: "8" });
    expect(sw.ok && sw.body.pair).toEqual([2, 3]);
    const bad = buildSweepBody(f, { ...blankSweep(), pair1: "2", pair2: "2", minGreen1: "10", minGreen2: "8" });
    expect(!bad.ok && bad.errors.pair2).toMatch(/diferentes/);
    const out = buildSweepBody(f, { ...blankSweep(), pair1: "1", pair2: "5", minGreen1: "10", minGreen2: "8" });
    expect(!out.ok && out.errors.pair2).toMatch(/entre 1 e 3/);
    const classic = buildSweepBody(exampleTraffic(), { ...blankSweep(), minGreen1: "10", minGreen2: "10" });
    expect(classic.ok && classic.body.pair).toBeUndefined();
  });

  it("traduz os campos da API para as fases 3 e 4, as classes e o CV de ℓ", () => {
    expect(trafficFieldKey("phases.2.green")).toBe("green3");
    expect(trafficFieldKey("phases.3.all_red")).toBe("allRed4");
    expect(trafficFieldKey("approaches.2.first_vehicle_cv")).toBe("a3.firstVehicleCv");
    expect(trafficFieldKey("approaches.0.classes.1.share")).toBe("a1.class.1.share");
    expect(trafficFieldKey("approaches.0.classes")).toBe("a1.class.0.share");
    expect(trafficFieldKey("scenarios.0.phases.2.green", [7])).toBe("plan.7.green3");
    expect(trafficFieldKey("pair")).toBe("pair1");
  });
});

describe("Fase 13.2: classes de veículos", () => {
  const withClasses = () => {
    const f = exampleTraffic();
    f.approaches[0] = {
      ...f.approaches[0],
      classes: [{ name: "carro", share: "0,7", factor: "1" }, { name: "moto", share: "0,2", factor: "0,35" }, { name: "ônibus", share: "0,1", factor: "2,2" }],
      firstVehicleCv: "0,3",
    };
    return f;
  };

  it("manda as classes e o CV de ℓ para a API, com vírgula decimal", () => {
    const b = body(withClasses());
    expect(b.approaches[0].classes).toEqual([
      { name: "carro", share: 0.7, factor: 1 }, { name: "moto", share: 0.2, factor: 0.35 }, { name: "ônibus", share: 0.1, factor: 2.2 },
    ]);
    expect(b.approaches[0].first_vehicle_cv).toBeCloseTo(0.3);
    expect(b.approaches[1].classes).toBeUndefined();
  });

  it("exige nome, parcela e fator: não há valor padrão", () => {
    const f = exampleTraffic();
    f.approaches[0].classes = [blankClass()];
    const built = buildTrafficBody(f);
    expect(built.ok).toBe(false);
    if (!built.ok) expect(Object.keys(built.errors)).toEqual(expect.arrayContaining(["a1.class.0.name", "a1.class.0.share", "a1.class.0.factor"]));
    f.approaches[0].classes = [{ name: "moto", share: "1", factor: "0" }];
    const zero = buildTrafficBody(f);
    expect(!zero.ok && zero.errors["a1.class.0.factor"]).toMatch(/maior que zero/);
  });

  it("parseClassFactors lê nome=fator com vírgula decimal e recusa o resto", () => {
    expect(parseClassFactors("")).toBeNull();
    expect(parseClassFactors("carro=1; moto=0,35\nônibus = 2.2")).toEqual({ carro: 1, moto: 0.35, ônibus: 2.2 });
    expect(parseClassFactors("moto=0")).toMatch(/Fator inválido/);
    expect(parseClassFactors("moto")).toMatch(/nome=fator/);
    expect(parseClassFactors("moto=abc")).toMatch(/Fator inválido/);
  });

  const estimate = fx.trafficVideoEstimateClasses as unknown as VideoEstimate;

  it("o vídeo com 3 aproximações e classes preenche o formulário inteiro", () => {
    const f = applyEstimate(blankTraffic(), estimate);
    expect(f.phases).toHaveLength(3);
    expect(f.approaches.map((a) => a.name)).toEqual(["N", "L", "E"]);
    expect(f.approaches[0].classes.map((c) => c.name)).toEqual(["carro", "moto", "ônibus"]);
    expect(f.approaches[0].classes[1].factor).toBe("0.35");
    expect(f.approaches[0].profile![0].count).toBeUndefined();
    expect(f.approaches[0].firstVehicleCv).not.toBe("");
  });

  it("reproduzir as contagens leva `count` e `class_counts` do vídeo no corpo", () => {
    const f = applyEstimate(blankTraffic(), estimate, true);
    const block = f.approaches[0].profile![0];
    expect(block.count).toBeDefined();
    expect(Object.keys(block.classCounts!)).toEqual(["carro", "moto", "ônibus"]);
    const full = { ...f, approaches: f.approaches.map((a) => ({ ...a, amberUsable: a.amberUsable || "0", initialQueue: a.initialQueue || "0" })) };
    const b = body(full);
    const sent = b.approaches[0].profile[0];
    expect(sent.count).toBe(Number(block.count));
    expect(sent.lambda).toBeUndefined();
    expect(Object.values(sent.class_counts).reduce((x: number, y: any) => x + y, 0)).toBe(sent.count);
  });
});
