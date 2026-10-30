"""Operator command line.

ragkit-server migrate
ragkit-server user create --email you@example.com --name "You" --admin
ragkit-server demo seed
ragkit-server reindex --collection developer-docs
ragkit-server openapi --out docs/api/openapi.json
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from ragkit_server.core.config import get_settings
from ragkit_server.core.logging import configure_logging

app = typer.Typer(
    no_args_is_help=True, help="Euron RAGKit server command line.", add_completion=False
)
user_app = typer.Typer(no_args_is_help=True, help="Manage accounts.")
demo_app = typer.Typer(no_args_is_help=True, help="Demo data for local stacks.")
app.add_typer(user_app, name="user")
app.add_typer(demo_app, name="demo")


@app.callback()
def _setup() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, "console")


@app.command()
def migrate() -> None:
    """Apply pending database migrations."""
    from ragkit_server.db.migrate import migrate as run

    asyncio.run(run(get_settings()))
    typer.echo("migrations applied")


@user_app.command("create")
def create_user(
    email: Annotated[str, typer.Option(help="Sign-in email.")],
    name: Annotated[str, typer.Option(help="Display name.")],
    password: Annotated[
        str | None,
        typer.Option(
            envvar="RAGKIT_USER_PASSWORD",
            help="Password. Without it the CLI prompts on a terminal, or reads one line from "
            "standard input (for ECS tasks and CI).",
        ),
    ] = None,
    admin: Annotated[bool, typer.Option(help="Instance administrator.")] = False,
) -> None:
    """Create an account."""
    from ragkit_server.db.session import Database
    from ragkit_server.services.users import create_user as create

    secret = password or read_password()

    async def run() -> None:
        db = Database(get_settings())
        try:
            async with db.session() as session:
                user = await create(
                    session, email=email, name=name, password=secret, is_admin=admin
                )
                typer.echo(f"created {user.email} ({user.id})")
        finally:
            await db.dispose()

    asyncio.run(run())


def read_password() -> str:
    """Prompt on a terminal; read the first line of standard input otherwise."""
    if sys.stdin.isatty():
        entered: str = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
        return entered
    line = sys.stdin.readline().rstrip("\n")
    if not line:
        raise typer.BadParameter("give --password, RAGKIT_USER_PASSWORD or a line on stdin")
    return line


@demo_app.command("seed")
def seed(
    samples: Annotated[Path, typer.Option(help="Folder of the demo corpus.")] = Path("samples"),
    password: Annotated[
        str | None, typer.Option(envvar="DEMO_PASSWORD", help="Password for every demo account.")
    ] = None,
    traffic: Annotated[bool, typer.Option(help="Replay two weeks of demo queries.")] = True,
) -> None:
    """Demo accounts, a project with two collections, pipeline versions, datasets and runs."""
    from ragkit_server.demo.seed import run

    settings = get_settings()
    if settings.is_production:
        raise typer.BadParameter("refusing to seed demo data with APP_ENV=production")
    secret = password or (
        settings.demo_password.get_secret_value() if settings.demo_password else None
    )
    if not secret:
        raise typer.BadParameter("set DEMO_PASSWORD (make env generates one)")
    asyncio.run(run(settings, samples, secret, traffic=traffic))


@app.command()
def reindex(
    collection: Annotated[
        str | None, typer.Option(help="Collection slug; all when omitted.")
    ] = None,
) -> None:
    """Parse every document (of one collection) again, which rebuilds every index of it."""
    from ragkit_server.demo.seed import reindex as run

    count = asyncio.run(run(get_settings(), collection))
    typer.echo(f"queued {count} document(s)")


@app.command()
def openapi(
    out: Annotated[Path, typer.Option(help="Where to write the OpenAPI document.")] = Path(
        "openapi.json"
    ),
) -> None:
    """Export the OpenAPI document generated from the routes."""
    from ragkit_server.main import create_app

    schema = create_app().openapi()
    out.write_text(json.dumps(schema, indent=2, sort_keys=False) + "\n")
    typer.echo(f"wrote {out}")


if __name__ == "__main__":
    app()
