import os
import sys
import argparse

from epatools.version import __APPNAME__, __VERSION__
import epatools.cli as cli 
from epatools.merger import Merger
from epatools.oaconverter import OpenApiConverter


def main():
    parser = argparse.ArgumentParser(description=cli.get_version(__APPNAME__, __VERSION__))
    parser.add_argument("-v", "--version", action="version", version=cli.get_version(__APPNAME__, __VERSION__))
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    merge_process_parser = subparsers.add_parser("merge", help="Merge capability statements")
    merge_process_parser.add_argument("--config", help="Config", default="sushi-config.yaml")

    merge_process_parser = subparsers.add_parser("openapi", help="Convert capability statements to openAPI")
    merge_process_parser.add_argument("--config", help="Config", default="sushi-config.yaml")

    args = parser.parse_args()

    try:
        if args.command == "merge":
            _merger = Merger(config_file=args.config).load()
            _merger.merge()

        if args.command == "openapi":
            _oaconverter = OpenApiConverter(config_file=args.config).load()
            _oaconverter.convert()
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()