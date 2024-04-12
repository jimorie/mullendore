import click
import os
import pathlib

from mullendore.convert import Converter

# from mullendore.markdown import get_markdown_metadata
from mullendore.types import Metadata, abspath

from typing import List, Mapping

AllMetadata = Mapping[pathlib.Path, Metadata]


@click.command()
@click.argument("args", nargs=-1, type=abspath)
@click.option(
    "-t",
    "--template",
    type=pathlib.Path,
    help=(
        "Path to the template to use. The template can use the `body` variable to "
        "include the given input path. If unspecified, a default template is used."
    ),
)
@click.option(
    "--no-template",
    is_flag=True,
    help="Convert Markdown to HTML directly without any template.",
)
@click.option("--env", is_flag=True, help="Use environment variables in templates.")
@click.option(
    "-o",
    "--output",
    type=abspath,
    help=(
        "Path where to write the output. By default the input path is used, "
        "with the suffix changed to `.html`."
    ),
)
@click.option(
    "-s",
    "--style",
    type=pathlib.Path,
    help=(
        "Path to the CSS stylesheet to use. If you use a custom template, this "
        "becomes the `style` variable."
    ),
)
@click.option(
    "-r",
    "--recursive",
    is_flag=True,
    help="Convert all `.md` files in the directory tree.",
)
@click.option(
    "--root",
    type=abspath,
    default=abspath("."),
    help="Root path for the site. Generated paths will be relative to this, if given.",
)
@click.option(
    "--reference",
    type=abspath,
    help=(
        "Path to a reference document. When this option is used text in the "
        "processed documents will be linked to matching headers in this document."
    ),
)
@click.option(
    "--reference-level",
    type=int,
    help="Header level used for references.",
    multiple=True,
)
@click.option(
    "--encoding", type=str, default="utf-8", help="Encoding used in the files."
)
def main(args: List[str], **options):
    """
    Convert Markdown files to HTML using Jinja templates.
    """
    if not args:
        raise click.UsageError("No input files given.")
    root_dir = options["root"]
    converter = Converter(options)
    paths = resolve_paths(args, root_dir, options["recursive"])
    if len(paths) <= 1:
        common_prefix = paths[0].parent.relative_to(root_dir)
    else:
        common_prefix = pathlib.Path(os.path.commonprefix(paths)).relative_to(root_dir)
    converter.convert_all(
        paths, root_dir=root_dir, common_prefix=common_prefix, store=dict()
    )


def resolve_paths(
    args: List[str], root_dir: pathlib.Path, recursive: bool
) -> List[pathlib.Path]:
    paths = []
    for arg in args:
        input_path = pathlib.Path(arg)
        if input_path.is_file():
            paths.append(input_path)
        elif input_path.is_dir():
            if recursive:
                paths.extend(input_path.rglob("*.md"))
            else:
                click.echo(
                    f"{input_path.relative_to(root_dir)}: "
                    "directory skipped (use the --recursive option)",
                    err=True,
                )
                continue
        elif "**" in input_path.parts:
            i = input_path.parts.index("**")
            for path in pathlib.Path(*input_path.parts[:i]).glob(
                "/".join(input_path.parts[i:])
            ):
                paths.append(path)
        else:
            click.echo(f"{input_path.relative_to(root_dir)}: no such file", err=True)
            continue
    # The ordering is important for metadata inheritance
    paths.sort(key=lambda path: (path.parent, path.name != "index.md", path.name))
    return paths
