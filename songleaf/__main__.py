# PYTHON_ARGCOMPLETE_OK
"""``python -m songleaf``: the command line, ``cw`` over :data:`songleaf.tools.TOOLS`.

Examples::

    python -m songleaf search "wonderwall oasis"
    python -m songleaf sheet "wonderwall oasis"     # -> a one-page A4 PDF
    python -m songleaf sheet kaggle_chords:1234 --output sheet.pdf
    python -m songleaf songs
"""

import functools
import inspect

import cw

from songleaf import tools

#: Dependency-injection parameters: seams for library callers, not CLI options.
_SEAMS = ("sources", "store", "renderer")


def _with_expected_errors(tool):
    """A failure the user can act on becomes one line on stderr, not a traceback."""

    @functools.wraps(tool)
    def command(*args, **kwargs):
        try:
            return tool(*args, **kwargs)
        except (LookupError, RuntimeError, ValueError) as error:
            raise cw.CommandError(str(error)) from error

    return command


def main(argv=None):
    """Run one songleaf command."""
    config = {
        tool.__name__: {
            name: cw.HIDE
            for name in _SEAMS
            if name in inspect.signature(tool).parameters
        }
        for tool in tools.TOOLS
    }
    commands = [_with_expected_errors(tool) for tool in tools.TOOLS]
    raise SystemExit(
        cw.dispatch(
            commands, argv, prog="songleaf", convention=cw.MODERN, config=config
        )
    )


if __name__ == "__main__":
    main()
