from datetime import datetime
import time
from acquisition.abstract import AcquisitionMethod, Parameters, Report


class AsrMethod(AcquisitionMethod):
    name = "ASR"
    description = """Apple Software Restore logical acquisition.
    This is the recommended option, but it works only for volumes."""

    def execute(self, params: Parameters) -> Report:
        # Prepare report
        report = Report(params, self, start_time=datetime.now())
        report.path_details = self._gather_path_info(params.source)
        report.hardware_info = self._gather_hardware_info()

        success = self._create_temporary_image(report)
        if not success:
            return report

        print("\nASR", params.source, "->", self.temporary_volume)
        command = [
            "asr",
            "restore",
            "--source",
            f"{params.source}",
            "--target",
            self.temporary_volume,
            "--noprompt",
            "--erase",
        ]
        status, _ = self._run_process(command)

        if status != 0:
            return report

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
