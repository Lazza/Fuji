import subprocess

from acquisition.abstract import Parameters
from checks.abstract import Check, CheckResult


class NetworkCheck(Check):
    name = "Network check"

    def execute(self, params: Parameters) -> CheckResult:
        result = CheckResult()

        # This is the CDN server used by the 'networkquality' command
        apple_server = "mensura.cdn-apple.com"

        try:
            http_test = subprocess.check_output(
                ["nc", "-z", apple_server, "80", "-G1"],
                stderr=subprocess.STDOUT,
                universal_newlines=True,
            )
            connected = "succeeded!" in http_test
        except:
            connected = False

        if connected:
            result.write("This Mac is connected to the Internet!")
            result.passed = False
        else:
            result.write("This Mac is not connected to the Internet")
            result.passed = True

        return result
