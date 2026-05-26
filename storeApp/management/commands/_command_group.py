"""Build a Django management command that delegates to nested Command classes."""

from __future__ import annotations

from typing import Type

from django.core.management.base import BaseCommand, CommandError


def build_group_command(
    *,
    help_text: str,
    subcommands: dict[str, Type[BaseCommand]],
) -> Type[BaseCommand]:
    if not subcommands:
        raise ValueError("subcommands must not be empty")

    names = ", ".join(sorted(subcommands))

    class GroupCommand(BaseCommand):
        help = help_text

        def add_arguments(self, parser):
            subparsers = parser.add_subparsers(
                dest="subcommand",
                required=True,
                metavar="SUBCOMMAND",
                help=f"Available: {names}",
            )
            for name, command_cls in subcommands.items():
                sub = subparsers.add_parser(
                    name,
                    help=(command_cls.help or name),
                )
                command_cls().add_arguments(sub)

        def handle(self, *args, **options):
            sub_name = options.pop("subcommand", None)
            if sub_name not in subcommands:
                raise CommandError(
                    f"Unknown subcommand {sub_name!r}. Choose: {names}"
                )
            subcommands[sub_name]().handle(*args, **options)

    return GroupCommand


def invoke_subcommand(command_cls: Type[BaseCommand], *args, **options) -> None:
    """Run a nested command implementation (for in-process calls)."""
    command_cls().handle(*args, **options)
