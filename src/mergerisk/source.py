"""Decode Python source according to its physical first two lines."""

import re
import tokenize


_BYTE_LINE_END = re.compile(br"\r\n?|\n")


def source_encoding(data: bytes) -> str:
    # The compiler accepts CR-only source. Give detect_encoding the same header lines.
    breaks = _BYTE_LINE_END.finditer(data)
    start = 0

    def readline() -> bytes:
        nonlocal start
        match = next(breaks, None)
        if match is None:
            line = data[start:]
            start = len(data)
            return line
        line = data[start:match.start()] + b"\n"
        start = match.end()
        return line

    return tokenize.detect_encoding(readline)[0]


def decode_source(data: bytes) -> str:
    return data.decode(source_encoding(data))
