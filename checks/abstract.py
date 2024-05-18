from abc import ABC, abstractmethod
from dataclasses import dataclass

from acquisition.abstract import Parameters


@dataclass
class CheckResult:
    passed: bool = True
    message: str = ""


class Check(ABC):
    name = "Abstract check"

    @abstractmethod
    def execute(self, params: Parameters) -> CheckResult:
        pass
