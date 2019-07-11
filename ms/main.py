import argparse
import importlib
import logging

from ms import core
from ms.config import Config


def main():
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(prog='ms')
    subparsers = parser.add_subparsers()

    core.add_commands(subparsers)

    # Import and load any commands for plugins specified in settings
    plugins = Config.get('PLUGINS')
    if plugins:
        for plugin in plugins:
            module = importlib.import_module(plugin)
            module.add_commands(subparsers)

    args = parser.parse_args()
    args.func(args)
