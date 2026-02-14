import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from acquisition.abstract import (
    AcquisitionMethod,
    OutputFormat,
    Parameters,
    Report,
    SparseInfo,
)
from shared.environment import RECOVERY


class SysdiagnoseMethod(AcquisitionMethod):
    name = "Sysdiagnose and logs"
    description = """System logs and configuration.
    This only acquires system data and unified logs (converted to JSONL)."""

    def available(self) -> bool:
        return not RECOVERY

    def _create_temporary_image(self, report: Report) -> Optional[SparseInfo]:
        # Temporary image is placed in the temporary directory
        base = report.parameters.tmp
        info = self._create_sparse_image(report, base=base, suffix="-temporary")
        self.temporary_image = info
        return info

    def _convert_logs(self, logarchive: Path, temporary_image: SparseInfo) -> int:
        print("\nRunning log show on", logarchive)

        output_file = Path(temporary_image.mount) / "unified_logs.jsonl"

        # Run log show
        command = [
            "log",
            "show",
            "--info",
            "--debug",
            "--signpost",
            "--style",
            "ndjson",
            "--archive",
            f"{logarchive}",
        ]
        status = self._run_dots(command, redirect=output_file)

        return status

    def execute(self, params: Parameters) -> Report:
        # Prepare report
        report = Report(params, self, start_time=datetime.now())
        report.path_details = self._gather_path_info(params.source)
        report.hardware_info = self._gather_hardware_info()
        # Write preliminary report
        self._write_report(report)

        temporary_image = self._create_temporary_image(report)
        if not temporary_image:
            return report

        sysdiagnose_destination = Path(temporary_image.mount)
        folder_name = "sysdiagnose_fuji"
        mount_point = self._find_mount_point(params.source)

        print("\nRunning sysdiagnose ->", sysdiagnose_destination)
        command = [
            "sysdiagnose",
            "-f",
            f"{sysdiagnose_destination}",
            "-A",
            f"{folder_name}",
            "-n",
            "-u",
            "-b",
            "-V",
            f"{mount_point}",
        ]
        status = self._run_status(command)

        if not status == 0:
            return report

        logarchive = sysdiagnose_destination / "unified_logs.logarchive"

        print("\nRunning log collect ->", logarchive)
        command = [
            "log",
            "collect",
            "--output",
            logarchive.as_posix(),
        ]
        status = self._run_status(command)

        if not status == 0:
            return report

        status = self._convert_logs(logarchive, temporary_image)

        if not status == 0:
            return report

        return self._pack_and_hash(report, format=OutputFormat.ZIP)
