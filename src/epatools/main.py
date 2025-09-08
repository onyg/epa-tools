import os
import sys
import argparse

from epatools.version import __APPNAME__, __VERSION__
import epatools.cli as cli 
from epatools.merger import Merger
from epatools.oaconverter import OpenApiConverter
from epatools.common import ConfigFileDoesNotExists, DEFAULT_CONFIG, DEFAULT_DEPENDENCIES_CONFIG

def main():
    parser = argparse.ArgumentParser(description=cli.get_version(__APPNAME__, __VERSION__))
    parser.add_argument("-v", "--version", action="version", version=cli.get_version(__APPNAME__, __VERSION__))
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    merge_parser = subparsers.add_parser("merge", help="Merge capability statements")
    merge_parser.add_argument("--config", help="Config", default=DEFAULT_CONFIG)
    merge_parser.add_argument("--dependencies", help="Path to the FHIR IG config file (e.g., sushi-config.yaml) containing package dependencies", default=DEFAULT_DEPENDENCIES_CONFIG)
    merge_parser.add_argument("--extra", action="store_true", help="Do not overwrite the CapabilityStatement")


    openapi_parser = subparsers.add_parser("openapi", help="Convert capability statements to openAPI")
    openapi_parser.add_argument("--config", help="Config", default=DEFAULT_CONFIG)

    args = parser.parse_args()

    try:
        if args.command == "merge":
            _merger = Merger(config_file=args.config).load()
            _merger.extra_merged_file = args.extra
            _merger.dependencies_config = args.dependencies
            _merger.merge()

        elif args.command == "openapi":
            _oaconverter = OpenApiConverter(config_file=args.config).load()
            _oaconverter.convert()
        else:
            parser.print_help()
    except ConfigFileDoesNotExists as e:
        print("⚠️  Config file missing. Skipping execution.")
        sys.exit(os.EX_OK)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(os.EX_DATAERR)


if __name__ == "__main__":
    main()