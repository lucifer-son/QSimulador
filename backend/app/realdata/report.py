"""Relatório experimental (RF-44) em Markdown ou HTML, a partir dos resultados já calculados.

Não recalcula nada: recebe o resultado estruturado da análise do JTL (`/analyze`), do
CSV agregado (`/import/levels`) e/ou da comparação (`/compare` ou `/compare-simulated`) e
só os apresenta, com o mesmo conteúdo nos dois formatos. Números no padrão brasileiro
(vírgula decimal).
"""

import html
from datetime import datetime, timezone

SOURCE = {
    "informado": "informado pelo usuário", "menor_nivel": "menor nível de carga (1/R)",
    "autoconsistente": "calibrado pelo próprio tempo de resposta (autoconsistente)",
    "estimado": "estimado pelos dados", "assumido": "assumido",
}
STATUS = {"ok": "ok", "atencao": "atenção", "critico": "crítico", "info": "informativo"}
METRIC_LABEL = {
    "W": "Tempo de resposta W (s)", "throughput": "Vazão X (req/s)",
    "L": "Requisições no sistema L", "p_block": "Probabilidade de bloqueio",
}

Block = tuple[str, object]


def num(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{num(value, digits)}%"


def _yn(value: bool | None) -> str:
    return "—" if value is None else ("sim" if value else "não")


def _when(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%d/%m/%Y %H:%M:%S")


def _analysis_blocks(a: dict) -> list[Block]:
    ds, est, ov = a["dataset"], a["estimates"], a["overall"]
    rec = a["recommended"] or a["nearest"]
    blocks: list[Block] = [
        ("h2", "1. Dados do teste"),
        ("p", f"{num(ds['rows'], 0)} amostras no arquivo; {num(ds['rows_analyzed'], 0)} analisadas. "
              f"Rótulos: {', '.join(ds['labels']) or '—'}. Período: {_when(ds['start'])} a {_when(ds['end'])} (UTC). "
              f"Sistema classificado como {'fechado' if a['system_type'] == 'closed' else 'aberto'}."),
        ("table", (["Medida (janela estável)", "Valor"], [
            ["Vazão X̂", f"{num(ov['throughput'])} req/s"],
            ["Taxa de chegada λ̂", f"{num(ov['arrival_rate'])} req/s"],
            ["Tempo médio de resposta W̄", f"{num(ov['mean_response'])} s"],
            ["p90 / p95 / p99", " / ".join(num(ov[k], 3) for k in ("p90", "p95", "p99")) + " s"],
            ["Requisições em andamento L̂", num(ov["mean_in_flight"])],
            ["Usuários médios N̄", num(ov["mean_users"], 1)],
            ["Rejeições", pct(ov["p_block"] * 100)], ["Erros funcionais", pct(ov["p_error"] * 100)],
        ])),
        ("h2", "2. Recomendação"),
    ]
    if a["status"] == "recommended" and a["recommended"]:
        blocks.append(("p", f"Modelo recomendado: {a['recommended']['notation']} (confiança {a['confidence']})."))
    else:
        blocks.append(("p", "Nenhum modelo do catálogo se ajusta bem"
                            + (f"; o mais próximo é {a['nearest']['notation']}." if a["nearest"] else ".")))
    blocks.append(("p", a["rationale"]))
    if rec:
        blocks.append(("p", f"Parâmetros do modelo: μ = {num(rec['mu'])} req/s, c = {rec['servers']}"
                            + (f", K = {rec['capacity']}" if rec.get("capacity") else "")
                            + (f", N = {rec['population']}" if rec.get("population") else "")
                            + (f", Z = {num(rec['think_time'])} s." if rec.get("think_time") is not None else ".")))
    blocks += [
        ("h2", "3. Estimativas e origem de cada parâmetro"),
        ("table", (["Parâmetro", "Valor", "Origem"], [
            ["μ (req/s)", num(est["mu"]), SOURCE.get(est["mu_source"], est["mu_source"])],
            ["Servidores c", str(est["servers"]), SOURCE.get(est["servers_source"], est["servers_source"])],
            ["Tempo de reflexão Z (s)", num(est["think_time"]), SOURCE.get(est["think_source"] or "", "—")],
            ["Capacidade K", "—" if est["capacity"] is None else str(est["capacity"]), SOURCE.get(est["capacity_source"] or "", "—")],
        ])),
    ]
    if est["notes"]:
        blocks.append(("ul", list(est["notes"])))
    blocks += [
        ("h2", "4. Ranking dos modelos"),
        ("table", (["Modelo", "Elegível", "Erro (%)", "Penalidade (p.p.)", "Escore", "Recomendado"], [
            [r["notation"], _yn(r["eligible"]), num(r["error_pct"], 2), num(r["penalty_pp"], 1),
             num(r["score_pct"], 2), _yn(r["recommended"])] for r in a["ranking"]
        ])),
        ("p", "Critérios que reprovaram cada modelo:"),
        ("ul", [f"{r['notation']}: " + "; ".join(c["reason"] for c in r["criteria"] if not c["passed"])
                for r in a["ranking"] if any(not c["passed"] for c in r["criteria"])] or ["Nenhum critério reprovou."]),
        ("h2", "5. Diagnósticos dos dados"),
        ("table", (["Verificação", "Situação", "Evidência"], [
            [f"{d['id']} — {d['title']}", STATUS.get(d["status"], d["status"]), d["evidence"]] for d in a["diagnostics"]
        ])),
    ]
    if len(a["levels"]) > 1 or a["levels"][0]["users"]:
        blocks += [("h2", "6. Níveis de carga medidos"), _levels_table(a["levels"])]
    return blocks


def _levels_table(levels: list[dict]) -> Block:
    return ("table", (["Usuários", "Amostras", "X̂ (req/s)", "W̄ (s)", "p90 (s)", "Erros"], [
        [str(lv["users"] or "—"), num(lv["metrics"]["samples"], 0), num(lv["metrics"]["throughput"]),
         num(lv["metrics"]["mean_response"]), num(lv["metrics"].get("p90")), pct(lv["metrics"]["p_error"] * 100)]
        for lv in levels
    ]))


def _comparison_blocks(comparison: list[dict], notation: str | None, sim: dict | None, number: str) -> list[Block]:
    has_sim = sim is not None
    head = ["Usuários", "Métrica", "Modelo", "Medido", "IC do medido", "Erro", "Modelo no IC?"]
    if has_sim:
        head += ["Simulação", "IC da simulação", "Erro (sim.)", "Simulação no IC do medido?"]
    rows = []
    for lv in comparison:
        for name, m in lv["metrics"].items():
            ci = "—" if m["observed_ci_low"] is None else f"[{num(m['observed_ci_low'])}; {num(m['observed_ci_high'])}]"
            row = [str(lv["users"] or "janela"), METRIC_LABEL.get(name, name), num(m["model"]), num(m["observed"]),
                   ci, pct(m["relative_error_pct"]), _yn(m["model_within_observed_ci"])]
            if has_sim:
                sci = "—" if m.get("simulated_ci_low") is None else f"[{num(m['simulated_ci_low'])}; {num(m['simulated_ci_high'])}]"
                row += [num(m.get("simulated_mean")), sci, pct(m.get("simulated_error_pct")),
                        _yn(m.get("simulation_within_observed_ci"))]
            rows.append(row)
    blocks: list[Block] = [("h2", f"{number}. Medido × modelo{f' {notation}' if notation else ''}"), ("table", (head, rows)),
        ("p", "Erro = |modelo − medido| / medido. L̂ ≈ X̂·W̄ vale por definição (lei de Little): não é uma validação independente.")]
    if has_sim:
        blocks.append(("p", f"Simulação: {sim['replications']} réplicas de {num(sim['simulation_time'], 0)} s, warm-up "
                            f"{num(sim['warmup_time'], 0)} s, semente-base {sim['seed']} (o nível i usa semente-base + i), "
                            f"confiança {num(sim['confidence_level'] * 100, 0)}%."))
    return blocks


def _levels_import_blocks(imported: dict) -> list[Block]:
    s = imported["suggestions"]
    return [
        ("h2", "1. Dados de entrada (CSV agregado por nível de carga)"),
        ("table", (["Usuários", "Tempo médio (s)", "p90 (s)", "Vazão (req/s)", "Erros"], [
            [str(lv["users"]), num(lv["metrics"]["mean_response"]), num(lv["metrics"].get("p90")),
             num(lv["metrics"]["throughput"]), pct(lv["metrics"]["p_error"] * 100)] for lv in imported["levels"]
        ])),
        ("p", f"Calibração sugerida no menor nível ({s['base_users']} usuário(s)): μ = {num(s['mu'])} req/s, "
              f"Z = {num(s['think_time'])} s."),
        ("ul", list(imported["warnings"])),
    ]


def _jmeter_summary_blocks(summary: dict, comparison: dict | None) -> list[Block]:
    blocks: list[Block] = [
        ("h2", "1. Dados medidos"),
        ("table", (["Medida", "Valor"], [
            ["Amostras totais / usadas", f"{summary['samples_total']} / {summary['samples_used']}"],
            ["Vazão X (req/s)", num(summary["throughput"])],
            ["Tempo médio de resposta W (s)", num(summary["mean_ms"] / 1000)],
            ["Usuários", str(summary.get("users") or "—")],
        ])),
    ]
    if comparison is None:
        return blocks

    blocks += [
        ("h2", f"2. Comparação com o modelo {comparison['model']}"),
        ("table", (["Métrica", "Medido", "Modelo", "Erro", "Medido no IC?"], [
            [METRIC_LABEL.get(name, name), num(metric["measured"]), num(metric["analytical"]),
             pct(metric.get("analytical_error_pct")), _yn(metric.get("measured_within_ci"))]
            for name, metric in comparison["metrics"].items()
        ])),
        ("p", "L é medido derivado pela lei de Little; não é uma validação independente."),
    ]
    simulation = comparison.get("simulation")
    if simulation:
        blocks.append(("p", f"Simulação: {simulation['replications']} réplicas, semente "
                            f"{simulation.get('seed')} (semente-base)."))
    if comparison.get("warnings"):
        blocks += [("h2", "3. Avisos e limitações"), ("ul", comparison["warnings"])]
    return blocks


def _levels_comparison_blocks(comparison: dict) -> list[Block]:
    blocks: list[Block] = [
        ("h2", "1. Comparação por nível de carga"),
        ("table", (["Usuários", "Métrica", "Medido", "Modelo", "Erro"], [
            [str(level["users"]), name, num(metric["measured"]), num(metric["analytical"]),
             pct(metric.get("analytical_error_pct"))]
            for level in comparison["levels"]
            for name, metric in (("Vazão", level["throughput"]), ("Resposta", level["W"]))
        ])),
        ("p", "A calibração usa a lei da resposta interativa."),
    ]
    if comparison.get("warnings"):
        blocks.append(("ul", comparison["warnings"]))
    return blocks


def build_blocks(title: str, analysis: dict | None, levels_import: dict | None,
                 comparison: dict | None) -> list[Block]:
    blocks: list[Block] = [("h1", title), ("p", f"Gerado pelo QSimulador em {datetime.now(timezone.utc):%d/%m/%Y %H:%M} (UTC).")]
    next_number = 1
    if analysis and "samples_total" in analysis and "dataset" not in analysis:
        legacy_comparison = next(
            (item for item in (levels_import, comparison)
             if item and "metrics" in item and "model" in item),
            None,
        )
        blocks += _jmeter_summary_blocks(analysis, legacy_comparison)
        return blocks
    if comparison and "levels" in comparison and "model" in comparison and "comparison" not in comparison:
        blocks += _levels_comparison_blocks(comparison)
        return blocks
    if analysis:
        blocks += _analysis_blocks(analysis)
        next_number = 7 if len(analysis["levels"]) > 1 or analysis["levels"][0]["users"] else 6
    elif levels_import:
        blocks += _levels_import_blocks(levels_import)
        next_number = 2
    if comparison:
        blocks += _comparison_blocks(comparison["comparison"], comparison["notation"], comparison.get("simulation"), str(next_number))
        next_number += 1
    elif analysis and analysis["comparison"]:
        chosen = (analysis["recommended"] or analysis["nearest"] or {}).get("notation")
        blocks += _comparison_blocks(analysis["comparison"], chosen, None, str(next_number))
        next_number += 1
    warnings = list((analysis or {}).get("warnings") or [])
    if analysis is None and levels_import:
        warnings += levels_import["warnings"]
    if warnings:
        blocks += [("h2", f"{next_number}. Avisos e limitações"), ("ul", warnings)]
    return blocks


def to_markdown(blocks: list[Block]) -> str:
    out: list[str] = []
    esc = lambda cell: str(cell).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    for kind, content in blocks:
        if kind == "h1":
            out.append(f"# {content}\n")
        elif kind == "h2":
            out.append(f"## {content}\n")
        elif kind == "p":
            out.append(f"{content}\n")
        elif kind == "ul":
            out.append("\n".join(f"- {item}" for item in content) + "\n")  # type: ignore[union-attr]
        elif kind == "table":
            head, rows = content  # type: ignore[misc]
            out.append("| " + " | ".join(esc(h) for h in head) + " |")
            out.append("|" + "|".join("---" for _ in head) + "|")
            out.extend("| " + " | ".join(esc(c) for c in row) + " |" for row in rows)
            out.append("")
    return "\n".join(out)


_CSS = (
    "body{font-family:system-ui,sans-serif;max-width:64rem;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#1a1a1a}"
    "table{border-collapse:collapse;margin:1rem 0;width:100%}th,td{border:1px solid #bbb;padding:.35rem .6rem;text-align:left}"
    "th{background:#eee}h1,h2{line-height:1.2}"
)


def to_html(blocks: list[Block], title: str) -> str:
    e = html.escape
    body: list[str] = []
    for kind, content in blocks:
        if kind in ("h1", "h2", "p"):
            body.append(f"<{kind}>{e(str(content))}</{kind}>")
        elif kind == "ul":
            body.append("<ul>" + "".join(f"<li>{e(i)}</li>" for i in content) + "</ul>")  # type: ignore[union-attr]
        elif kind == "table":
            head, rows = content  # type: ignore[misc]
            body.append(
                "<table><thead><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr></thead><tbody>"
                + "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in row) + "</tr>" for row in rows)
                + "</tbody></table>"
            )
    return (
        f'<!DOCTYPE html>\n<html lang="pt-BR"><head><meta charset="utf-8"><title>{e(title)}</title>'
        f"<style>{_CSS}</style></head><body>\n" + "\n".join(body) + "\n</body></html>\n"
    )


def build_report(fmt: str, title: str, analysis: dict | None, levels_import: dict | None,
                 comparison: dict | None) -> str:
    blocks = build_blocks(title, analysis, levels_import, comparison)
    return to_markdown(blocks) if fmt == "markdown" else to_html(blocks, title)
