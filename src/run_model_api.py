from __future__ import annotations

import uvicorn

from src.API.APISpecification import APISpecification
from src.converter.ConverterRegistry import make_default_converter_registry
from src.formalmodels.BaseFormalModel import BaseFormalModel
from src.formalmodels.DummyFormalModels import DummySASBFormalModel


def make_model() -> BaseFormalModel:
    """
    Create a new instance of the formal model exposed by the API.

    Args:

    Returns:
        Formal model exposed by the API.
    """

    return DummySASBFormalModel(
        model_id="model_a",
        random_seed=1,
    )


def run_api() -> None:
    """
    Run a REST API exposing one dummy formal model.

    Args:

    Returns:
    """

    api = APISpecification(
        model_factory=make_model,
        converter=make_default_converter_registry(),
    )

    uvicorn.run(
        api.app,
        host="127.0.0.1",
        port=8001,
    )


if __name__ == "__main__":
    run_api()
