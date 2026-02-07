import subprocess
from typing import List, Tuple


def lines_to_properties(lines: List[str], separator=":", strip_chars=None) -> dict:
    result = {}

    for line in filter((lambda x: separator in x), lines):
        key, value = line.split(separator, 1)
        result[key.strip(strip_chars)] = value.strip(strip_chars)

    return result


def command_to_properties(
    arguments: List[str], separator=":", strip_chars=None
) -> dict:
    output = subprocess.check_output(arguments, universal_newlines=True)
    return lines_to_properties(output.splitlines(), separator, strip_chars)


def dedent(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return text
    return "\n".join(line.strip() for line in lines)
