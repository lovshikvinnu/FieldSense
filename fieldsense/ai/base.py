"""LocalLLMAdapter abstraction contract.

Deliberately mirrors fieldsense.domain.contracts.sensor.SensorAdapter: an
optional external resource that may be physically absent, fronted by a
deterministic stand-in, selected at runtime by a factory.
"""

from abc import ABC, abstractmethod

from .models import AINarrative, ExplanationContext


class LocalLLMAdapter(ABC):
    """Abstract interface for offline natural-language explanation backends.

    Implementations MUST NOT alter, recompute, or contradict any deterministic
    value in the supplied ExplanationContext. They translate structured results
    into prose and nothing else.
    """

    @abstractmethod
    def is_available(self) -> bool:
        """Report whether this backend can run right now.

        Checks for required on-disk assets such as an inference binary and
        model weights. Must never raise, so a factory can probe backends
        safely on a machine that has none of them installed.
        """
        pass

    @abstractmethod
    def initialize(self) -> None:
        """Prepare the backend for generation."""
        pass

    @abstractmethod
    def explain(self, context: ExplanationContext) -> AINarrative:
        """Generate a guarded natural-language narrative for the context.

        Must never raise on routine failure. Absent weights, timeouts, and
        safety-guard rejections are reported through the returned
        AINarrative.generation_status so the pipeline always completes.
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Release any resources held by the backend."""
        pass

    def __enter__(self) -> "LocalLLMAdapter":
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.shutdown()
