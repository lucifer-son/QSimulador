"""Compatibilidade: os experimentos do M/G/1 agora vivem em `app.experiments.general`.

A lógica passou a servir também ao M/G/c (Fase 11), então ganhou um módulo próprio. Este arquivo
só reexporta os nomes antigos para não quebrar quem já os importava.
"""

from app.experiments.general import (  # noqa: F401
    SHAPE_VARIABLE,
    ServiceSeries,
    ServicesComparisonResult,
    evaluate_mg1_point,
    mg1_experiment_metrics,
    run_mg1_sensitivity,
    run_mg1_sweep,
    run_services_comparison,
    service_at,
    sweepable_variables_mg1,
    validate_mg1_variable,
    validate_service_list,
)
