import pathlib
import jinja2
import yaml
import wrapt

from typing import Iterable, Tuple, Callable, Optional, Dict, TextIO

from mullendore.markdown import markdown_to_html


class Template(wrapt.ObjectProxy):
    def __init__(self, *args, **kwargs):
        wrapt.ObjectProxy.__init__(self, *args, **kwargs)
        self.metadata = None
        self.filepath = None
        self.page = False

    def render(self, **ctx):
        ctx["store"].setdefault("here", [])
        ctx["store"]["here"].append(self)
        previously_in_markdown = ctx["store"].get("in_markdown", False)
        if self.filename.endswith(".md") and not previously_in_markdown:
            ctx["store"]["in_markdown"] = True
            result = self.__wrapped__.render(**ctx)
            result = markdown_to_html(result, ctx)
            ctx["store"]["in_markdown"] = False
        else:
            result = self.__wrapped__.render(**ctx)
        ctx["store"]["here"].pop()
        return result

    def root_render_func(self, ctx):
        ctx["store"].setdefault("here", [])
        ctx["store"]["here"].append(self)
        previously_in_markdown = ctx["store"].get("in_markdown", False)
        if self.filename.endswith(".md") and not previously_in_markdown:
            ctx["store"]["in_markdown"] = True
            result = jinja2.utils.concat(self.__wrapped__.root_render_func(ctx))
            result = markdown_to_html(result, ctx)
            ctx["store"]["in_markdown"] = False
        else:
            result = jinja2.utils.concat(self.__wrapped__.root_render_func(ctx))
        ctx["store"]["here"].pop()
        return result

    def new_context(self, vars=None, shared=False, locals=None):
        if vars is None:
            vars = {}
        ctx = self.__wrapped__.new_context(vars=vars, shared=shared, locals=locals)
        return ctx


class Context(jinja2.runtime.Context):
    def __init__(self, environment, parent, name, blocks):
        super().__init__(environment, parent, name, blocks)
        self.template_stack = []


jinja2.Environment.context_class = Context


class Environment(jinja2.Environment):
    def join_path(self, template, parent):
        if parent:
            parent_path = self.loader.find_path(parent)
            if parent_path:
                path = parent_path.parent.joinpath(template)
                if path.is_file():
                    return str(path.resolve())
        return template


class Loader(jinja2.BaseLoader):
    """
    Custom jinja2 Loader that works like `jinja2.FileSystemLoader` where one of the
    paths in the searchpath is the parent directory of the file being converted.

    Loaded templates are customized to convert Markdown for templates whose name ends
    with the `.md` suffix.
    """

    def __init__(self, encoding: Optional[str] = None, followlinks: bool = False):
        self.encoding = encoding or "utf-8"
        self.followlinks = followlinks
        self.root_file: Optional[pathlib.Path] = None
        self.root_dir: Optional[pathlib.Path] = None
        self.loadinfo = []

    def set_root_file(self, path: pathlib.Path):
        self.root_file = path
        self.root_dir = path.parent

    @property
    def searchpath(self) -> Iterable[pathlib.Path]:
        if self.root_dir:
            yield self.root_dir
        yield pathlib.Path(__file__).parent.joinpath("templates")
        yield pathlib.Path(__file__).parent.joinpath("styles")

    def find_path(self, name: str) -> pathlib.Path:
        path = pathlib.Path(name)
        if path.is_absolute() and path.is_file():
            return path
        for searchpath in self.searchpath:
            tmp = searchpath.joinpath(path)
            if tmp.is_file():
                return tmp
        return None

    def get_source(
        self, environment: jinja2.Environment, template: str
    ) -> Tuple[str, str, Callable]:
        path = self.find_path(template)
        if not path:
            raise jinja2.exceptions.TemplateNotFound(template)

        with path.open(mode="r", encoding=self.encoding) as fh:
            self.loadinfo.append((path, self._read_yaml_header(fh)))
            contents = fh.read()

        mtime = path.stat().st_mtime

        def uptodate():
            try:
                return path.stat().st_mtime == mtime
            except OSError:
                return False

        return contents, template, uptodate

    @jinja2.utils.internalcode
    def load(self, *args, **kwargs):
        template = Template(jinja2.BaseLoader.load(self, *args, **kwargs))
        loadinfo = self.loadinfo.pop()
        if not loadinfo:
            raise RuntimeError("Template loaded without path or metadata")
        template.filepath, template.metadata = loadinfo
        return template

    def _read_yaml_header(self, fh: TextIO) -> Dict:
        if fh.readline() != "---\n":
            fh.seek(0)
            return 0, {}
        blob = ""
        linecount = 1
        while True:
            linecount += 1
            line = fh.readline()
            if not line or line == "---\n":
                break
            blob += line
        metadata = yaml.safe_load(blob)
        metadata["metadata_linecount"] = linecount
        metadata = self._process_metadata(metadata, fh.name)
        return metadata

    @staticmethod
    def _process_metadata(metadata: Dict, filename: str) -> Dict:
        for k, v in list(metadata.items()):
            if isinstance(v, str):
                if v.startswith("path(") and v.endswith(")"):
                    path = pathlib.Path(v[len("path(") : -1])
                    if not path.is_absolute():
                        path = pathlib.Path(filename).resolve().parent / path
                    metadata[k] = path
        return metadata
