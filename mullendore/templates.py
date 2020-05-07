import pathlib
import jinja2

from typing import Iterable, Tuple, Callable, Union

from mullendore.markdown import markdown_to_html


class Loader(jinja2.BaseLoader):
    """
    Custom jinja2 Loader that works like `jinja2.FileSystemLoader` where one of the
    paths in the searchpath is the parent directory of the file being converted.

    Loaded templates are customized to convert Markdown for templates whose name ends
    with the `.md` suffix.
    """

    def __init__(self, encoding: str = "utf-8", followlinks: bool = False):
        self.encoding = encoding
        self.followlinks = followlinks
        self.root_file = None
        self.root_dir = None

    def set_root_file(self, path: pathlib.Path):
        self.root_file = path
        self.root_dir = path.parent

    @property
    def searchpath(self) -> Iterable[pathlib.Path]:
        if self.root_dir:
            yield self.root_dir
        yield pathlib.Path(__file__).parent.joinpath("templates")
        yield pathlib.Path(__file__).parent.joinpath("styles")

    def get_source(
        self, environment: jinja2.Environment, template: str
    ) -> Tuple[str, str, Callable]:
        path = pathlib.Path(template)
        if not path.is_absolute():
            for searchpath in self.searchpath:
                tmp = searchpath.joinpath(path)
                if tmp.is_file():
                    path = tmp
                    break
            else:
                raise jinja2.exceptions.TemplateNotFound(template)
        elif not path.is_file():
            raise jinja2.exceptions.TemplateNotFound(template)

        contents = path.read_text(encoding=self.encoding)
        mtime = path.stat().st_mtime

        def uptodate():
            try:
                return path.stat().st_mtime == mtime
            except OSError:
                return False

        environment.last_loaded_path = path

        return contents, template, uptodate

    @jinja2.utils.internalcode
    def load(
        self,
        environment: jinja2.Environment,
        name: Union[str, pathlib.Path],
        globals: dict = None,
    ) -> jinja2.Template:
        if type(name) is not str:
            name = str(name.resolve())
        template = jinja2.FileSystemLoader.load(
            self, environment, name, globals=globals
        )
        root_render_func = template.root_render_func

        def render_func(
            ctx,
            *args,
            name=name,
            path=environment.last_loaded_path,
            root_render_func=root_render_func,
            **kwargs,
        ):
            store = ctx["store"]
            if "paths" not in store:
                store["paths"] = []
            store["paths"].append(path)
            # Don't convert child Markdown twice
            previously_in_markdown = store.get("in_markdown", False)
            if name.endswith(".md") and not previously_in_markdown:
                store["in_markdown"] = True
                html = markdown_to_html(
                    jinja2.utils.concat(root_render_func(ctx, *args, **kwargs)),
                    ctx.parent,
                )
                store["in_markdown"] = previously_in_markdown
                yield html
            else:
                yield from root_render_func(ctx, *args, **kwargs)
            store["paths"].pop()

        template.root_render_func = render_func
        return template
