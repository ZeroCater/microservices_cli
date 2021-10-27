import json
import os


class Config(object):
    """Class that handles I/O related to the config. Currently all static methods."""
    @staticmethod
    def _get_config_path():
        return os.path.join(os.path.expanduser('~'), '.ms')

    @staticmethod
    def _read():
        config_file = Config._get_config_path()

        # Touch file if it doesn't exist
        if not os.path.isfile(config_file):
            open(config_file, 'a').close()

        with open(config_file) as config:
            try:
                return json.load(config)
            except ValueError as ex:
                print(f'Error loading config file: {ex}')
                return {}

    @staticmethod
    def _write(config_data):
        """Write config data to disk"""
        with open(Config._get_config_path(), 'w') as f:
            f.write(json.dumps(config_data, indent=4))
            f.write('\n')  # EOF newline

    @staticmethod
    def get(var, default=None):
        config_value = Config._read().get(var)

        if not config_value:
            return default

        return config_value

    @staticmethod
    def set(var, value):
        """Set config variable and write to disk"""
        # TODO: Make this work with nested/dictionary values
        config_data = Config._read()

        config_data[var] = value
        Config._write(config_data)
