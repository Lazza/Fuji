import subprocess
from datetime import datetime
from typing import List, Optional

from wx import Control, Font

ACCENT_COLOR = (181, 78, 78)
GREEN_COLOR = (34, 170, 54)
RED_COLOR = (203, 11, 1)


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


def datetime_string(value: Optional[datetime]) -> str:
    if value is None:
        return "-"
    else:
        info = value.astimezone().tzinfo
        if info is not None:
            timezone_name = f" ({info.tzname(value)})"
        else:
            timezone_name = ""
        iso_format = value.isoformat(sep=" ")
        return f"{iso_format}{timezone_name}"


def set_font(widget: Control, size: Optional[int] = None, weight: Optional[int] = None):
    font: Font = widget.GetFont()
    if size is not None:
        font.SetPointSize(size)
    if weight is not None:
        font.SetWeight(weight)
    widget.SetFont(font)
