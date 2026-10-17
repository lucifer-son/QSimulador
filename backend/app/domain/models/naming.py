"""Nome do modelo em notação de Kendall."""


def queue_model_name(servers: int, capacity: int | None) -> str:
    """Ex.: (1, None) -> "M/M/1"; (3, None) -> "M/M/3"; (3, 10) -> "M/M/3/10"."""
    base = f"M/M/{servers}"
    return base if capacity is None else f"{base}/{capacity}"


def finite_population_model_name(servers: int, population: int) -> str:
    """Ex.: (1, 20) -> "M/M/1//20"; (4, 50) -> "M/M/4//50" (N entre as barras, sem K)."""
    return f"M/M/{servers}//{population}"


def service_model_name(distribution: str) -> str:
    """Um servidor com serviço geral: \"M/D/1\" se determinístico; senão \"M/G/1\"."""
    return "M/D/1" if distribution == "deterministic" else "M/G/1"
