"""Executa o M/M/1 analítico e o simulado e compara os resultados.

Uso (a partir da pasta backend/, com o ambiente virtual ativo):

    python -m examples.mm1_demo
    python -m examples.mm1_demo --lam 40 --mu 50 --time 2000 --reps 10 --warmup 100 --seed 2026

Os valores padrão reproduzem o exemplo do README.
"""

import argparse
import sys

from app.analysis.comparison import compare_mm1
from app.domain.validation.errors import QueueValidationError

METRICS = ("rho", "L", "Lq", "W", "Wq", "p0")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compara o M/M/1 analítico com a simulação de eventos discretos."
    )
    p.add_argument("--lam", type=float, default=40.0, help="taxa de chegada λ (padrão: 40)")
    p.add_argument("--mu", type=float, default=50.0, help="taxa de serviço μ (padrão: 50)")
    p.add_argument("--time", type=float, default=2000.0, help="tempo simulado por réplica (padrão: 2000)")
    p.add_argument("--reps", type=int, default=10, help="número de réplicas, de 2 a 100 (padrão: 10)")
    p.add_argument("--warmup", type=float, default=100.0, help="período inicial descartado (padrão: 100)")
    p.add_argument("--seed", type=int, default=2026, help="semente aleatória (padrão: 2026)")
    p.add_argument("--confidence", type=float, default=0.95, help="nível do intervalo de confiança (padrão: 0.95)")
    return p


def _verdict(within_ci: bool | None) -> str:
    return "-" if within_ci is None else ("sim" if within_ci else "não")


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):  # evita erro de codificação no Windows
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = build_parser().parse_args(argv)
    try:
        result = compare_mm1(
            args.lam,
            args.mu,
            simulation_time=args.time,
            replications=args.reps,
            warmup_time=args.warmup,
            seed=args.seed,
            confidence_level=args.confidence,
        )
    except QueueValidationError as exc:
        print(f"Erro: {exc}")
        return 1

    print(f"M/M/1  lambda={args.lam:g}  mu={args.mu:g}  (rho = {result.metrics['rho'].analytical:.2f})")
    print(
        f"Simulação: T={args.time:g}, warm-up={args.warmup:g}, "
        f"{args.reps} réplicas, semente={result.seed}"
    )
    print()
    level = f"IC {args.confidence:.0%}"
    print(f"{'métrica':<8}{'analítico':>11}{'simulação':>11}   {level:<20}{'erro':>7}   no IC?")
    for name in METRICS:
        m = result.metrics[name]
        interval = (
            f"[{m.ci_low:.4f}, {m.ci_high:.4f}]" if m.ci_low is not None else "(1 réplica)"
        )
        err = f"{m.relative_error_pct:.2f}%"
        print(
            f"{name:<8}{m.analytical:>11.4f}{m.simulated_mean:>11.4f}   "
            f"{interval:<20}{err:>7}   {_verdict(m.within_ci)}"
        )
    print()
    thr = result.metrics["throughput"]
    print(f"vazão observada: {thr.simulated_mean:.3f} (esperado ≈ lambda = {args.lam:g})")
    if result.all_within_ci is not None:
        print(f"todas as métricas dentro do IC: {_verdict(result.all_within_ci)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
