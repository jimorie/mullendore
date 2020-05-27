import jinja2
import pathlib

from typing import Callable, Mapping, Optional, Union

from mullendore.markdown import markdown_to_html


plugin_functions = {}
plugin_filters = {}


def template_function(func: Callable) -> Callable:
    """
    Decorator to make a function available in templates.
    """
    func = jinja2.contextfunction(func)
    plugin_functions[func.__name__] = func
    return func


def template_filter(func: Callable) -> Callable:
    """
    Decorator to make a function available as a filter in templates.
    """
    func = jinja2.contextfilter(func)
    plugin_filters[func.__name__] = func
    return func


@template_function
def debug(ctx: Mapping, text: str) -> jinja2.Markup:
    """
    Debug print from templates.
    """
    print(text)
    return jinja2.Markup("")


@template_filter
def markdown(ctx: Mapping, text: str) -> jinja2.Markup:
    """
    Template filter for converting Markdown to HTML.
    """
    store = ctx["store"]
    previously_in_markdown = store.get("in_markdown", False)
    if not previously_in_markdown:
        store["in_markdown"] = True
        html = markdown_to_html(text, ctx.parent, skip_toc=True)
        store["in_markdown"] = previously_in_markdown
        return jinja2.Markup(html)
    return text


@template_function
def here(ctx: Mapping) -> pathlib.Path:
    """
    Return the path of the current template.
    """
    store = ctx["store"]
    paths = store.get("paths")
    path = paths[-1] if paths else pathlib.Path(".")
    return path.parent


@template_filter
def href(ctx: Mapping, path: Union[str, pathlib.Path]) -> jinja2.Markup:
    """
    Convert a local path to a href link.
    """
    if type(path) is str:
        path = pathlib.Path(path)
    if not path.is_absolute():
        path = here(ctx).joinpath(path)
    if path.suffix == ".md":
        path = path.with_suffix(".html")
    path = str(path.relative_to(ctx["root_dir"]))
    return jinja2.Markup(f"/{path}")


@template_function
def toc(ctx: Mapping) -> jinja2.Markup:
    """
    Return previously generated TOC.
    """
    return jinja2.Markup(ctx["store"].get("toc") or "")


@template_function
def glob(ctx: Mapping, pattern: str = "*", exclude: Optional[list] = None):
    path = pathlib.Path(pattern)
    if not path.is_absolute():
        path = here(ctx).joinpath(path)
    pattern = path.name
    path = path.parent
    return (
        str(p.resolve())
        for p in sorted(path.glob(pattern))
        if exclude is None or p.name not in exclude
    )


@template_function
def menu_links(ctx: Mapping) -> str:
    all_metadata = ctx["store"].get("all_metadata") or {}
    out = ""
    for path, metadata in sorted(
        all_metadata.items(), key=lambda item: item[1].get("menu-item") or ""
    ):
        if not metadata.get("menu-item") or not metadata.get("title"):
            continue
        if str(path) == "index.md":
            continue
        out += f'<a href="{href(ctx, path)}">{metadata.get("title")}</a>\n'
    return out


@template_function
def list_files(ctx: Mapping, path: Union[pathlib.Path, str]) -> str:
    if type(path) is str:
        path = pathlib.Path(path)
    out = "<ul>\n"
    for filepath in sorted(path.glob("*")):
        if filepath.name.startswith("."):
            continue
        if not filepath.is_file():
            continue
        out += f'<li><a href="{href(ctx, filepath)}">{filepath.name}</a></li>\n'
    out += "</ul>\n"
    return out


@template_function
def include_section(
    ctx: Mapping,
    path: Union[pathlib.Path, str],
    header: str,
    include_blockquotes: bool = False,
) -> str:
    if type(path) is str:
        path = pathlib.Path(path)
    out = []
    level = 0
    for line in path.read_text().splitlines():
        if include_blockquotes is False and line.startswith(">"):
            continue
        if line.startswith("#"):
            line_level = line.count("#")
            if not level:
                line_header = line[line_level:].strip()
                if line_header == header:
                    level = line_level
                    out.append(line)
            elif line_level <= level:
                break
            else:
                out.append(line)
        elif level:
            out.append(line)
    return "\n".join(out)
