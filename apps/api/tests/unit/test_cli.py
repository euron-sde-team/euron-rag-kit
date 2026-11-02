"""The operator CLI's account creation: how a password is chosen when nobody can be asked."""

from __future__ import annotations

import io
import sys

import pytest
from typer.testing import CliRunner

from ragkit_server.cli import app, resolve_password
from ragkit_server.core.security import temporary_password, validate_password


def test_a_temporary_password_passes_the_policy_and_is_never_repeated() -> None:
    passwords = {temporary_password() for _ in range(50)}
    assert len(passwords) == 50
    for password in passwords:
        validate_password(password)
        assert len(password) == 15
        assert password[7] == "-"
        # No characters that are easy to misread when someone types it in.
        assert not set(password) & set("0O1lI")


def test_a_given_password_is_used_as_it_is() -> None:
    assert resolve_password("a-chosen-password") == ("a-chosen-password", False)


def test_one_line_of_standard_input_is_the_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("piped-in-secret\n"))
    assert resolve_password(None) == ("piped-in-secret", False)


def test_with_nobody_to_ask_a_temporary_password_is_generated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An ECS one-off task has no terminal and an empty standard input.
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    password, generated = resolve_password(None)
    assert generated
    validate_password(password)


def test_the_command_lists_its_subcommands() -> None:
    result = CliRunner().invoke(app, ["user", "--help"])
    assert result.exit_code == 0
    assert "create" in result.output
