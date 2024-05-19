import os

from acquisition.abstract import Parameters
from checks.abstract import Check, CheckResult


class FoldersCheck(Check):
    name = "Folders check"

    def execute(self, params: Parameters) -> CheckResult:
        result = CheckResult(passed=True)

        same_path = params.tmp == params.destination

        tmp_is_directory = os.path.isdir(params.tmp)
        destination_is_directory = os.path.isdir(params.destination)

        tmp_path = params.tmp / params.image_name
        tmp_busy = os.path.exists(tmp_path)
        destination_path = params.destination / params.image_name
        destination_busy = os.path.exists(destination_path)

        if not same_path:
            if not tmp_is_directory:
                result.write("Temp image location is not a directory!")
                result.passed = False
            elif tmp_busy:
                result.write(
                    f"Temp image location already contains {params.image_name}!"
                )
                result.passed = False
            else:
                result.write("Temp image location is a valid directory")

        if not destination_is_directory:
            result.write("Destination is not a directory!")
            result.passed = False
        elif destination_busy:
            result.write(f"Destination already contains {params.image_name}!")
            result.passed = False
        else:
            result.write("Destination is a valid directory")

        return result
