"""Entry point: run the Traveller Flask app under gunicorn.

Forwards any CLI arguments to gunicorn, then appends the WSGI app target
so a bare ``traveller`` invocation works while flags like ``--bind`` and
``--workers`` are still honoured.
"""

import sys

from gunicorn.app.wsgiapp import run


def main() -> None:
    sys.argv.append("traveller.app:create_app()")
    run()


if __name__ == "__main__":
    main()
