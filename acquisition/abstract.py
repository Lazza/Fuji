import os
import subprocess
from abc import ABC, abstractmethod
import sys
import time
from typing import List, Tuple
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Parameters:
    case: str = ""
    examiner: str = ""
    notes: str = ""
    image_name: str = "FujiAcquisition"
    source: Path = Path("/")
    tmp: Path = Path("/Volumes/Fuji")
    destination: Path = Path("/Volumes/Fuji")


class AcquisitionMethod(ABC):
    name = "Abstract method"
    description = "This method cannot be used directly"

    temporary_path: Path = None
    temporary_volume: str = None
    output_path: Path = None

    def _run_process(self, arguments: List[str], awake=True) -> Tuple[int, str]:
        if awake:
            arguments = ["caffeinate", "-dimsu"] + arguments

        p = subprocess.Popen(
            arguments,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )

        output = ""
        while True:
            out = p.stdout.read(1)
            sys.stdout.write(out)
            output = output + out

            if p.poll() != None:
                out = p.stdout.read()
                sys.stdout.write(out)
                output = output + out
                break

        return p.returncode, output

    def _create_temporary_image(self, params: Parameters) -> bool:
        output_directory = params.tmp / params.image_name
        output_directory.mkdir(parents=True, exist_ok=True)

        disk_stats = os.statvfs(params.source)
        sectors = int(disk_stats.f_blocks * disk_stats.f_frsize / 512)
        self.temporary_path = output_directory / f"{params.image_name}.sparseimage"

        image_path: str = f"{self.temporary_path}"
        self.temporary_volume = None
        result, output = self._run_process(
            [
                "hdiutil",
                "create",
                "-sectors",
                f"{sectors}",
                "-volname",
                params.image_name,
                image_path,
            ],
        )
        if result > 0:
            return False

        result, output = self._run_process(["hdiutil", "attach", image_path])
        self.temporary_volume = output.strip().split(" ")[0]

        return result == 0

    def _detach_temporary_image(self, delay=30, interval=10, attempts=3) -> bool:
        time.sleep(delay)
        result = False

        i = 1
        while not result:
            result, _ = self._run_process(["hdiutil", "detach", self.temporary_volume])
            if result == 0:
                return True
            i = i + 1
            if i == attempts:
                break
            time.sleep(interval)
        return False

    def _generate_dmg(self, params: Parameters) -> bool:
        output_directory = params.destination / params.image_name
        output_directory.mkdir(parents=True, exist_ok=True)
        self.output_path = output_directory / f"{params.image_name}.dmg"

        print("\nConverting", self.temporary_path, "->", self.output_path)
        sparseimage = f"{self.temporary_path}"
        dmg = f"{self.output_path}"
        result, _ = self._run_process(
            ["hdiutil", "convert", sparseimage, "-format", "UDZO", "-o", dmg]
        )
        return result == 0

    @abstractmethod
    def execute(self, params: Parameters) -> bool:
        pass
