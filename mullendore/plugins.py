import jinja2
import pathlib

from typing import Callable, Optional, Union, Any

from mullendore.markdown import markdown_to_html

Pathlike = Union[str, pathlib.Path]

plugin_functions = {}
plugin_filters = {}


def template_function(func: Callable) -> Callable:
    """
    Decorator to make a function available in templates.
    """
    ctxfunc: Callable = jinja2.contextfunction(func)
    plugin_functions[ctxfunc.__name__] = ctxfunc
    return ctxfunc


def template_filter(func: Callable) -> Callable:
    """
    Decorator to make a function available as a filter in templates.
    """
    ctxfilter: Callable = jinja2.contextfilter(func)
    plugin_filters[ctxfilter.__name__] = ctxfilter
    return ctxfilter


@template_function
def debug(ctx: jinja2.runtime.Context, text: str) -> jinja2.Markup:
    """
    Debug print from templates.
    """
    print(text)
    return jinja2.Markup("")


@template_filter
def markdown(ctx: jinja2.runtime.Context, text: str) -> jinja2.Markup:
    """
    Template filter for converting Markdown to HTML.
    """
    store = ctx["store"]
    previously_in_markdown = store.get("in_markdown", False)
    if not previously_in_markdown:
        store["in_markdown"] = True
        parent: Any = ctx.parent
        html = markdown_to_html(text, parent, skip_toc=True)
        store["in_markdown"] = False
        return jinja2.Markup(html)
    return jinja2.Markup(text)


@template_function
def here(ctx: jinja2.runtime.Context) -> Optional[pathlib.Path]:
    """
    Return the path of the current template.
    """
    templates = ctx["store"].get("here")
    return templates[-1].filepath.parent if templates else None


@template_filter
def href(ctx: jinja2.runtime.Context, pathlike: Pathlike) -> jinja2.Markup:
    """
    Convert a local path to a href link.
    """
    path = pathlib.Path(pathlike) if isinstance(pathlike, str) else pathlike
    if not path.is_absolute():
        path = ctx["root_dir"] / ctx["common_prefix"] / path
    path = path.relative_to(ctx["root_dir"])
    if path.suffix == ".md":
        path = path.with_suffix(".html")
    return jinja2.Markup(f"/{path}")


@template_function
def toc(ctx: jinja2.runtime.Context) -> jinja2.Markup:
    """
    Return previously generated TOC.
    """
    return jinja2.Markup(ctx["store"].get("toc") or "")


@template_function
def glob(
    ctx: jinja2.runtime.Context, pattern: str = "*", exclude: Optional[list] = None
):
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
def menu_links(ctx: jinja2.runtime.Context) -> str:
    pages = ctx["pages"] or {}
    out = ""
    for path, template in sorted(
        pages.items(), key=lambda item: item[1].metadata.get("menu-item", 0)
    ):
        if "menu-item" not in template.metadata or "title" not in template.metadata:
            continue
        out += f'<a href="{href(ctx, path)}">{template.metadata.get("title")}</a>\n'
    return out


@template_function
def list_files(ctx: jinja2.runtime.Context, pathlike: Pathlike) -> str:
    path = pathlib.Path(pathlike) if isinstance(pathlike, str) else pathlike
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
    ctx: jinja2.runtime.Context,
    pathlike: Pathlike,
    header: str,
    include_blockquotes: bool = False,
) -> str:
    path = pathlib.Path(pathlike) if isinstance(pathlike, str) else pathlike
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
