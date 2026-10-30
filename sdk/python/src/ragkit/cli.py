"""The `ragkit` command line: query, answer, ingest, and gate CI on evaluation runs.

    export RAGKIT_URL=http://localhost:8160 RAGKIT_API_KEY=rgk_... RAGKIT_PROJECT=acme-payments
    ragkit query developer-docs "How do I verify webhook signatures?"
    ragkit eval gate smoke --min hit_rate=0.9 --max-drop 0.03 --report gate.md

`ragkit eval gate` exits 0 when every check passes, 1 when a metric regressed past its
threshold, and 2 when the run could not be evaluated, so CI can tell a regression from an
outage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from ragkit.client import RAGKit, load_jsonl
from ragkit.errors import NotFoundError, RAGKitError
from ragkit.gate import (
    EXIT_ERROR,
    exit_code,
    json_report,
    markdown_report,
    parse_thresholds,
)
from ragkit.models import GateResult

app = typer.Typer(no_args_is_help=True, help="Euron RAGKit command line.", add_completion=False)
eval_app = typer.Typer(no_args_is_help=True, help="Datasets, evaluation runs and the CI gate.")
app.add_typer(eval_app, name="eval")

Url = Annotated[str | None, typer.Option("--url", envvar="RAGKIT_URL", help="API base URL.")]
Key = Annotated[str | None, typer.Option("--api-key", envvar="RAGKIT_API_KEY", help="API key.")]
ProjectOption = Annotated[
    str | None, typer.Option("--project", envvar="RAGKIT_PROJECT", help="Project slug.")
]


def _client(url: str | None, key: str | None, project: str | None) -> RAGKit:
    try:
        return RAGKit(url, key, project)
    except RAGKitError as exc:
        typer.echo(f"error: {exc.message}", err=True)
        raise typer.Exit(EXIT_ERROR) from exc


def _fail(exc: RAGKitError) -> typer.Exit:
    typer.echo(f"error: {exc}", err=True)
    return typer.Exit(EXIT_ERROR)


def _metadata(pairs: list[str]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep:
            raise typer.BadParameter(f"expected key=value, got {pair!r}")
        try:
            metadata[key] = json.loads(value)
        except json.JSONDecodeError:
            metadata[key] = value
    return metadata


@app.command()
def query(
    collection: Annotated[str, typer.Argument(help="Collection slug.")],
    text: Annotated[str, typer.Argument(help="The query.")],
    top_k: Annotated[int | None, typer.Option(help="Hits to return.")] = None,
    mode: Annotated[str | None, typer.Option(help="vector, keyword or hybrid.")] = None,
    rerank: Annotated[str | None, typer.Option(help="none, lexical or cross-encoder.")] = None,
    version: Annotated[int | None, typer.Option(help="Pipeline version (default: active).")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print the raw response.")] = False,
    url: Url = None,
    api_key: Key = None,
    project: ProjectOption = None,
) -> None:
    """Retrieve passages, with each stage's score."""
    options = {"top_k": top_k, "mode": mode, "rerank": rerank, "pipeline_version": version}
    with _client(url, api_key, project) as rk:
        try:
            result = rk.collection(collection).query(
                text, **{k: v for k, v in options.items() if v is not None}
            )
        except RAGKitError as exc:
            raise _fail(exc) from exc
    if as_json:
        typer.echo(result.model_dump_json(indent=2))
        return
    typer.echo(
        f"version {result.pipeline_version}, {result.mode}, rerank {result.rerank['kind']}, "
        f"{result.timings_ms.get('total', 0):.0f} ms{' (cached)' if result.cached else ''}"
    )
    for hit in result.hits:
        snippet = " ".join(hit.text.split())[:110]
        typer.echo(f"{hit.rank:>2}. {hit.score:.3f}  {hit.external_id} ({hit.location})  {snippet}")


@app.command()
def answer(
    collection: Annotated[str, typer.Argument(help="Collection slug.")],
    text: Annotated[str, typer.Argument(help="The question.")],
    version: Annotated[int | None, typer.Option(help="Pipeline version (default: active).")] = None,
    url: Url = None,
    api_key: Key = None,
    project: ProjectOption = None,
) -> None:
    """Answer a question with citations."""
    options = {"pipeline_version": version} if version else {}
    with _client(url, api_key, project) as rk:
        try:
            result = rk.collection(collection).answer(text, **options)
        except RAGKitError as exc:
            raise _fail(exc) from exc
    typer.echo(result.answer)
    for citation in result.citations:
        typer.echo(f"  [{citation.n}] {citation.document_title} ({citation.location})")


@app.command()
def ingest(
    collection: Annotated[str, typer.Argument(help="Collection slug.")],
    paths: Annotated[list[Path], typer.Argument(help="Files to upload.", exists=True)],
    metadata: Annotated[
        list[str] | None, typer.Option("--metadata", "-m", help="key=value, repeatable.")
    ] = None,
    wait: Annotated[bool, typer.Option(help="Wait until the active version is indexed.")] = True,
    url: Url = None,
    api_key: Key = None,
    project: ProjectOption = None,
) -> None:
    """Upload files (PDF, Word, Markdown, HTML, text, CSV) to a collection."""
    with _client(url, api_key, project) as rk:
        target = rk.collection(collection)
        try:
            result = target.add_files(paths, metadata=_metadata(metadata or []))
            typer.echo(
                f"created {len(result.created)}, duplicates {len(result.duplicates)}, "
                f"rejected {len(result.rejected)}"
            )
            for rejected in result.rejected:
                typer.echo(f"  rejected {rejected.name}: {rejected.message}", err=True)
            if wait and result.created:
                version = target.wait_until_indexed()
                typer.echo(
                    f"version {version.version} index {version.index.status}: "
                    f"{version.index.chunk_count} chunks"
                )
        except RAGKitError as exc:
            raise _fail(exc) from exc


@eval_app.command("import")
def import_dataset(
    dataset: Annotated[str, typer.Argument(help="Dataset slug (created when missing).")],
    file: Annotated[Path, typer.Argument(help="JSONL items.", exists=True, dir_okay=False)],
    collection: Annotated[
        str | None, typer.Option(help="Collection, when the dataset is created.")
    ] = None,
    replace: Annotated[bool, typer.Option(help="Replace existing items.")] = False,
    url: Url = None,
    api_key: Key = None,
    project: ProjectOption = None,
) -> None:
    """Load questions from JSONL into a dataset."""
    items = load_jsonl(file)
    with _client(url, api_key, project) as rk:
        try:
            try:
                rk.evals.dataset(dataset)
                result = rk.evals.import_items(dataset, items, replace=replace)
            except NotFoundError:
                if not collection:
                    raise typer.BadParameter(
                        "the dataset does not exist yet; pass --collection to create it"
                    ) from None
                result = rk.evals.create_dataset(
                    dataset.replace("-", " ").capitalize(), collection, items, slug=dataset
                )
        except RAGKitError as exc:
            raise _fail(exc) from exc
    typer.echo(f"dataset {result.slug}: {result.item_count} questions")


@eval_app.command("run")
def run_dataset(
    dataset: Annotated[str, typer.Argument(help="Dataset slug.")],
    version: Annotated[int | None, typer.Option(help="Pipeline version (default: active).")] = None,
    k: Annotated[int, typer.Option(help="Retrieval cutoff for the metrics.")] = 5,
    label: Annotated[str | None, typer.Option(help="Run label.")] = None,
    grader: Annotated[str, typer.Option(help="deterministic or model.")] = "deterministic",
    wait: Annotated[bool, typer.Option(help="Wait for the run to finish.")] = True,
    url: Url = None,
    api_key: Key = None,
    project: ProjectOption = None,
) -> None:
    """Start an evaluation run and print its metrics."""
    with _client(url, api_key, project) as rk:
        try:
            run = rk.evals.run(
                dataset, pipeline_version=version, k=k, label=label, grader=grader, wait=wait
            )
        except RAGKitError as exc:
            raise _fail(exc) from exc
    typer.echo(f"run {run.id} ({run.label}): {run.status}")
    for name, value in sorted(run.means.items()):
        typer.echo(f"  {name:<20} {value:.3f}")
    if run.status == "failed":
        raise typer.Exit(EXIT_ERROR)


@eval_app.command("gate")
def gate(
    dataset: Annotated[str, typer.Argument(help="Dataset slug.")],
    version: Annotated[int | None, typer.Option(help="Pipeline version (default: active).")] = None,
    k: Annotated[int, typer.Option(help="Retrieval cutoff for the metrics.")] = 5,
    minimum: Annotated[
        list[str] | None,
        typer.Option("--min", help="Floor as metric=value, repeatable (hit_rate=0.85)."),
    ] = None,
    max_drop: Annotated[
        float | None, typer.Option(help="Largest allowed drop against the baseline run.")
    ] = None,
    baseline: Annotated[
        str | None, typer.Option(help="Baseline run id (default: the dataset's baseline).")
    ] = None,
    run_id: Annotated[
        str | None, typer.Option("--run", help="Gate an existing run instead of starting one.")
    ] = None,
    report: Annotated[Path | None, typer.Option(help="Write the verdict to this file.")] = None,
    fmt: Annotated[str, typer.Option("--format", help="markdown or json.")] = "markdown",
    url: Url = None,
    api_key: Key = None,
    project: ProjectOption = None,
) -> None:
    """Run a dataset (or take a finished run) and fail when metrics regress."""
    try:
        floors = parse_thresholds(minimum or [])
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    with _client(url, api_key, project) as rk:
        try:
            run = (
                rk.evals.wait(run_id)
                if run_id
                else rk.evals.run(dataset, pipeline_version=version, k=k)
            )
            verdict: GateResult | None = None
            if run.status == "completed":
                verdict = rk.evals.gate(
                    run.id,
                    min=floors or None,
                    max_drop=max_drop,
                    baseline_run_id=baseline,
                )
        except RAGKitError as exc:
            raise _fail(exc) from exc
    text = json_report(run, verdict) if fmt == "json" else markdown_report(run, verdict)
    typer.echo(text)
    if report is not None:
        report.write_text(text, encoding="utf-8")
    raise typer.Exit(exit_code(run, verdict))


if __name__ == "__main__":
    app()
