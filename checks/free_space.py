import os

import humanize
from acquisition.abstract import Parameters
from checks.abstract import Check, CheckResult


class FreeSpaceCheck(Check):
    name = "Free space check"

    def _get_used_space(self, path):
        statvfs = os.statvfs(path)
        total_space = statvfs.f_blocks * statvfs.f_frsize
        free_space = statvfs.f_bfree * statvfs.f_frsize
        return total_space - free_space

    def _get_free_space(self, path):
        statvfs = os.statvfs(path)
        free_space = statvfs.f_bfree * statvfs.f_frsize
        return free_space

    def execute(self, params: Parameters) -> CheckResult:
        result = CheckResult()

        source_used = self._get_used_space(params.source)
        tmp_string = f"{params.tmp}"
        destination_string = f"{params.destination}"
        same_volume = tmp_string.startswith(
            destination_string
        ) or destination_string.startswith(tmp_string)

        if same_volume:
            destination_free = self._get_free_space(params.destination)
            result.passed = destination_free >= 2 * source_used

            needed_readable = humanize.naturalsize(2 * source_used)
            free_readable = humanize.naturalsize(destination_free)
            tail = f"(up to {needed_readable} / {free_readable})"
            if result.passed:
                result.message = f"Free space in destination seems enough {tail}"
            else:
                result.message = (
                    f"Free space in destination could be insufficient {tail}"
                )

        else:
            tmp_free = self._get_free_space(params.tmp)
            tmp_passed = tmp_free >= source_used
            tmp_needed_readable = humanize.naturalsize(source_used)
            tmp_free_readable = humanize.naturalsize(tmp_free)

            destination_free = self._get_free_space(params.destination)
            destination_passed = destination_free >= source_used
            destination_needed_readable = humanize.naturalsize(source_used)
            destination_free_readable = humanize.naturalsize(destination_free)

            result.passed = tmp_passed and destination_passed
            tmp_tail = f"(up to {tmp_needed_readable} / {tmp_free_readable})"
            if tmp_passed:
                result.message = (
                    f"Free space in temp. image location seems enough {tmp_tail}"
                )
            else:
                result.message = f"Free space in temp. image location could be insufficient {tmp_tail}"

            destination_tail = (
                f"(up to {destination_needed_readable} / {destination_free_readable})"
            )
            if destination_passed:
                result.message = result.message + (
                    f"\nFree space in destination seems enough {destination_tail}"
                )
            else:
                result.message = (
                    result.message
                    + f"\nFree space in destination could be insufficient {destination_tail}"
                )

        return result
