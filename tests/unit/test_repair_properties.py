import ast

from hypothesis import given, settings, strategies as st

from mergerisk.repair import byte_offset


@settings(max_examples=72, deadline=None)
@given(
    encoding=st.sampled_from(["utf-8", "utf-8-sig", "latin-1", "cp1252"]),
    newline=st.sampled_from(["\n", "\r\n", "\r"]),
    comments=st.lists(st.text(alphabet="abcé ñ", max_size=15), max_size=5),
    form_feed=st.booleans(),
)
def test_ast_coordinates_locate_the_same_bytes_across_encodings(encoding, newline, comments, form_feed):
    codec = "utf-8" if encoding == "utf-8-sig" else encoding
    argument = "\u2028é" if codec == "utf-8" else "é"
    prefix = "\f" if form_feed else ""
    source = newline.join([f"# coding: {codec}", *(f"# {comment}" for comment in comments),
                           f"{prefix}s = {argument!r}; handler(value=2)", ""])
    data = source.encode(encoding)
    call = ast.parse(data).body[-1].value
    offset = byte_offset(data, call.lineno, call.col_offset)
    assert offset == data.index(b"handler(value=2)")
    assert data[offset:].startswith(b"handler(value=2)")
