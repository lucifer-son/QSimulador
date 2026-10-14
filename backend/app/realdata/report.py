"""Relatório experimental (Markdown ou HTML) a partir dos resultados já calculados.

Não recalcula nada: recebe os dicionários estruturados da importação e da comparação
e só os apresenta, com o mesmo conteúdo nos dois formatos. Números no padrão brasileiro
(vírgula decimal).
"""

import html
from datetime import datetime, timezone

METRIC_LABELS = {
    "throughput": ("Vazão X", "req/s"),
    "W": ("Tempo de resposta W", "s"),
    "L": ("Usuários no sistema L", ""),
    "rho": ("Utilização ρ", ""),
}
SOURCE_LABELS = {
    "informed": "informado pelo usuário",
    "inverse_response": "1/tempo médio de resposta do próprio teste",
    "baseline": "1/tempo de resposta em carga mínima",
    "interactive_law": "lei da resposta interativa, Z = N/X − R",
}
ROLE_LABELS = {"prediction": "previsão", "input": "entrada do modelo"}


def num(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(value: float | None) -> str:
    return "—" if value is None else f"{num(value, 2)}%"


def _yes_no(value: bool | None) -> str:
    return "—" if value is None else ("sim" if value else "não")


Table = tuple[list[str], list[list[str]]]


def _blocks(
    title: str,
    dataset: dict | None,
    comparison: dict | None,
    levels: dict | None,
) -> list[tuple[str, object]]:
    """Representação neutra do relatório: lista de (tipo, conteúdo)."""
    blocks: list[tuple[str, object]] = [
        ("h1", title),
        ("p", f"Gerado pelo QSimulador em {datetime.now(timezone.utc):%d/%m/%Y %H:%M} (UTC)."),
    ]
    if dataset:
        d = dataset
        blocks += [
            ("h2", "1. Dados medidos"),
            ("p", f"Amostras no arquivo: {d['samples_total']}; usadas: {d['samples_used']}. "
                  f"Rótulo: {d['label'] or 'todos'}. Janela de medição: {num(d['window_seconds'], 1)} s "
                  f"(descartados {num(d['trim_start_s'], 1)} s no início e {num(d['trim_end_s'], 1)} s no fim). "
                  f"Amostras com falha {'incluídas' if d['include_failures'] else 'excluídas'}."),
            ("table", (["Métrica", "Valor"], [
                ["Vazão", f"{num(d['throughput'])} req/s"],
                ["Tempo médio de resposta", f"{num(d['mean_ms'], 2)} ms"],
                ["Desvio padrão", f"{num(d['std_ms'], 2)} ms"],
                ["p50 / p90 / p95 / p99", " / ".join(num(d[k], 1) for k in ("p50_ms", "p90_ms", "p95_ms", "p99_ms")) + " ms"],
                ["Taxa de erro", pct(d["error_rate"] * 100)],
                ["Usuários (allThreads, mediana)", "—" if d["users"] is None else str(d["users"])],
            ])),
        ]
        if d.get("labels"):
            blocks.append(("table", (["Rótulo", "Amostras", "Média (ms)", "p90 (ms)", "Erros"], [
                [x["label"], str(x["samples"]), num(x["mean_ms"], 2), num(x["p90_ms"], 1), pct(x["error_rate"] * 100)]
                for x in d["labels"]
            ])))
    if comparison:
        c = comparison
        blocks.append(("h2", "2. Modelo e calibração"))
        items = [
            f"Modelo: {c['model']} ({'sistema fechado, população finita' if c['mode'] == 'closed' else 'sistema aberto'}).",
            f"μ = {num(c['mu'])} req/s por servidor ({SOURCE_LABELS.get(c['mu_source'], c['mu_source'])}); servidores: {c['servers']}.",
        ]
        if c["mode"] == "closed":
            items.append(f"N = {c['users']} usuários; tempo de reflexão Z = {num(c['think_time'])} s "
                         f"({SOURCE_LABELS.get(c['think_time_source'], c['think_time_source'])}).")
        else:
            items.append(f"λ = {num(c['arrival_rate'])} req/s (vazão medida).")
        if c.get("simulation"):
            s = c["simulation"]
            items.append(f"Simulação: {s['replications']} réplicas de {num(s['simulation_time'], 0)} s, "
                         f"warm-up {num(s['warmup_time'], 0)} s, semente {s['seed']}, confiança {num(s['confidence_level'] * 100, 0)}%.")
        blocks += [("ul", items), ("h2", "3. Comparação: medido × modelo × simulação")]
        has_sim = bool(c.get("simulation"))
        head = ["Métrica", "Medido", "Analítico", "Erro (analítico)"]
        if has_sim:
            head += ["Simulação", "IC", "Erro (simulação)", "Medido no IC?"]
        head += ["Observação"]
        rows = []
        for key, (label, unit) in METRIC_LABELS.items():
            m = c["metrics"][key]
            row = [f"{label}{' (' + unit + ')' if unit else ''}", num(m["measured"]), num(m["analytical"]), pct(m["analytical_error_pct"])]
            if has_sim:
                ci = "—" if m["ci_low"] is None else f"[{num(m['ci_low'])}; {num(m['ci_high'])}]"
                row += [num(m["simulated_mean"]), ci, pct(m["simulated_error_pct"]), _yes_no(m["measured_within_ci"])]
            note = ROLE_LABELS.get(m["role"], m["role"]) + ("; medido derivado" if m["measured_derived"] else "")
            rows.append(row + [note])
        blocks.append(("table", (head, rows)))
        blocks.append(("p", "Erro = |modelo − medido| / medido. L (Little) e ρ (X/(c·μ)) são derivados das medições. "
                            "O IC é o da média simulada entre réplicas; um único teste medido tem variabilidade própria, "
                            "então cair fora do IC não indica, sozinho, erro do modelo."))
    if levels:
        lv = levels
        blocks += [
            ("h2", "2. Modelo e calibração"),
            ("ul", [
                f"Modelo: {lv['model']} (sistema fechado), {lv['servers']} servidor(es).",
                f"μ = {num(lv['mu'])} req/s ({SOURCE_LABELS.get(lv['mu_source'], lv['mu_source'])}); "
                f"Z = {num(lv['think_time'])} s ({SOURCE_LABELS.get(lv['think_time_source'], lv['think_time_source'])}).",
            ]),
            ("h2", "3. Comparação por nível de carga"),
        ]
        has_sim = bool(lv.get("simulation"))
        head = ["Usuários", "X medida", "X modelo", "Erro X", "W medido (s)", "W modelo (s)", "Erro W"]
        if has_sim:
            head += ["X simulada", "W simulado"]
        rows = []
        for x in lv["levels"]:
            row = [str(x["users"]), num(x["measured_throughput"]), num(x["throughput"]["analytical"]),
                   pct(x["throughput"]["analytical_error_pct"]), num(x["measured_response_s"]),
                   num(x["W"]["analytical"]), pct(x["W"]["analytical_error_pct"])]
            if has_sim:
                row += [num(x["throughput"]["simulated_mean"]), num(x["W"]["simulated_mean"])]
            rows.append(row)
        blocks.append(("table", (head, rows)))
    warnings = (comparison or levels or {}).get("warnings") or []
    if warnings:
        blocks += [("h2", "4. Avisos e limitações"), ("ul", list(warnings))]
    return blocks


def to_markdown(blocks: list[tuple[str, object]]) -> str:
    out: list[str] = []
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
            esc = lambda cell: str(cell).replace("|", "\\|")
            out.append("| " + " | ".join(esc(h) for h in head) + " |")
            out.append("|" + "|".join("---" for _ in head) + "|")
            out.extend("| " + " | ".join(esc(c) for c in row) + " |" for row in rows)
            out.append("")
    return "\n".join(out)


_CSS = (
    "body{font-family:system-ui,sans-serif;max-width:60rem;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#1a1a1a}"
    "table{border-collapse:collapse;margin:1rem 0;width:100%}th,td{border:1px solid #bbb;padding:.35rem .6rem;text-align:left}"
    "th{background:#eee}h1,h2{line-height:1.2}"
)


def to_html(blocks: list[tuple[str, object]], title: str) -> str:
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


def build_report(
    fmt: str,
    title: str,
    dataset: dict | None,
    comparison: dict | None,
    levels: dict | None,
) -> str:
    blocks = _blocks(title, dataset, comparison, levels)
    return to_markdown(blocks) if fmt == "markdown" else to_html(blocks, title)
