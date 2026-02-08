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

        temporary_bundle = self._create_temporary_image(report)
        if not temporary_bundle:
            return report

        print("\nASR", params.source, "->", temporary_bundle.volume)
        command = [
            "asr",
            "restore",
            "--source",
            f"{params.source}",
            "--target",
            temporary_bundle.volume,
            "--noprompt",
            "--erase",
        ]
        status, output = self._run_process(command)

        # Sometimes ASR crashes at the end but the acquisition is still OK
        success = status == 0 or (
            output.count("..100") > 1 and "Restored target" in output
        )

        if not success:
            return report

        return self._dmg_and_hash(report)
