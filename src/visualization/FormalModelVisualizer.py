from __future__ import annotations

from typing import Any

from dash import html

from src.formalmodels.BaseFormalModel import BaseFormalModel
from src.visualization.BaseVisualizer import BaseVisualizer


class FormalModelVisualizer(BaseVisualizer):
    """
    Base class for dashboards that visualize a single formal model.

    The dashboard shows the mechanics of one formal model without any
    interaction data, so the model only supplies its parameters and its update
    logic. Model-specific dashboards subclass this and implement build_body.

    Args:

    Returns:
    """

    def validate_source(
        self,
        source: Any,
    ) -> BaseFormalModel:
        """
        Validate the formal model rendered by the dashboard.

        Args:
            source: Formal model rendered by the dashboard.

        Returns:
            Validated formal model.
        """

        if not isinstance(source, BaseFormalModel):
            raise TypeError("FormalModelVisualizer requires a formal model.")

        source.validate_model_interface()

        return source

    @property
    def model(
        self,
    ) -> BaseFormalModel:
        """
        Return the visualized formal model.

        Args:

        Returns:
            Visualized formal model.
        """

        return self.source

    def model_caption(
        self,
    ) -> html.Div:
        """
        Create a caption describing the visualized formal model.

        Args:

        Returns:
            Dash component holding the model description.
        """

        return self.caption(
            {
                "model": self.model.model_id,
                "state space": self.model.state_space,
                "analysis unit": self.model.analysis_unit,
                "dimensions": ", ".join(self.model.dimensions),
            }
        )
