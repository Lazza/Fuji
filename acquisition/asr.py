from datetime import datetime
from acquisition.abstract import AcquisitionMethod, Parameters, Report


class AsrMethod(AcquisitionMethod):
    name = "ASR"
    description = """Apple Software Restore logical acquisition.
    This is quite fast but less reliable, and it works only for volumes."""

    def execute(self, params: Parameters) -> Report:
        # Prepare report
        report = self._initialize_report(params)

        temporary_image = self._create_temporary_image(report)
        if not temporary_image:
            return report

        print("\nASR", params.source, "->", temporary_image.volume)
        command = [
            "asr",
            "restore",
            "--source",
            f"{params.source}",
            "--target",
            temporary_image.volume,
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

        return self._pack_and_hash(report)
