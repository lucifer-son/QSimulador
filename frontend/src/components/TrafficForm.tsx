import { HEADWAY_LABEL, HEADWAY_ORDER, type ApproachText, type HeadwayDistribution, type TrafficErrors, type TrafficText } from "../domain/traffic";
import { TextField } from "./TextField";

interface Props {
  value: TrafficText;
  errors: TrafficErrors;
  onChange: (next: TrafficText) => void;
}

const cycleOf = (v: TrafficText): string => {
  const parts = [v.green1, v.amber1, v.allRed1, v.green2, v.amber2, v.allRed2].map((s) => Number(s.replace(",", ".")));
  const g = [v.green1, v.green2].every((s) => s.trim() !== "");
  return g && parts.every((n) => Number.isFinite(n)) ? `${parts.reduce((a, b) => a + b, 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 })} s` : "—";
};

export function TrafficForm({ value, errors, onChange }: Props) {
  const set = <K extends keyof TrafficText>(key: K, v: TrafficText[K]) => onChange({ ...value, [key]: v });
  const setApproach = (i: 0 | 1, patch: Partial<ApproachText>) => {
    const next: [ApproachText, ApproachText] = [value.approaches[0], value.approaches[1]];
    next[i] = { ...next[i], ...patch };
    onChange({ ...value, approaches: next });
  };
  const text = (key: keyof TrafficText, label: string, hint?: string) => (
    <TextField id={`traffic-${String(key)}`} label={label} value={value[key] as string} error={errors[key as string]} hint={hint}
      onChange={(v) => set(key, v as never)} />
  );

  return (
    <>
      <fieldset className="scenario-card">
        <legend>Semáforo (ciclo fixo, duas fases)</legend>
        <p className="sub">A aproximação 1 é atendida na fase 1 e a 2 na fase 2. Ciclo: <strong>{cycleOf(value)}</strong>.</p>
        <div className="grid2">
          {text("green1", "Verde da fase 1 (s)")}
          {text("green2", "Verde da fase 2 (s)")}
          {text("amber1", "Amarelo da fase 1 (s)")}
          {text("amber2", "Amarelo da fase 2 (s)")}
          {text("allRed1", "Todo-vermelho da fase 1 (s)")}
          {text("allRed2", "Todo-vermelho da fase 2 (s)")}
        </div>
        {text("offset", "Offset no instante inicial (s)", "Segundos do ciclo já decorridos em t = 0 (0 = o verde da fase 1 começa em t = 0). Vazio = não informado.")}
        {errors.phases && <span className="field-error" role="alert">{errors.phases}</span>}
      </fieldset>

      {value.approaches.map((a, idx) => {
        const i = idx as 0 | 1;
        const p = `a${i + 1}.`;
        const id = `traffic-a${i + 1}`;
        return (
          <fieldset key={i} className="scenario-card">
            <legend>Aproximação {i + 1}</legend>
            <div className="field">
              <label htmlFor={`${id}-name`}>Nome</label>
              <input id={`${id}-name`} value={a.name} onChange={(e) => setApproach(i, { name: e.target.value })} />
            </div>
            {a.profile ? (
              <div className="field">
                <span className="note">Chegadas por blocos vindas do vídeo: {a.profile.length} blocos (de {a.profile.map((b) => b.rate).join("; ")} veíc./min).</span>
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
                hint="Medida no vídeo; sem valor padrão." onChange={(v) => setApproach(i, { headwayMean: v })} />
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
              <TextField id={`${id}-au`} label="Amarelo utilizável (s)" value={a.amberUsable} error={errors[`${p}amberUsable`]}
                hint="Quanto do amarelo ainda se cruza. Vazio = não informado." onChange={(v) => setApproach(i, { amberUsable: v })} />
            </div>
            <TextField id={`${id}-q0`} label="Fila inicial (veículos)" value={a.initialQueue} error={errors[`${p}initialQueue`]}
              hint="Veículos já esperando em t = 0. Vazio = não informado." onChange={(v) => setApproach(i, { initialQueue: v })} />
          </fieldset>
        );
      })}

      <fieldset className="scenario-card">
        <legend>Simulação</legend>
        <div className="grid2">
          {text("simulationTime", "Tempo simulado T (s)")}
          {text("replications", "Réplicas")}
          {text("warmupTime", "Aquecimento (s)", "0 para reproduzir uma gravação.")}
          {text("seed", "Semente", "Mesma semente, mesmo resultado.")}
        </div>
        {text("seriesStep", "Passo da série da fila (s)", "Vazio = cerca de 240 pontos.")}
      </fieldset>
    </>
  );
}
