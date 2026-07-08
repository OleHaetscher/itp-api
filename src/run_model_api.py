from __future__ import annotations

import uvicorn

from src.API.APISpecification import APISpecification
from src.formalmodels.DummyFormalModel import DummyFormalModel


def run_api() -> None:
    """
    Run a REST API exposing one dummy formal model.

    Args:

    Returns:
    """

    model = DummyFormalModel(
        model_id="model_a",
        random_seed=1,
    )

    api = APISpecification(model=model)

    uvicorn.run(
        api.app,
        host="127.0.0.1",
        port=8001,
    )


if __name__ == "__main__":
    run_api()