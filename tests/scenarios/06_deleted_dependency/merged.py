def render_report(value):
    return f"<<{value}>>"


def generate_summary(values):
    return ", ".join(legacy_formatter(v) for v in values)
