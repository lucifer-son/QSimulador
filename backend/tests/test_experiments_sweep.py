import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.parametrize(
    "model,base_params",
    [
        ("mm1", {"mu": 10}),
        ("mmc", {"mu": 10, "servers": 2}),
        ("mm1k", {"mu": 10, "capacity": 5}),
        ("mmck", {"mu": 10, "servers": 2, "capacity": 5}),
    ],
)
def test_sweep_calculates_all_supported_models(model, base_params):
    response = client.post(
        "/api/experiments/sweep",
        json={
            "model_type": model,
            "base_params": base_params,
            "sweep_variable": "lambda",
            "start": 1,
            "end": 3,
            "step": 1,
        },
    )

    assert response.status_code == 200
    points = response.json()["points"]
    assert len(points) == 3
    assert all(point["warning"] is None for point in points)
    assert all(point["W"] is not None and point["rho"] is not None for point in points)


@pytest.mark.parametrize(
    "model,base_params,start,end",
    [
        ("mm1", {"mu": 10}, 5, 15),
        ("mmc", {"mu": 10, "servers": 2}, 15, 25),
    ],
)
def test_sweep_reports_unstable_points_without_discarding_stable_points(
    model, base_params, start, end
):
    response = client.post(
        "/api/experiments/sweep",
        json={
            "model_type": model,
            "base_params": base_params,
            "sweep_variable": "lambda",
            "start": start,
            "end": end,
            "step": 5,
        },
    )

    assert response.status_code == 200
    points = response.json()["points"]
    assert points[0]["W"] is not None
    assert points[1]["warning"]
    assert points[1]["W"] is None
    assert points[2]["warning"]
    assert points[2]["W"] is None
