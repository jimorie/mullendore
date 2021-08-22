import collections
import pathlib


def path(s):
    return pathlib.Path(s)


def abspath(s):
    return pathlib.Path(s).resolve()


class Metadata(collections.ChainMap):
    def __getitem__(self, key):
        for mapping in self.maps:
            if (
                mapping is not self.maps[0]
                and key == "private"
                or ("private" in mapping and key in mapping["private"])
            ):
                continue
            try:
                return mapping[key]
            except KeyError:
                pass
        return self.__missing__(key)

    def __iter__(self):
        for key in collections.ChainMap.__iter__(self):
            try:
                self[key]
                yield key
            except KeyError:
                continue

    def __contains__(self, key):
        try:
            self[key]
            return True
        except KeyError:
            return False
