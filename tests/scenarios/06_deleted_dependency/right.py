def legacy_formatter(value):
    return f"[{value}]"


def render_report(value):
    return legacy_formatter(value)


def generate_summary(values):
    return ", ".join(legacy_formatter(v) for v in values)
