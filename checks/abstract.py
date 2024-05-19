from abc import ABC, abstractmethod
from dataclasses import dataclass

from acquisition.abstract import Parameters


@dataclass
class CheckResult:
    passed: bool = True
    message: str = ""

    def write(self, content: str):
        if self.message:
            self.message = self.message + "\n" + content
        else:
            self.message = content


class Check(ABC):
    name = "Abstract check"

    @abstractmethod
    def execute(self, params: Parameters) -> CheckResult:
        pass
