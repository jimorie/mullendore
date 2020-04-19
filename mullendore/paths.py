import pathlib


def path(s):
    return pathlib.Path(s)


def abspath(s):
    return pathlib.Path(s).resolve()
