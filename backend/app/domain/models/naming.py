"""Nome do modelo em notação de Kendall."""


def queue_model_name(servers: int, capacity: int | None) -> str:
    """Ex.: (1, None) -> "M/M/1"; (3, None) -> "M/M/3"; (3, 10) -> "M/M/3/10"."""
    base = f"M/M/{servers}"
    return base if capacity is None else f"{base}/{capacity}"
