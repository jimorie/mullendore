import click
import os
import jinja2
import pathlib
import re
import time
import yaml

from typing import Union, Dict, List, Tuple, Iterable

from mullendore.markdown import markdown_to_html
from mullendore.plugins import plugin_functions, plugin_filters
from mullendore.templates import Loader, Environment
from mullendore.types import Metadata


ReferencesMetadata = Dict[str, Tuple[str, pathlib.Path, str]]
References = Tuple[re.Pattern, ReferencesMetadata]


class Converter:
    """
    Worker class for converting files according to options it was created with.
    """

    def __init__(self, options: dict):
        self.options = options
        self.encoding = options.get("encoding")
        self.loader = Loader(encoding=self.encoding)
        self.env = Environment(loader=self.loader)
        self.env.globals.update(plugin_functions)
        self.env.filters.update(plugin_filters)
        if options["env"]:
            self.env.globals.update(os.environ)
        if options["reference"]:
            self.references = self._build_references(
                options["reference"],
                options["root"],
                options["reference_level"] or [2],
            )
        else:
            self.references = None

    def get_template(self, path: Union[str, pathlib.Path]) -> jinja2.Template:
        """
        Load a template.

        Args:
            path: Path of the template.

        Returns:
            The loaded template.

        Raises:
            jinja2.exceptions.TemplateNotFound: If no template was found.
        """
        return self.env.get_template(str(path))

    def convert_all(self, paths: List[pathlib.Path], **ctx_vars) -> List[pathlib.Path]:
        """
        Convert a list of paths.

        This will compile all the listed page templates and their metadata
        before converting the individual pages. This makes metadata for all
        pages available to the individual pages while rendering.

        Args:
            paths: List of paths to convert.
            ctx_vars: Dict of variables available to the templates.

        Returns:
            List of the paths to the converted files.

        Raises:
            jinja2.exceptions.TemplateError: If there was a template rendering issue.
        """
        ctx_vars["pages"] = pages = {}
        try:
            for path in paths:
                template = self.get_template(path)
                template.page = True
                pages[path] = template
                # Update template metadata to inherit from parent index.md pages
                parent = path.parent.parent if path.name == "index.md" else path.parent
                while parent.stem and parent / "index.md" not in pages:
                    parent = parent.parent
                if parent / "index.md" in pages:
                    template.metadata = pages[parent / "index.md"].metadata.new_child(
                        template.metadata
                    )
                else:
                    template.metadata = Metadata(template.metadata)
            return [
                self.convert(path, **ctx_vars, **pages[path].metadata) for path in paths
            ]
        except jinja2.exceptions.TemplateNotFound as e:
            click.echo(f"{path}: no template found named '{e}'", err=True)
        except jinja2.exceptions.TemplateSyntaxError as e:
            click.echo(f"{path}: {e.name} line {e.lineno}: {e}", err=True)
        except jinja2.exceptions.TemplateError as e:
            click.echo(f"{path}: {e}", err=True)

    def convert(self, input_path: pathlib.Path, **ctx_vars) -> pathlib.Path:
        """
        Convert a Markdown file to a HTML and render its templates.

        Args:
            input_path: Path of the file to convert.
            ctx_vars: Dict of variables available to the template.

        Returns:
            Path of the converted file.

        Raises:
            jinja2.exceptions.TemplateError: If there was a template rendering issue.
        """

        starttime = time.time()

        root_dir = ctx_vars["root_dir"]

        click.echo(f"{input_path.relative_to(root_dir)}...", nl=False)

        input_path = input_path.resolve()
        self.loader.set_root_file(input_path)

        ctx_vars["body"] = str(input_path)
        ctx_vars["encoding"] = self.encoding
        ctx_vars["references"] = self.references
        ctx_vars["store"] = dict()

        if self.options["template"]:
            template = self.get_template(self.options["template"].with_suffix(".html"))
        elif self.options["no_template"]:
            template = self.get_template(input_path)
        else:
            template = self.get_template("_default.html")

        if self.options["style"]:
            ctx_vars["style"] = str(self.options["style"].with_suffix(".css"))
        else:
            ctx_vars["style"] = "_default.css"

        if self.options["output"]:
            output_path = self.options["output"]
        else:
            output_path = input_path.with_suffix(".html")

        with output_path.open("w") as output_fh:
            output_fh.write(template.render(**ctx_vars))

        click.echo(
            f" -> {output_path.relative_to(root_dir)} "
            f"({(time.time() - starttime):.2f} s)"
        )

        return output_path

    def _build_references(
        self, path: pathlib.Path, root_dir: pathlib.Path, levels: Iterable[int]
    ) -> References:
        store: Dict = dict()
        ctx: Dict = dict(store=store)
        markdown_to_html(path.read_text(encoding=self.encoding), ctx)
        regexes = []
        metadata = {}
        index = 1
        for level, anchor, name in store["toc_list"]:
            if level not in levels:
                continue
            if "{" in name:
                i = name.find("{")
                options = yaml.safe_load(name[i:])
                name = name[:i]
            else:
                options = {}
            if "//" in name:
                _, name = name.split("//", 1)
            if "/" in name:
                aliases = name.split("/")
            else:
                aliases = [name]
            data = [
                f"/{path.relative_to(root_dir).with_suffix('.html')}#{anchor}",
                path,
                anchor,
            ]
            for alias in aliases:
                alias = alias.strip()
                if not alias:
                    continue
                group = f"g{index}"
                index += 1
                metadata[group] = data
                flags = ""
                if not options.get("case"):
                    flags += "i"
                if flags:
                    flags = f"?{flags}:"
                regexes.append(f"(?P<{group}>\\b({flags}{re.escape(alias)}s?)\\b)")
        regexes.sort(key=lambda regex: len(regex), reverse=True)
        pattern = re.compile("|".join(regexes))
        return (pattern, metadata)
