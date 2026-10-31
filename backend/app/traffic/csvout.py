"""CSV das telas do cruzamento (Fase 13.1): simulação, comparação de planos e varredura.

Formato RFC 4180 (vírgula, ponto decimal, UTF-8 com BOM para o Excel reconhecer os acentos), como o
CSV da comparação de cenários. Vazio = valor que não existe (métrica sem amostra, plano sem comparação).
Tempos em segundos, taxas em veículos por segundo, filas em veículos.
"""

import csv
import io

_VERDICT = {"higher": "aumento", "lower": "reducao", "inconclusive": "inconclusivo"}
_WHO = {"x": "cruzamento", "a1": "aproximacao_1", "a2": "aproximacao_2"}


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
            analytic = ref.get(who, {}).get(name) if who in ("a1", "a2") else (ref.get(name) if who == "x" else None)
            m = m or {}
            w.writerow((_WHO[who], name, _cell(m.get("mean")), _cell(m.get("std")), _cell(m.get("ci_low")),
                        _cell(m.get("ci_high")), _cell(m.get("n")), _cell(analytic if isinstance(analytic, (int, float)) else None),
                        s["seed"], s["simulation_time"], s["warmup_time"], s["confidence_level"]))
    if report.get("series"):
        w.writerow(())
        w.writerow(("serie_temporal", "tempo_s", "fila_a1_media", "fila_a1_ic_inf", "fila_a1_ic_sup",
                    "fila_a2_media", "fila_a2_ic_inf", "fila_a2_ic_sup"))
        ser = report["series"]
        for j, t in enumerate(ser["times"]):
            w.writerow(("", t, *[_cell(ser[k][f][j]) for k in ("a1", "a2") for f in ("mean", "ci_low", "ci_high")]))
    return _done(out)


def compare_csv(result: dict) -> str:
    out, w = _writer()
    s = result["settings"]
    w.writerow(("plano", "papel", "verde_1_s", "verde_2_s", "ciclo_s", "nivel", "metrica", "media", "ic_inferior",
                "ic_superior", "diferenca_media", "diferenca_ic_inferior", "diferenca_ic_superior", "variacao_relativa",
                "veredito", "alertas", "semente", "replicas", "nivel_ic_diferenca"))
    for row in [result["base"], *result["plans"]]:
        head = (row["name"], "base" if row["role"] == "base" else "plano", row["phases"][0]["green"], row["phases"][1]["green"], row["cycle"])
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
    w.writerow(("verde_1_s", "verde_2_s", "saturacao_1", "saturacao_2", "atraso_com_pendentes_media", "atraso_ic_inferior",
                "atraso_ic_superior", "atraso_concluidos_media", "atraso_a1_media", "atraso_a2_media", "ciclos_com_fila_a1",
                "ciclos_com_fila_a2", "atraso_referencia", "contra_o_melhor", "semente", "replicas"))
    for p in result["points"]:
        d = p["intersection"]["delay_censored"] or {}
        w.writerow((p["green"][0], p["green"][1], p["saturation"]["a1"], p["saturation"]["a2"], _cell(d.get("mean")),
                    _cell(d.get("ci_low")), _cell(d.get("ci_high")), _cell((p["intersection"]["delay"] or {}).get("mean")),
                    _cell((p["a1"]["delay_censored"] or {}).get("mean")), _cell((p["a2"]["delay_censored"] or {}).get("mean")),
                    _cell((p["a1"]["overflow_cycles"] or {}).get("mean")), _cell((p["a2"]["overflow_cycles"] or {}).get("mean")),
                    _cell(p["reference_delay"]), _SWEEP_VS.get(p["vs_best"]["verdict"], ""), s["seed"], s["replications"]))
    return _done(out)
