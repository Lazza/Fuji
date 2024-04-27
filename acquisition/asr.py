from datetime import datetime
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
        status = self._run_status(command, buffer_size=1)

        if status != 0:
            return report

        return self._dmg_and_hash(report)
