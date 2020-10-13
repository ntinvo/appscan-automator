import argparse
import logging
from argparse import ArgumentDefaultsHelpFormatter

ALL = "all"
STATIC = "static"
DYNAMIC = "dynamic"
SCAN = "scan"
REPORTS = "reports"
SINGLE = "single"
COCDEV = "cocdev"
COC = "coc"
V10 = "10.0"
V95 = "9.5"


def init_argparse():
    try:
        parser = argparse.ArgumentParser(
            description="Automator for static and dynamic scan.",
            formatter_class=ArgumentDefaultsHelpFormatter,
            epilog="Have a nice day! :)",
        )

        optionals = parser.add_argument_group()
        optionals.add_argument(
            "-v",
            "--verbose",
            dest="verbose",
            choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            help="logging level",
            default=logging.WARNING,
        )
        subparsers = parser.add_subparsers(dest="mode")

        # create subparsers
        for mode in [SCAN, REPORTS]:
            mode_parser = subparsers.add_parser(mode)

            mode_subparser = mode_parser.add_subparsers(dest="type")
            for type in [ALL, STATIC, DYNAMIC]:
                type_parser = mode_subparser.add_parser(type)

                if mode == SCAN:
                    if type == ALL or type == STATIC:
                        type_parser.add_argument(
                            "-s",
                            "--source",
                            required=True,
                            dest="source",
                            help=f"the path to source code. When running type {STATIC} and mode {SCAN}, this is required.",
                        )

                    if type == ALL or type == DYNAMIC:
                        type_parser.add_argument(
                            "-ver",
                            "--version",
                            choices=[SINGLE, COCDEV, COC, V95, V10],
                            help=f"version to run the scan on.",
                            default=SINGLE,
                        )
                if mode == REPORTS:
                    type_parser.add_argument(
                        "-o",
                        "--output",
                        required=True,
                        dest="output",
                        help=f"path to store the reports.",
                    )
        arguments = parser.parse_args()
    except argparse.ArgumentError as e:
        print("Error parsing arguments")
        raise e
    else:
        print(f"Arguments have been parsed: {arguments}")
        return arguments


args = init_argparse()
print(args)
