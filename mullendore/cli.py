import click
import jinja2
import os
import pathlib

from typing import List

from mullendore.convert import Converter
from mullendore.markdown import get_markdown_metadata
from mullendore.paths import path, abspath


@click.command()
@click.argument("files", nargs=-1, type=abspath)
@click.option(
    "-t",
    "--template",
    type=path,
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
@click.option(
    "--env", is_flag=True, help="Use environment variables in templates.",
)
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
    type=path,
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
    "--encoding", type=str, default="utf-8", help="Encoding used in the files.",
)
def main(files: List[str], **options):
    """
    Convert Markdown files to HTML using Jinja templates.
    """
    converter = Converter(options)
    if not files:
        raise click.UsageError("No input files given.")
    root_dir = options["root"]
    paths = []
    for input_path in files:
        if input_path.is_file():
            paths.append(input_path)
        elif input_path.is_dir():
            if options["recursive"]:
                paths.extend(input_path.rglob("*.md"))
            else:
                click.echo(
                    f"{input_path.relative_to(root_dir)}: "
                    "directory skipped (use the --recursive option)",
                    err=True,
                )
                continue
        else:
            click.echo(f"{input_path.relative_to(root_dir)}: no such file", err=True)
            continue
    all_metadata = {}
    site_metadata = None
    for file_path in paths:
        metadata = get_markdown_metadata(
            file_path.read_text(encoding=options.get("encoding"))
        )
        all_metadata[file_path] = metadata
        if file_path.name == "index.md":
            site_metadata = metadata
    for metadata in all_metadata.values():
        if metadata != site_metadata:
            for k, v in site_metadata.items():
                metadata.setdefault(k, v)
        metadata["site_title"] = site_metadata.get("title")
    common_prefix = pathlib.Path(os.path.commonprefix(paths)).relative_to(root_dir)
    for file_path in paths:
        metadata = all_metadata[file_path]
        store = dict(all_metadata=all_metadata)
        try:
            output_path = converter.convert(
                file_path,
                root_dir=root_dir,
                common_prefix=common_prefix,
                store=store,
                **metadata,
            )
        except jinja2.exceptions.TemplateNotFound as e:
            click.echo(f"{file_path}: no template found named '{e}'", err=True)
        except jinja2.exceptions.TemplateSyntaxError as e:
            click.echo(f"{file_path}: {e.name} line {e.lineno}: {e}", err=True)
        except jinja2.exceptions.TemplateError as e:
            click.echo(f"{file_path}: {e}", err=True)
        else:
            click.echo(
                f"{file_path.relative_to(root_dir)} "
                f"-> {output_path.relative_to(root_dir)}"
            )
            continue
