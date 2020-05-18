import os
import jinja2
import pathlib
import re

from typing import Union

from mullendore.markdown import markdown_to_html
from mullendore.plugins import plugin_functions, plugin_filters
from mullendore.templates import Loader


class Converter:
    """
    Worker class for converting files according to options it was created with.
    """

    def __init__(self, options: dict):
        self.options = options
        self.encoding = options.get("encoding")
        self.loader = Loader(encoding=self.encoding)
        self.env = jinja2.Environment(loader=self.loader)
        self.env.globals.update(plugin_functions)
        self.env.filters.update(plugin_filters)
        if options["env"]:
            self.env.globals.update(os.environ)
        if options["reference"]:
            self.references = self._build_references(
                options["reference"], options["root"]
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

    def convert(self, input_path: pathlib.Path, **context: dict) -> pathlib.Path:
        """
        Convert a Markdown file to a HTML and render its templates.

        Args:
            input_path: Path of the file to convert.

        Returns:
            Path of the converted file.

        Raises:
            jinja2.exceptions.TemplateError: If there was a template rendering issue.
        """

        input_path = input_path.resolve()
        self.loader.set_root_file(input_path)

        context["body"] = str(input_path)
        context["encoding"] = self.encoding
        context["references"] = self.references

        if self.options["template"]:
            template = self.get_template(self.options["template"].with_suffix(".html"))
        elif self.options["no_template"]:
            template = self.get_template(input_path)
        else:
            template = self.get_template("_default.html")

        if self.options["style"]:
            context["style"] = str(self.options["style"].with_suffix(".css"))
        else:
            context["style"] = "_default.css"

        if self.options["output"]:
            output_path = self.options["output"]
        else:
            output_path = input_path.with_suffix(".html")

        with output_path.open("w") as output_fh:
            output_fh.write(template.render(**context))

        return output_path

    def _build_references(self, path: pathlib.Path, root_dir: pathlib.Path):
        store = dict()
        markdown_to_html(path.read_text(encoding=self.encoding), dict(store=store))
        references = []
        for level, anchor, name in store["toc_list"]:
            if level != 2:
                continue
            if "/" in name:
                aliases = name.split("/")
            else:
                aliases = [name]
            for alias in aliases:
                alias = alias.strip()
                if not alias:
                    continue
                pat = re.compile(f"\\b({alias}s?)\\b", re.IGNORECASE)
                references.append(
                    (
                        pat,
                        f"/{path.relative_to(root_dir).with_suffix('.html')}#{anchor}",
                    )
                )
        references.sort(key=lambda ref: len(ref[0].pattern), reverse=True)
        return references
