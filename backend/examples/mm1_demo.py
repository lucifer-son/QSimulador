"""Executa o M/M/1 analítico e o simulado e compara os resultados.

Uso (a partir da pasta backend/, com o ambiente virtual ativo):

    python -m examples.mm1_demo
    python -m examples.mm1_demo --lam 40 --mu 50 --time 2000 --reps 10 --warmup 100 --seed 2026

Os valores padrão reproduzem o exemplo do README.
"""

import argparse
import sys

from app.analytical.mm1 import mm1_metrics
from app.domain.validation.errors import QueueValidationError
from app.simulation.mm1 import simulate_mm1

METRICS = ("rho", "L", "Lq", "W", "Wq")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compara o M/M/1 analítico com a simulação de eventos discretos."
    )
    p.add_argument("--lam", type=float, default=40.0, help="taxa de chegada λ (padrão: 40)")
    p.add_argument("--mu", type=float, default=50.0, help="taxa de serviço μ (padrão: 50)")
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
    try:
        exact = mm1_metrics(args.lam, args.mu)
        result = simulate_mm1(
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

    print(f"M/M/1  lambda={args.lam:g}  mu={args.mu:g}  (rho = {exact.rho:.2f})")
    print(
        f"Simulação: T={args.time:g}, warm-up={args.warmup:g}, "
        f"{args.reps} réplicas, semente={result.seed}"
    )
    print()
    level = f"IC {args.confidence:.0%}"
    print(f"{'métrica':<8}{'analítico':>11}{'simulação':>11}   {level:<22}{'erro':>7}")
    for name in METRICS:
        a = getattr(exact, name)
        s = result.summary[name]
        interval = (
            f"[{s.ci_low:.4f}, {s.ci_high:.4f}]" if s.ci_low is not None else "(1 réplica)"
        )
        error = abs(s.mean - a) / a * 100
        print(f"{name:<8}{a:>11.4f}{s.mean:>11.4f}   {interval:<22}{error:>6.2f}%")
    print()
    print(f"vazão observada: {result.summary['throughput'].mean:.3f} (esperado ≈ lambda = {args.lam:g})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
