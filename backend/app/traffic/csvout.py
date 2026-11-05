"""CSV das telas do cruzamento (Fase 13.1): simulação, comparação de planos e varredura.

Formato RFC 4180 (vírgula, ponto decimal, UTF-8 com BOM para o Excel reconhecer os acentos), como o
CSV da comparação de cenários. Vazio = valor que não existe (métrica sem amostra, plano sem comparação).
Tempos em segundos, taxas em veículos por segundo, filas em veículos.
"""

import csv
import io

_VERDICT = {"higher": "aumento", "lower": "reducao", "inconclusive": "inconclusivo"}
_WHO = {"x": "cruzamento", "a1": "aproximacao_1", "a2": "aproximacao_2", "a3": "aproximacao_3", "a4": "aproximacao_4"}
_KEYS = ("a1", "a2", "a3", "a4")


def _cell(value: object) -> object:
    return "" if value is None else value


def _writer():
    out = io.StringIO()
    return out, csv.writer(out, lineterminator="\r\n")


def _done(out: io.StringIO) -> str:
    return "\ufeff" + out.getvalue()


def simulate_csv(report: dict) -> str:
    out, w = _writer()
    s = report["settings"]
    w.writerow(("nivel", "metrica", "media", "desvio", "ic_inferior", "ic_superior", "replicas", "referencia_analitica",
                "semente", "tempo_simulado_s", "aquecimento_s", "nivel_ic"))
    ref = report["reference"]
    for who, metrics in report["metrics"].items():
        for name, m in metrics.items():
            analytic = ref.get(who, {}).get(name) if who in _KEYS else (ref.get(name) if who == "x" else None)
            m = m or {}
            w.writerow((_WHO[who], name, _cell(m.get("mean")), _cell(m.get("std")), _cell(m.get("ci_low")),
                        _cell(m.get("ci_high")), _cell(m.get("n")), _cell(analytic if isinstance(analytic, (int, float)) else None),
                        s["seed"], s["simulation_time"], s["warmup_time"], s["confidence_level"]))
    if report.get("series"):
        w.writerow(())
        present = [k for k in _KEYS if k in report["series"]]
        w.writerow(("serie_temporal", "tempo_s", *[f"fila_{k}_{s}" for k in present for s in ("media", "ic_inf", "ic_sup")]))
        ser = report["series"]
        for j, t in enumerate(ser["times"]):
            w.writerow(("", t, *[_cell(ser[k][f][j]) for k in present for f in ("mean", "ci_low", "ci_high")]))
    return _done(out)


def compare_csv(result: dict) -> str:
    out, w = _writer()
    s = result["settings"]
    n = len(result["base"]["phases"])
    w.writerow(("plano", "papel", *[f"verde_{i + 1}_s" for i in range(n)], "ciclo_s", "nivel", "metrica", "media", "ic_inferior",
                "ic_superior", "diferenca_media", "diferenca_ic_inferior", "diferenca_ic_superior", "variacao_relativa",
                "veredito", "alertas", "semente", "replicas", "nivel_ic_diferenca"))
    for row in [result["base"], *result["plans"]]:
        head = (row["name"], "base" if row["role"] == "base" else "plano", *[p["green"] for p in row["phases"]], row["cycle"])
        alerts = " | ".join(a["message"] for a in row["alerts"]) or (row.get("message") or "")
        tail = (s["seed"], s["replications"], s["diff_confidence_level"])
        if not row["metrics"]:
            w.writerow((*head, "", "", *[""] * 7, alerts, *tail))
            continue
        for who, metrics in row["metrics"].items():
            for name, m in metrics.items():
                sim, diff = m["simulation"] or {}, m["diff"] or {}
                w.writerow((*head, _WHO[who], name, _cell(sim.get("mean")), _cell(sim.get("ci_low")), _cell(sim.get("ci_high")),
                            _cell(diff.get("mean")), _cell(diff.get("ci_low")), _cell(diff.get("ci_high")),
                            _cell(m["relative_change"]), _VERDICT.get(m["verdict"], ""), alerts, *tail))
    return _done(out)


_SWEEP_VS = {"best": "melhor", "worse": "pior", "better": "melhor", "indistinguishable": "indistinguivel", "unknown": ""}


def sweep_csv(result: dict) -> str:
    out, w = _writer()
    s = result["settings"]
    keys = [k for k in _KEYS if k in result["points"][0]] if result["points"] else ["a1", "a2"]
    n = len(keys)
    w.writerow((*[f"verde_{i + 1}_s" for i in range(n)], *[f"saturacao_{i + 1}" for i in range(n)],
                "atraso_com_pendentes_media", "atraso_ic_inferior", "atraso_ic_superior", "atraso_concluidos_media",
                *[f"atraso_{k}_media" for k in keys], *[f"ciclos_com_fila_{k}" for k in keys],
                "atraso_referencia", "contra_o_melhor", "semente", "replicas"))
    for p in result["points"]:
        d = p["intersection"]["delay_censored"] or {}
        w.writerow((*p["green"], *[p["saturation"][k] for k in keys], _cell(d.get("mean")),
                    _cell(d.get("ci_low")), _cell(d.get("ci_high")), _cell((p["intersection"]["delay"] or {}).get("mean")),
                    *[_cell((p[k]["delay_censored"] or {}).get("mean")) for k in keys],
                    *[_cell((p[k]["overflow_cycles"] or {}).get("mean")) for k in keys],
                    _cell(p["reference_delay"]), _SWEEP_VS.get(p["vs_best"]["verdict"], ""), s["seed"], s["replications"]))
    return _done(out)


_TEST_DECISION = {"rejected": "rejeitado", "not_rejected": "nao_rejeitado", "not_evaluated": "nao_avaliado",
                  "equivalent": "equivalente", "not_shown": "equivalencia_nao_demonstrada"}


def validation_csv(result: dict) -> str:
    """Validação (Fase 13.2): resumo por aproximação, intervalo a intervalo e testes de hipótese."""
    out, w = _writer()
    s = result["settings"]
    w.writerow(("resumo", "aproximacao", "metrica", "n", "vies", "erro_medio_absoluto", "rmse", "cobertura_da_faixa",
                "observado", "simulado_media", "simulado_inf", "simulado_sup", "erro_relativo", "nivel_faixa", "semente", "replicas"))
    for key, a in result["approaches"].items():
        for name in ("queue", "departures"):
            e = a.get(name)
            if e:
                w.writerow(("erros", a["approach_id"], {"queue": "fila", "departures": "saidas"}[name], e["n"], e["bias"], e["mae"], e["rmse"],
                            e["coverage"], "", "", "", "", "", s["band_level"], s["seed"], s["replications"]))
        t = a["departures_total"]
        w.writerow(("total_de_saidas", a["approach_id"], "saidas_total", "", "", "", "", "", _cell(t["observed"]), t["mean"], t["low"], t["high"],
                    _cell(t["relative_error"]), s["band_level"], s["seed"], s["replications"]))
        d = a.get("delay")
        if d:
            w.writerow(("atraso", a["approach_id"], "atraso_medio_s", d["observed_n"], "", "", "", "", d["observed_mean"], d["simulated_mean"],
                        d["simulated_low"], d["simulated_high"], "", s["band_level"], s["seed"], s["replications"]))
    w.writerow(())
    w.writerow(("intervalos", "aproximacao", "inicio_s", "fim_s", "fila_observada", "fila_simulada_media", "fila_inf", "fila_sup",
                "saidas_observadas", "saidas_simuladas_media", "saidas_inf", "saidas_sup"))
    for key, a in result["approaches"].items():
        for r in a["intervals"]:
            q, d = r["queue"], r["departures"]
            w.writerow(("", a["approach_id"], r["start"], r["end"], _cell(q["observed"]), q["mean"], q["low"], q["high"],
                        _cell(d["observed"]), d["mean"], d["low"], d["high"]))
    w.writerow(())
    w.writerow(("testes", "aproximacao", "teste", "hipotese_nula", "estatistica", "p_valor", "p_ajustado_holm", "alfa", "decisao", "equivalente", "observacao"))
    for key, a in result["approaches"].items():
        for t in a.get("tests", []):
            eq = t.get("equivalent")
            w.writerow(("", a["approach_id"], t["name"], t["h0"], _cell(t["statistic"]), _cell(t["p_value"]), _cell(t["p_adjusted"]), t["alpha"],
                        _TEST_DECISION.get(t["decision"], ""), "" if eq is None else ("sim" if eq else "nao"), t.get("note") or ""))
    return _done(out)


def sessions_csv(result: dict) -> str:
    """Duas sessões lado a lado (Fase 13.2)."""
    out, w = _writer()
    la, lb = result["labels"]
    w.writerow(("grupo", "grandeza", "unidade", la, lb, "diferenca_b_menos_a", "razao_b_sobre_a", "razao_ic_inferior", "razao_ic_superior", "p_valor", "observacao"))
    for r in result["rows"]:
        ci = r.get("ratio_ci") or ["", ""]
        w.writerow((r["group"], r["name"], r["unit"], _cell(r["a"]), _cell(r["b"]), _cell(r["difference"]), _cell(r["ratio"]), ci[0], ci[1],
                    _cell(r["p_value"]), r.get("note") or ""))
    return _done(out)
