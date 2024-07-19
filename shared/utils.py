import subprocess
from typing import List, Tuple


def lines_to_properties(lines: List[str], separator=":") -> dict:
    result = {}

    for line in filter((lambda x: separator in x), lines):
        key, value = line.split(separator, 1)
        result[key.strip()] = value.strip()

    return result


def command_to_properties(arguments: List[str]) -> dict:
    output = subprocess.check_output(arguments, universal_newlines=True)
    return lines_to_properties(output.splitlines())
