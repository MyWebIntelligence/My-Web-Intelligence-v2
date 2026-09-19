#!/usr/bin/env python

import sys

from mwi import cli


def main() -> int:
    """Run the CLI and translate the controller result into an exit code.

    Mapping (A09): 0 on success, 1 on business failure, a cancelled
    confirmation (decision D-13) or an unhandled exception. Argparse keeps
    its own 2 for a usage error.

    Fail-safe on purpose: anything that is not an explicit 1 is a failure, so
    a controller that forgets to return cannot pass for a success.
    """
    return 0 if cli.command_input() == 1 else 1


if __name__ == '__main__':
    sys.exit(main())
