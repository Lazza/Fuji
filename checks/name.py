import os

from acquisition.abstract import Parameters
from checks.abstract import Check, CheckResult


class NameCheck(Check):
    name = "Name check"

    def execute(self, params: Parameters) -> CheckResult:
        special_extensions = {
            ".app",
            ".bundle",
            ".logarchive",
            ".pkg",
            ".sparsebundle",
            ".workflow",
            ".xpc",
        }
        result = CheckResult(passed=True)

        # Get extension from image name
        _, ext = os.path.splitext(params.image_name)
        ext = ext.lower()

        if ext in special_extensions:
            result.passed = False
            result.write(
                f'Special extension "{ext}" shall not be used in the image name!'
            )
        else:
            result.write(f"The image name is valid")

        return result
