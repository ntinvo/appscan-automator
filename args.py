import argparse
import logging
import os
from argparse import ArgumentDefaultsHelpFormatter

from constants import ALL, COC, COCDEV, DEPCHECK, DYNAMIC, REPORTS, SCAN, SINGLE, STATIC, V10, V95

# logging
main_logger = logging.getLogger(__name__)


def add_optionals_args(parser):
    """
    docstring
    """
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="logging level",
        default=logging.WARNING,
    )


def add_output_arg(parser):
    """
    docstring
    """
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        help=f"path to store the reports",
        default=f"{os.getcwd()}/reports",
    )


def add_version_arg(parser, required=False):
    """
    docstring
    """
    parser.add_argument(
        "-ver",
        "--version",
        required=required,
        choices=[SINGLE, COCDEV, COC, V95, V10],
        help=f"version to run the scan on",
        default=SINGLE,
    )


def add_source_arg(parser, required=False):
    """
    docstring
    """
    parser.add_argument(
        "-s",
        "--source",
        required=required,
        dest="source",
        help=f"the path to source code. When running type {STATIC} and mode {SCAN}, this is required",
    )


def init_argparse():
    try:
        parser = argparse.ArgumentParser(
            description="Automator for static, dynamic scan, and dependency check.",
            formatter_class=ArgumentDefaultsHelpFormatter,
            epilog="Have a nice day! :)",
        )

        subparsers = parser.add_subparsers(
            title="mode", dest="mode", description="automator mode to run", required=True
        )

        # create subparsers
        for mode in [SCAN, REPORTS, DEPCHECK]:
            mode_parser = subparsers.add_parser(mode)
            add_optionals_args(mode_parser)
            if mode == DEPCHECK:
                add_version_arg(mode_parser)
                add_output_arg(mode_parser)
            else:
                mode_subparser = mode_parser.add_subparsers(
                    title="type", dest="type", description="type of scan to run", required=True
                )
                for type in [ALL, STATIC, DYNAMIC]:
                    type_parser = mode_subparser.add_parser(type)
                    add_optionals_args(type_parser)
                    if mode == SCAN:
                        if type == ALL or type == STATIC:
                            add_source_arg(type_parser, required=True)
                        if type == ALL or type == DYNAMIC:
                            add_version_arg(type_parser)
                    if mode == REPORTS:
                        add_output_arg(type_parser)
        arguments = parser.parse_args()
    except argparse.ArgumentError as e:
        main_logger.error("Error parsing arguments")
        raise e
    else:
        main_logger.info(f"Arguments have been parsed: {arguments}")
        return arguments

