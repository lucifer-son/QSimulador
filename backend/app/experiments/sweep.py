import numpy as np
from typing import List
from app.analytical import mm1, mmck
from app.api.schemas import SweepRequest, SweepPointOut
from app.domain.validation.errors import UnstableSystemError

def run_analytical_sweep(request: SweepRequest) -> List[SweepPointOut]:
    points = []
    
    # Gera o intervalo. Adicionamos (step/2) ao final para garantir que o último número seja incluído.
    sweep_values = np.arange(request.start, request.end + (request.step / 2), request.step)
    
    for val in sweep_values:
        # Copia os parâmetros fixos
        params = request.base_params.copy()

        # Injeta o valor da variável atual (ex: lambda = 15)
        params[request.sweep_variable] = float(val)

        try:
            # Chama a função correta dependendo do modelo
            if request.model_type == "mm1":
                metrics_obj = mm1.mm1_metrics(lam=params["lambda"], mu=params["mu"])
            elif request.model_type == "mmc":
                servers = int(params.get("servers", 1))
                metrics_obj = mmck.mmc_metrics(
                    lam=params["lambda"], mu=params["mu"], servers=servers
                )
            elif request.model_type == "mm1k":
                capacity = int(params.get("capacity", 1))
                metrics_obj = mmck.mm1k_metrics(
                    lam=params["lambda"], mu=params["mu"], capacity=capacity
                )
            elif request.model_type == "mmck":
                servers = int(params.get("servers", 1))
                capacity = int(params.get("capacity", 1))
                metrics_obj = mmck.mmck_metrics(
                    lam=params["lambda"], mu=params["mu"], servers=servers, capacity=capacity
                )
            else:
                raise ValueError(f"Modelo {request.model_type} ainda não implementado na varredura.")

            # Converte o objeto QueueMetrics para um dicionário para podermos extrair os valores
            metrics_dict = metrics_obj.model_dump() if hasattr(metrics_obj, "model_dump") else vars(metrics_obj)

            # Salva o resultado matemático para este ponto da curva
            points.append(SweepPointOut(
                sweep_value=float(val),
                **metrics_dict
            ))

        except UnstableSystemError as e:
            points.append(SweepPointOut(
                sweep_value=float(val),
                warning=str(e)
            ))

    return points
