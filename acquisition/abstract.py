from datetime import datetime
import hashlib
import os
import re
import subprocess
from abc import ABC, abstractmethod
import sys
import time
from typing import List, Tuple
from dataclasses import dataclass, field
from pathlib import Path

from meta import AUTHOR, VERSION


@dataclass
class Parameters:
    case: str = ""
    examiner: str = ""
    notes: str = ""
    image_name: str = "MacAcquisition"
    source: Path = Path("/")
    tmp: Path = Path("/Volumes/Fuji")
    destination: Path = Path("/Volumes/Fuji")
    sound: bool = True


@dataclass
class PathDetails:
    path: Path
    is_disk: bool = True
    disk_sectors: int = 0
    disk_device: str = ""
    disk_parent: str = ""
    disk_identifier: int = 0
    disk_info: str = ""


@dataclass
class HashedFile:
    path: Path
    md5: str = ""
    sha1: str = ""
    sha256: str = ""


@dataclass
class Report:
    parameters: Parameters
    method: "AcquisitionMethod"
    start_time: datetime = None
    end_time: datetime = None
    path_details: PathDetails = None
    hardware_info: str = ""
    success: bool = False
    output_files: List[Path] = field(default_factory=list)
    result: HashedFile = None


class AcquisitionMethod(ABC):
    name = "Abstract method"
    description = "This method cannot be used directly"

    temporary_path: Path = None
    temporary_volume: str = None
    temporary_mount: str = None
    output_path: Path = None

    def _run_silent(self, arguments: List[str], awake=True) -> Tuple[int, str]:
        # Run a process silently. Return its status code and output.
        if awake:
            arguments = ["caffeinate", "-dimsu"] + arguments

        p = subprocess.run(arguments, capture_output=True, universal_newlines=True)
        return p.returncode, p.stdout

    def _run_process(
        self, arguments: List[str], awake=True, buffer_size=None
    ) -> Tuple[int, str]:
        # Run a process in plain sight. Return its status code and output.
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
            if buffer_size:
                out = p.stdout.read(buffer_size)
            else:
                out = p.stdout.readline()
            sys.stdout.write(out)
            output = output + out

            if p.poll() != None:
                out = p.stdout.read()
                sys.stdout.write(out)
                output = output + out
                break

        return p.returncode, output

    def _run_status(self, arguments: List[str], awake=True, buffer_size=None) -> int:
        # Run a process in plain sight. Return its status code.
        if awake:
            arguments = ["caffeinate", "-dimsu"] + arguments

        p = subprocess.Popen(
            arguments,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
        )

        while True:
            if buffer_size:
                out = p.stdout.read(buffer_size)
            else:
                out = p.stdout.readline()
            sys.stdout.write(out)

            if p.poll() != None:
                out = p.stdout.read()
                sys.stdout.write(out)
                break

        return p.returncode

    def _disk_from_device(self, device: str) -> str:
        if not device.startswith("/dev/disk"):
            return device
        chunk = device[9:].split("s")[0]
        return "/dev/disk" + chunk

    def _find_mount_point(self, path: Path) -> Path:
        path = os.path.realpath(path)
        while not os.path.ismount(path):
            path = os.path.dirname(path)
        return path

    def _gather_path_info(self, path: Path) -> PathDetails:
        is_disk = os.path.ismount(path)
        disk_stats = os.statvfs(path)
        sectors = int(disk_stats.f_blocks * disk_stats.f_frsize / 512)

        disk_device = ""
        if is_disk:
            result, disk_info = self._run_silent(["diskutil", "info", f"{path}"])
            lines = disk_info.splitlines()
            if result == 0:
                disk_device = lines[1].split(":")[1].strip()
            else:
                is_disk = False
        else:
            mount_point = self._find_mount_point(path)
            mount_info = self._gather_path_info(mount_point)
            disk_device = mount_info.disk_device
            disk_info = mount_info.disk_info

        disk_identifier = os.stat(path).st_dev

        details = PathDetails(
            path,
            is_disk=is_disk,
            disk_sectors=sectors,
            disk_device=disk_device,
            disk_parent=self._disk_from_device(disk_device),
            disk_identifier=disk_identifier,
            disk_info=disk_info,
        )
        return details

    def _gather_hardware_info(self) -> str:
        _, hardware_info = self._run_silent(["system_profiler", "SPHardwareDataType"])
        return hardware_info

    def _create_temporary_image(self, report: Report) -> bool:
        params = report.parameters
        output_directory = params.tmp / params.image_name
        output_directory.mkdir(parents=True, exist_ok=True)

        sectors = report.path_details.disk_sectors
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
        last_line = output.strip().split("\n")[-1]
        parts = re.split("\s+", last_line, maxsplit=2)
        self.temporary_volume = parts[0]
        self.temporary_mount = parts[2]

        success = result == 0
        if success:
            report.output_files.append(self.temporary_path)

        return success

    def _detach_temporary_image(self, delay=30, interval=10, attempts=3) -> bool:
        print("\nWaiting to detach temporary image...")
        time.sleep(delay)
        result = False

        i = 1
        while not result:
            result = self._run_status(["hdiutil", "detach", self.temporary_volume])
            if result == 0:
                return True
            i = i + 1
            if i == attempts:
                break
            time.sleep(interval)
        return False

    def _generate_dmg(self, report: Report) -> bool:
        params = report.parameters
        output_directory = params.destination / params.image_name
        output_directory.mkdir(parents=True, exist_ok=True)
        self.output_path = output_directory / f"{params.image_name}.dmg"

        print("\nConverting", self.temporary_path, "->", self.output_path)
        sparseimage = f"{self.temporary_path}"
        dmg = f"{self.output_path}"
        result = self._run_status(
            ["hdiutil", "convert", sparseimage, "-format", "UDZO", "-o", dmg]
        )

        success = result == 0
        if success:
            report.output_files.append(self.output_path)

        return success

    def _compute_hashes(self, path: Path) -> HashedFile:
        print("\nHashing", path)

        total_size = os.stat(path).st_size
        amount = 0
        last_percent = 0
        chunk_size = 16 * 1024

        sha1 = hashlib.sha1()
        sha256 = hashlib.sha256()
        md5 = hashlib.md5()

        # The process needs to be caffeinated manually, because the hashing
        # function is done directly via our Python code. We start a caffeinate
        # instance with a very long duration (7 days) and terminate after the
        # process is completed.

        one_week = 60 * 60 * 24 * 7
        coffee = subprocess.Popen(["caffeinate", "-dimsu", "-t", f"{one_week}"])

        try:
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        print("")
                        break
                    sha1.update(chunk)
                    sha256.update(chunk)
                    md5.update(chunk)

                    amount = amount + chunk_size
                    percent = 100 * amount // total_size
                    if percent > last_percent:
                        print(f"{percent}% ", end="")
                        last_percent = percent
        finally:
            coffee.kill()

        result = HashedFile(
            path, md5=md5.hexdigest(), sha1=sha1.hexdigest(), sha256=sha256.hexdigest()
        )
        return result

    def _write_report(self, report: Report) -> None:
        params = report.parameters
        output_directory = params.destination / params.image_name
        output_directory.mkdir(parents=True, exist_ok=True)
        self.output_report = output_directory / f"{params.image_name}.txt"

        print("\nWriting report file", self.output_report)

        separator = "-" * 80
        with open(self.output_report, "w") as output:
            for line in (
                [
                    "Fuji - Forensic Unattended Juicy Imaging",
                    f"Version {VERSION} by {AUTHOR}",
                    "Acquisition log",
                    separator,
                    f"Case name: {report.parameters.case}",
                    f"Examiner: {report.parameters.examiner}",
                    f"Notes: {report.parameters.notes}",
                    separator,
                    f"Start time: {report.start_time}",
                    f"End time: {report.end_time}",
                    f"Source: {report.parameters.source}",
                    f"Acquisition method: {report.method.name}",
                    separator,
                    report.hardware_info,
                    separator,
                    report.path_details.disk_info,
                    separator,
                    "Generated files:",
                ]
                + [f"    - {file}" for file in report.output_files]
                + [
                    separator,
                    f"Computed hashes ({report.result.path}):",
                    f"    - MD5: {report.result.md5}",
                    f"    - SHA1: {report.result.sha1}",
                    f"    - SHA256: {report.result.sha256}",
                ]
            ):
                output.write(line + "\n")

        print("\nAcquisition completed!")

    def _dmg_and_hash(self, report: Report) -> Report:
        result = self._detach_temporary_image()
        if not result:
            return report

        result = self._generate_dmg(report)
        if not result:
            return report

        # Compute all hashes and mark report as done
        report.result = self._compute_hashes(self.output_path)
        report.success = True
        report.end_time = datetime.now()

        self._write_report(report)
        return report

    @abstractmethod
    def execute(self, params: Parameters) -> Report:
        pass
