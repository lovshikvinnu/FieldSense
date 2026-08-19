"""Abstract base contract for recommendation rules."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

from fieldsense.zones.models import Zone
from fieldsense.recommendations.models import Recommendation


class RecommendationRule(ABC):
    """Abstract contract interface for recommendation evaluation rules."""

    @abstractmethod
    def evaluate(self, zone: Zone, context: Dict[str, Any]) -> List[Recommendation]:
        """Evaluate a zone and context to produce structured recommendations.

        Args:
            zone: Target management zone.
            context: Pipeline evaluation context.

        Returns:
            List of Recommendation objects.
        """
        pass
