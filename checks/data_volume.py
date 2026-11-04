from acquisition.abstract import Parameters
from checks.abstract import Check, CheckResult
from shared import filevault
from shared.environment import RECOVERY


class DataVolumeCheck(Check):
    name = "Data volume check"

    def active(self) -> bool:
        # In a running macOS the data volume is always mounted
        return RECOVERY

    def execute(self, params: Parameters) -> CheckResult:
        result = CheckResult(passed=True)
        volumes = filevault.data_volumes()

        if not volumes:
            result.passed = False
            result.write("No macOS data volume found!")
            return result

        for volume in volumes:
            if volume.mounted:
                result.write(f"{volume.name} ({volume.identifier}) {volume.state()}")
            elif volume.locked:
                result.passed = False
                result.write(
                    f"{volume.name} ({volume.identifier}) is locked by FileVault! "
                    'Use "Unlock data volume" on the previous screen.'
                )
            else:
                result.passed = False
                result.write(
                    f"{volume.name} ({volume.identifier}) is not mounted! "
                    'Use "Unlock data volume" on the previous screen.'
                )

        on_data_volume = any(
            filevault.contains(v.mount_point, params.source)
            for v in volumes
            if v.mounted
        )
        if not on_data_volume:
            result.passed = False
            result.write("The source is not located on a macOS data volume!")

        return result
