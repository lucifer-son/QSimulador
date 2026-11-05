import { IconPlus, IconTrash } from "@tabler/icons-react";
import {
  blankClass, HEADWAY_LABEL, HEADWAY_ORDER, MAX_CLASSES, MAX_PHASES, MIN_PHASES, resizePhases,
  type ApproachText, type HeadwayDistribution, type PhaseText, type TrafficErrors, type TrafficText,
} from "../domain/traffic";
import { TextField } from "./TextField";

interface Props {
  value: TrafficText;
  errors: TrafficErrors;
  onChange: (next: TrafficText) => void;
}

const cycleOf = (v: TrafficText): string => {
  const numbers = v.phases.flatMap((p) => [p.green, p.amber, p.allRed]).map((s) => Number(s.replace(",", ".")));
  const g = v.phases.every((p) => p.green.trim() !== "");
  return g && numbers.every((n) => Number.isFinite(n)) ? `${numbers.reduce((a, b) => a + b, 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} s` : "—";
};

const sharesOf = (a: ApproachText): number | null => {
  if (a.classes.length === 0) return null;
  const parts = a.classes.map((c) => Number(c.share.replace(",", ".")));
  return parts.every((n) => Number.isFinite(n)) && a.classes.every((c) => c.share.trim() !== "") ? parts.reduce((x, y) => x + y, 0) : null;
};

export function TrafficForm({ value, errors, onChange }: Props) {
  const n = value.phases.length;
  const set = <K extends keyof TrafficText>(key: K, v: TrafficText[K]) => onChange({ ...value, [key]: v });
  const setPhase = (i: number, patch: Partial<PhaseText>) => onChange({ ...value, phases: value.phases.map((p, j) => (j === i ? { ...p, ...patch } : p)) });
  const setApproach = (i: number, patch: Partial<ApproachText>) => onChange({ ...value, approaches: value.approaches.map((a, j) => (j === i ? { ...a, ...patch } : a)) });
  const simple = (key: "offset" | "simulationTime" | "replications" | "warmupTime" | "seed" | "seriesStep", label: string, hint?: string) => (
    <TextField id={`traffic-${key}`} label={label} value={value[key]} error={errors[key]} hint={hint} onChange={(v) => set(key, v)} />
  );

  return (
    <>
      <fieldset className="scenario-card">
        <legend>Semáforo (ciclo fixo, {n} fases)</legend>
        <p className="sub">
          A aproximação i é atendida na fase i; cada movimento com verde próprio (uma conversão protegida, uma terceira via) é uma aproximação.
          Ciclo: <strong>{cycleOf(value)}</strong>.
        </p>
        <div className="grid2">
          {value.phases.map((p, i) => (
            <TextField key={`g${i}`} id={`traffic-green${i + 1}`} label={`Verde da fase ${i + 1} (s)`} value={p.green} error={errors[`green${i + 1}`]}
              onChange={(v) => setPhase(i, { green: v })} />
          ))}
          {value.phases.map((p, i) => (
            <TextField key={`a${i}`} id={`traffic-amber${i + 1}`} label={`Amarelo da fase ${i + 1} (s)`} value={p.amber} error={errors[`amber${i + 1}`]}
              onChange={(v) => setPhase(i, { amber: v })} />
          ))}
          {value.phases.map((p, i) => (
            <TextField key={`r${i}`} id={`traffic-allRed${i + 1}`} label={`Todo-vermelho da fase ${i + 1} (s)`} value={p.allRed} error={errors[`allRed${i + 1}`]}
              onChange={(v) => setPhase(i, { allRed: v })} />
          ))}
        </div>
        <div className="actions">
          <button type="button" className="btn btn-small" disabled={n >= MAX_PHASES} onClick={() => onChange(resizePhases(value, n + 1))}>
            <IconPlus size={14} aria-hidden="true" /> Adicionar fase
          </button>
          <button type="button" className="btn btn-small" disabled={n <= MIN_PHASES} onClick={() => onChange(resizePhases(value, n - 1))}>
            <IconTrash size={14} aria-hidden="true" /> Remover a última fase
          </button>
        </div>
        {simple("offset", "Offset no instante inicial (s)", "Segundos do ciclo já decorridos em t = 0 (0 = o verde da fase 1 começa em t = 0). Vazio = não informado.")}
        {errors.phases && <span className="field-error" role="alert">{errors.phases}</span>}
      </fieldset>

      {value.approaches.map((a, i) => {
        const p = `a${i + 1}.`;
        const id = `traffic-a${i + 1}`;
        const total = sharesOf(a);
        return (
          <fieldset key={i} className="scenario-card">
            <legend>Aproximação {i + 1}</legend>
            <div className="field">
              <label htmlFor={`${id}-name`}>Nome</label>
              <input id={`${id}-name`} value={a.name} onChange={(e) => setApproach(i, { name: e.target.value })} />
            </div>
            {a.profile ? (
              <div className="field">
                <span className="note">
                  Chegadas por blocos vindas do vídeo: {a.profile.length} blocos
                  {a.profile[0]?.count !== undefined ? " (contagens observadas, reproduzidas)" : ` (de ${a.profile.map((b) => b.rate).join("; ")} veíc./min)`}.
                </span>
                <button type="button" className="btn btn-small" onClick={() => setApproach(i, { profile: null })}>Usar uma taxa constante</button>
                {errors[`${p}rate`] && <span className="field-error" role="alert">{errors[`${p}rate`]}</span>}
              </div>
            ) : (
              <TextField id={`${id}-rate`} label="Chegada (veículos/min)" value={a.rate} error={errors[`${p}rate`]}
                hint="Contada no vídeo. Taxa constante durante toda a simulação." onChange={(v) => setApproach(i, { rate: v })} />
            )}
            <div className="field">
              <label htmlFor={`${id}-dist`}>Intervalo entre veículos na descarga</label>
              <select id={`${id}-dist`} value={a.distribution} onChange={(e) => setApproach(i, { distribution: e.target.value as HeadwayDistribution })}>
                {HEADWAY_ORDER.map((d) => <option key={d} value={d}>{HEADWAY_LABEL[d]}</option>)}
              </select>
            </div>
            <div className="grid2">
              <TextField id={`${id}-hm`} label="Média h (s)" value={a.headwayMean} error={errors[`${p}headwayMean`]}
                hint={a.classes.length > 0 ? "Por carro equivalente (um carro = fator 1). Medida no vídeo; sem valor padrão." : "Medida no vídeo; sem valor padrão."}
                onChange={(v) => setApproach(i, { headwayMean: v })} />
              {(a.distribution === "lognormal" || a.distribution === "weibull") && (
                <TextField id={`${id}-hc`} label="CV" value={a.headwayCv} error={errors[`${p}headwayCv`]}
                  onChange={(v) => setApproach(i, { headwayCv: v })} />
              )}
              {a.distribution === "erlang" && (
                <TextField id={`${id}-hk`} label="k (inteiro)" value={a.headwayK} error={errors[`${p}headwayK`]}
                  onChange={(v) => setApproach(i, { headwayK: v })} />
              )}
            </div>
            <div className="grid2">
              <TextField id={`${id}-fv`} label="1º veículo cruza em ℓ (s)" value={a.firstVehicle} error={errors[`${p}firstVehicle`]}
                hint="Do início do verde até o 1º da fila cruzar. Vazio = não informado." onChange={(v) => setApproach(i, { firstVehicle: v })} />
              <TextField id={`${id}-fvcv`} label="CV de ℓ entre ciclos" value={a.firstVehicleCv} error={errors[`${p}firstVehicleCv`]}
                hint="A partida varia de um verde para outro. Vazio ou 0 = ℓ constante." onChange={(v) => setApproach(i, { firstVehicleCv: v })} />
            </div>
            <div className="grid2">
              <TextField id={`${id}-au`} label="Amarelo utilizável (s)" value={a.amberUsable} error={errors[`${p}amberUsable`]}
                hint="Quanto do amarelo ainda se cruza. Vazio = não informado." onChange={(v) => setApproach(i, { amberUsable: v })} />
              <TextField id={`${id}-q0`} label="Fila inicial (veículos)" value={a.initialQueue} error={errors[`${p}initialQueue`]}
                hint="Veículos já esperando em t = 0. Vazio = não informado." onChange={(v) => setApproach(i, { initialQueue: v })} />
            </div>

            <div className="field" role="group" aria-label={`Classes de veículos da aproximação ${i + 1}`}>
              <span className="note">
                Classes de veículos (opcional): cada veículo ocupa a linha por h × fator da sua classe. O fator é a equivalência em carros
                (carro = 1) e <strong>não tem valor padrão</strong>: quem conhece o cruzamento informa. As parcelas somam 1.
              </span>
              {a.classes.map((c, j) => (
                <div key={j} className="grid2">
                  <TextField id={`${id}-cn${j}`} label={`Classe ${j + 1}: nome`} value={c.name} error={errors[`${p}class.${j}.name`]}
                    onChange={(v) => setApproach(i, { classes: a.classes.map((x, k) => (k === j ? { ...x, name: v } : x)) })} />
                  <TextField id={`${id}-cs${j}`} label={`Classe ${j + 1}: parcela (0 a 1)`} value={c.share} error={errors[`${p}class.${j}.share`]}
                    onChange={(v) => setApproach(i, { classes: a.classes.map((x, k) => (k === j ? { ...x, share: v } : x)) })} />
                  <TextField id={`${id}-cf${j}`} label={`Classe ${j + 1}: fator (carros equivalentes)`} value={c.factor} error={errors[`${p}class.${j}.factor`]}
                    onChange={(v) => setApproach(i, { classes: a.classes.map((x, k) => (k === j ? { ...x, factor: v } : x)) })} />
                  <button type="button" className="btn btn-small" onClick={() => setApproach(i, { classes: a.classes.filter((_, k) => k !== j) })}>
                    <IconTrash size={14} aria-hidden="true" /> Remover classe {j + 1}
                  </button>
                </div>
              ))}
              {total !== null && Math.abs(total - 1) > 1e-6 && <span className="field-error" role="alert">As parcelas somam {total.toLocaleString("pt-BR", { maximumFractionDigits: 4 })}, e devem somar 1.</span>}
              <button type="button" className="btn btn-small" disabled={a.classes.length >= MAX_CLASSES}
                onClick={() => setApproach(i, { classes: [...a.classes, blankClass()] })}>
                <IconPlus size={14} aria-hidden="true" /> Adicionar classe
              </button>
            </div>
          </fieldset>
        );
      })}

      <fieldset className="scenario-card">
        <legend>Simulação</legend>
        <div className="grid2">
          {simple("simulationTime", "Tempo simulado T (s)")}
          {simple("replications", "Réplicas")}
          {simple("warmupTime", "Aquecimento (s)", "0 para reproduzir uma gravação.")}
          {simple("seed", "Semente", "Mesma semente, mesmo resultado.")}
        </div>
        {simple("seriesStep", "Passo da série da fila (s)", "Vazio = cerca de 240 pontos.")}
      </fieldset>
    </>
  );
}
