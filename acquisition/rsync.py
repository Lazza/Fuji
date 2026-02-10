from datetime import datetime
from pathlib import Path
from typing import List

from acquisition.abstract import AcquisitionMethod, Parameters, Report
from shared.environment import RECOVERY, RSYNC_PATH


class RsyncMethod(AcquisitionMethod):
    name = "Rsync"
    description = """Files and directories are copied using Rsync.
    This is a bit slow but it can be used on any source directory. Errors are ignored."""

    def available(self) -> bool:
        return not RECOVERY

    def _compute_exclusions(self, params: Parameters) -> List[Path]:
        # Rsync can be tricked into acquiring files multiple times by macOS, due
        # to how it handles mount points inside the APFS container. This method
        # aims to prevent acquiring duplicates of the same files.

        _, mount_points = self._run_silent(["mount"])
        lines = mount_points.splitlines()

        source_info = self._gather_path_info(params.source)
        source_disk = source_info.disk_parent

        results = []
        for line in lines:
            if not (line.startswith("/dev/disk") and " on " in line):
                continue
            device = line.split(" on ")[0]
            point = line.split(" on ")[1].split("(")[0].strip()
            point_path = Path(point)
            point_disk = self._disk_from_device(device)

            if point_disk == source_disk and params.source in point_path.parents:
                results.append(point_path)

        return results

    def execute(self, params: Parameters) -> Report:
        # Prepare report
        report = Report(params, self, start_time=datetime.now())
        report.path_details = self._gather_path_info(params.source)
        report.hardware_info = self._gather_hardware_info()

        print("Computing exclusions...")
        exclusions = self._compute_exclusions(params)

        temporary_image = self._create_temporary_image(report)
        if not temporary_image:
            return report

        print("\nRsync", params.source, "->", temporary_image.mount)
        source_str = f"{params.source}"
        if not source_str.endswith("/"):
            source_str = source_str + "/"
        command = [RSYNC_PATH, "-xrlptgoEv", "--progress"]
        for exclusion in exclusions:
            command.extend(["--exclude", f"{exclusion}/"])
        command.extend([source_str, temporary_image.mount])
        status = self._run_status(command)

        # We cannot rely on the exit code, because it will probably contain some
        # errors if a few files cannot be copied.
        if status != 0:
            print(f"Rsync terminated (with status {status})")
        else:
            print("Rsync terminated")

        return self._pack_and_hash(report)
