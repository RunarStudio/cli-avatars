"""Product version. Installer, boot check, and updater read this string.

The short git commit is not part of the version. A build writes it next
to the installed app. ``pyproject.toml`` repeats this string; the
packaging tests keep the two copies the same.
"""

__version__ = "0.4.0"
