"""CSV da comparação de cenários: uma linha por cenário e métrica.

Formato RFC 4180 (vírgula, ponto decimal, UTF-8 com BOM para o Excel reconhecer os acentos). No Excel
em português, abra por Dados → De Texto/CSV, que deixa escolher o separador e o decimal. Os vazios
são valores que não existem (métrica fora do modelo, base sem comparação, cenário não simulado).
"""

import csv
import io

from app.simulation.results import QUEUE_METRIC_NAMES

HEADER = (
    "cenario", "papel", "modelo", "status", "metrica",
    "analitico", "simulacao_media", "simulacao_ic_inferior", "simulacao_ic_superior",
    "diferenca_analitica", "diferenca_media", "diferenca_ic_inferior", "diferenca_ic_superior",
    "variacao_relativa", "veredito", "alertas",
    "semente", "replicas", "nivel_ic_diferenca",
)
_STATUS = {"ok": "ok", "unstable": "instavel", "error": "erro"}
_VERDICT = {"higher": "aumento", "lower": "reducao", "inconclusive": "inconclusivo"}
_ROLE = {"base": "base", "scenario": "cenario"}


def _cell(value: object) -> object:
    return "" if value is None else value


def comparison_csv(result: dict) -> str:
    """Texto do CSV (com BOM) a partir do resultado completo da comparação."""
    settings = result["settings"]
    tail = [settings["seed"], settings["replications"], settings["diff_confidence_level"]]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(HEADER)
    for row in [result["base"], *result["scenarios"]]:
        head = [row["name"], _ROLE[row["role"]], row["model_label"], _STATUS[row["status"]]]
        alerts = " | ".join(a["message"] for a in row["alerts"]) or (row["message"] or "")
        if not row["metrics"]:
            writer.writerow([*head, "", *[""] * 10, alerts, *tail])
            continue
        for name in QUEUE_METRIC_NAMES:
            m = row["metrics"].get(name)
            if m is None:
                continue
            sim, diff = m["simulation"] or {}, m["diff"] or {}
            writer.writerow([
                *head, name, _cell(m["analytic"]),
                _cell(sim.get("mean")), _cell(sim.get("ci_low")), _cell(sim.get("ci_high")),
                _cell(m["analytic_diff"]),
                _cell(diff.get("mean")), _cell(diff.get("ci_low")), _cell(diff.get("ci_high")),
                _cell(m["relative_change"]), _VERDICT.get(m["verdict"], ""), alerts, *tail,
            ])
    return "\ufeff" + out.getvalue()
