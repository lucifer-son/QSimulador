"""Compara o analítico e a simulação de M/M/c, M/M/1/K e M/M/c/K.

Uso (a partir da pasta backend/, com o ambiente virtual ativo):

    python -m examples.queue_demo                                   # M/M/3/6 (padrão)
    python -m examples.queue_demo --servers 10 --lam 8 --mu 1       # M/M/10 (sem --capacity)
    python -m examples.queue_demo --servers 1 --capacity 5 --lam 12 --mu 10   # M/M/1/5

Sem --capacity a fila é ilimitada (M/M/c) e exige lam < servers * mu.
Os valores padrão reproduzem o exemplo do README.
"""

import argparse
import sys

from app.analysis.comparison import compare_queue
from app.domain.models.naming import queue_model_name
from app.domain.validation.errors import QueueValidationError
from app.simulation.results import QUEUE_METRIC_NAMES


def _verdict(within_ci: bool | None) -> str:
    return "-" if within_ci is None else ("sim" if within_ci else "não")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compara o analítico com a simulação de M/M/c, M/M/1/K e M/M/c/K."
    )
    p.add_argument("--lam", type=float, default=25.0, help="taxa de chegada λ (padrão: 25)")
    p.add_argument("--mu", type=float, default=10.0, help="taxa de serviço por servidor μ (padrão: 10)")
    p.add_argument("--servers", type=int, default=3, help="número de servidores c (padrão: 3)")
    p.add_argument("--capacity", type=int, default=6,
                   help="capacidade total K, incluindo os em atendimento (padrão: 6). "
                        "Use --capacity 0 para fila ilimitada (M/M/c)")
    p.add_argument("--time", type=float, default=2000.0, help="tempo simulado por réplica (padrão: 2000)")
    p.add_argument("--reps", type=int, default=10, help="número de réplicas (padrão: 10)")
    p.add_argument("--warmup", type=float, default=100.0, help="período inicial descartado (padrão: 100)")
    p.add_argument("--seed", type=int, default=2026, help="semente aleatória (padrão: 2026)")
    p.add_argument("--confidence", type=float, default=0.95, help="nível do intervalo de confiança (padrão: 0.95)")
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # evita erro de codificação no Windows
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    capacity = args.capacity if args.capacity > 0 else None
    try:
        result = compare_queue(
            args.lam, args.mu, args.servers, capacity,
            simulation_time=args.time,
            replications=args.reps,
            warmup_time=args.warmup,
            seed=args.seed,
            confidence_level=args.confidence,
        )
    except QueueValidationError as exc:
        print(f"Erro: {exc}")
        return 1

    name = queue_model_name(result.servers, result.capacity)
    print(f"{name}  lambda={args.lam:g}  mu={args.mu:g}  servidores={result.servers}  "
          f"capacidade={'ilimitada' if capacity is None else capacity}")
    print(f"Simulação: T={args.time:g}, warm-up={args.warmup:g}, {args.reps} réplicas, semente={result.seed}")
    print()
    level = f"IC {args.confidence:.0%}"
    print(f"{'métrica':<11}{'analítico':>11}{'simulação':>11}   {level:<20}{'erro':>7}   no IC?")
    for metric in QUEUE_METRIC_NAMES:
        m = result.metrics[metric]
        interval = f"[{m.ci_low:.4f}, {m.ci_high:.4f}]" if m.ci_low is not None else "(1 réplica)"
        err = "-" if m.relative_error_pct is None else f"{m.relative_error_pct:.2f}%"
        print(f"{metric:<11}{m.analytical:>11.4f}{m.simulated_mean:>11.4f}   "
              f"{interval:<20}{err:>7}   {_verdict(m.within_ci)}")
    print()
    if result.all_within_ci is not None:
        print(f"todas as métricas dentro do IC: {_verdict(result.all_within_ci)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
