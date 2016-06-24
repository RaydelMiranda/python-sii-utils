""" Configuration File (see files/cfg_utils.yml in repository)
"""
import io

import yaml
from sii.lib.lib import fileio

__all__ = [
    'Configuration'
]


class Configuration:

    def __init__(self, cfg_path, cfg_templ):
        self._cfg_path  = cfg_path
        self._cfg_templ = cfg_templ

        buff = io.StringIO(fileio.read_create(cfg_path, cfg_templ))
        yml  = yaml.load(buff)

        for section, data in yml.items():
            name = str(section)
            self.__dict__[name] = Section(name, data)

    def __getattr__(self, key):
        if key not in self.__dict__:
            raise KeyError("Config expected and could not find section: <{0}>".format(key))
        else:
            value = super().__getattr__(key)

            if value is None:
                raise ValueError("Config section <{0}> is expected but not set!".format(key))

            return value


class Section:

    def __init__(self, name, data):
        self._name = name
        self.__dict__.update(data)

    def __getattr__(self, key):
        if key not in self.__dict__:
            raise KeyError("Config section <{0}> expected parameter: <{1}>".format(self._name, key))
        else:
            value = super().__getattr__(key)

            if value is None:
                raise ValueError("Config section <{0}> parameter <{1}> unexpected a value!".format(self._name, key))

            return value