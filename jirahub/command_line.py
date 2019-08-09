import os
import sys
from argparse import ArgumentParser
import traceback
import logging
from datetime import datetime, timezone

from .config import load_config, generate_config_template
from .permissions import check_permissions
from .jirahub import IssueSync


logger = logging.getLogger(__name__)


def _parse_args():
    parent_parser = ArgumentParser()
    parent_parser.add_argument("-v", "--verbose", action="store_true", help="enable verbose log messages")

    parser = ArgumentParser(description="GitHub/JIRA issue sync tool", parents=[parent_parser], add_help=False)

    subparsers = parser.add_subparsers(dest="command", help="selected command")
    subparsers.required = True

    sync_parser = subparsers.add_parser("sync", description="Perform sync", parents=[parent_parser], add_help=False)
    sync_parser.add_argument("config_path", nargs="+", help="path to jirahub config file", metavar="config-path")

    placeholder_group = sync_parser.add_mutually_exclusive_group()
    min_updated_at_help = (
        "consider issues updated after this timestamp "
        "(format is ISO-8601 in UTC with no timezone suffix, e.g., "
        "1983-11-20T11:00:00"
    )
    placeholder_group.add_argument("--min-updated-at", help=min_updated_at_help)
    placeholder_group.add_argument("--placeholder-path", help="path to placeholder file")

    sync_parser.add_argument("--dry-run", action="store_true", help="query but do not make changes to GitHub or JIRA")

    permissions_parser = subparsers.add_parser(
        "check-permissions",
        description="Check GitHub and JIRA credentials and permissions",
        parents=[parent_parser],
        add_help=False,
    )
    permissions_parser.add_argument("config_path", nargs="+", help="path to jirahub config file", metavar="config-path")

    subparsers.add_parser(
        "generate-config", description="Print config file template to stdout", parents=[parent_parser], add_help=False
    )

    return parser.parse_args()


def main():
    args = _parse_args()

    _configure_logging(args)

    if args.command == "sync":
        return _handle_sync(args)
    elif args.command == "generate-config":
        return _handle_generate_config(args)
    elif args.command == "check-permissions":
        return _handle_check_permissions(args)


def _configure_logging(args):
    handler = logging.StreamHandler()

    if args.verbose:
        handler.setLevel(logging.INFO)
        logging.getLogger("jirahub").setLevel(logging.INFO)
    else:
        handler.setLevel(logging.WARNING)

    formatter = logging.Formatter("%(asctime)s - %(levelname)-7s - %(name)s - %(message)s")
    handler.setFormatter(formatter)

    logging.getLogger().addHandler(handler)


def _handle_sync(args):
    try:
        config = load_config(args.config_path)
    except Exception:
        _print_error("Failed parsing config file:")
        traceback.print_exc(file=sys.stderr)
        return 1

    if args.min_updated_at:
        min_updated_at = datetime.fromisoformat(args.min_updated_at).replace(tzinfo=timezone.utc)
    elif args.placeholder_path:
        min_updated_at = _read_placeholder(args.placeholder_path)
    else:
        min_updated_at = None

    if min_updated_at:
        logger.info("Starting placeholder: %s", _format_placeholder(min_updated_at))
    else:
        logger.warning("Missing placeholder.  Will sync issues from all time.")

    new_min_updated_at = datetime.utcnow()

    try:
        issue_sync = IssueSync.from_config(config, dry_run=args.dry_run)
        issue_sync.perform_sync(min_updated_at)
    except Exception:
        logger.exception("Fatal error")
        return 1

    logger.info("Sync successful.  Next placeholder: %s", _format_placeholder(new_min_updated_at))
    if args.placeholder_path and not args.dry_run:
        _write_placeholder(args.placeholder_path, new_min_updated_at)

    return 0


def _handle_check_permissions(args):
    try:
        config = load_config(args.config_path)
    except Exception:
        _print_error("Failed parsing config file:")
        traceback.print_exc(file=sys.stderr)
        return 1

    try:
        errors = check_permissions(config)
    except Exception:
        logger.exception("Fatal error")
        return 1

    if errors:
        _print_error("JIRA and/or GitHub permissions must be corrected:")
        for error in errors:
            _print_error(error)
        return 1
    else:
        print("JIRA and GitHub permissions are sufficient")
        return 0


def _handle_generate_config(args):
    sys.stdout.write(generate_config_template())

    return 0


def _print_error(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)


def _read_placeholder(path):
    if os.path.isfile(path):
        with open(path, "r") as file:
            value = file.read()
        min_updated_at = datetime.fromisoformat(value.strip())
        return min_updated_at.replace(tzinfo=timezone.utc)
    else:
        logger.warning("Placeholder file missing")
        return None


def _write_placeholder(path, min_updated_at):
    with open(path, "w") as file:
        file.write(_format_placeholder(min_updated_at))
        file.write("\n")


def _format_placeholder(value):
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")
