import time
from acquisition.abstract import AcquisitionMethod, Parameters


class AsrMethod(AcquisitionMethod):
    name = "ASR"
    description = """Apple Software Restore logical acquisition.
    This is the recommended option, but it works only for volumes."""

    def execute(self, params: Parameters) -> bool:
        success = self._create_temporary_image(params)
        if not success:
            return False

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
            return False

        result = self._detach_temporary_image()
        if not result:
            return False

        result = self._generate_dmg(params)

        return result
