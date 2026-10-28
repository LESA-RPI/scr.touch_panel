"""Human-readable panel version; Git commits identify the exact deployed source."""

VERSION = "0.2.6"


def build_commit():
    """Release archives carry their commit; local previews need no Git process."""
    from pathlib import Path

    try:
        value = (
            (Path(__file__).resolve().parents[1] / "DEPLOYED_COMMIT")
            .read_text(encoding="ascii")
            .strip()
        )
    except (OSError, UnicodeError):
        return None
    return (
        value[:7]
        if len(value) == 40 and all(c in "0123456789abcdef" for c in value)
        else None
    )


BUILD_COMMIT = build_commit()
