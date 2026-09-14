from __future__ import annotations

from src.formalmodels.LASSIFormalModel import LASSIFormalModel
from src.visualization.LASSIFormalModelVisualizer import LASSIFormalModelVisualizer


def make_visualizer(
    model_id: str = "model_lassi",
    host: str = "127.0.0.1",
    port: int = 8050,
) -> LASSIFormalModelVisualizer:
    """
    Create the LASSI state distribution dashboard.

    Args:
        model_id: Identifier of the visualized formal model.
        host: Host the dashboard is served on.
        port: Port the dashboard is served on.

    Returns:
        LASSI dashboard.
    """

    model = LASSIFormalModel(model_id=model_id)

    return LASSIFormalModelVisualizer(
        model=model,
        host=host,
        port=port,
    )


if __name__ == "__main__":
    visualizer = make_visualizer()
    visualizer.run(debug=False)
