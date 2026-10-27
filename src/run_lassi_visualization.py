"""
Serve the LASSI state distribution dashboard.

8050 is the first choice. A port already in use makes the dashboard take the
next free one in 8050-8059 and print it, rather than refusing to start over a
port that belongs to something else. ``ITP_VISUALIZATION_PORT`` names one, and
is then obeyed exactly. Nothing else has to agree: unlike the API and its mock
client, a dashboard has no second process that needs to find it.
"""

from __future__ import annotations

from src.formalmodels.LASSIFormalModel import LASSIFormalModel
from src.utils.ports import (
    VISUALIZATION_PORT_CANDIDATES,
    VISUALIZATION_PORT_VARIABLE,
    resolve_port,
)
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
    host = "127.0.0.1"
    port = resolve_port(
        VISUALIZATION_PORT_CANDIDATES,
        VISUALIZATION_PORT_VARIABLE,
        host=host,
    )

    if port != VISUALIZATION_PORT_CANDIDATES[0]:
        print(
            f"\n  Port {VISUALIZATION_PORT_CANDIDATES[0]} is in use, "
            f"serving on {port} instead."
        )

    print(f"\n  LASSI state distribution dashboard  ->  http://{host}:{port}\n")

    visualizer = make_visualizer(host=host, port=port)
    visualizer.run(debug=False)
