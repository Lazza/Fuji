from abc import ABC, abstractmethod

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Parameters:
    case: str = ""
    examiner: str = ""
    notes: str = ""
    source: Path = Path("/")
    tmp: Path = Path("/Volumes/Fuji")
    destination: Path = Path("/Volumes/Fuji")


class AcquisitionMethod(ABC):
    name = "Abstract method"
    description = "This method cannot be used directly"

    @abstractmethod
    def execute(self, params: Parameters):
        pass
