import markdown2
import re

from typing import Callable, Optional, Mapping

preprocessors = []
postprocessors = []


def markdown_preprocessor(func: Callable) -> Callable:
    """
    Decorator to mark a function as a markdown preprocessor.
    """
    preprocessors.append(func)
    return func


def markdown_postprocessor(func: Callable) -> Callable:
    """
    Decorator to mark a function as a markdown postprocessor.
    """
    postprocessors.append(func)
    return func


def pass_context(func: Callable) -> Callable:
    """
    Decorator to mark a markdown processor to have context passed to it.
    """
    func.pass_context = True
    return func


@markdown_postprocessor
def swedish_quotes(text):
    return text.replace("&#8216;", "&#8217;").replace("&#8220;", "&#8221;")


@markdown_postprocessor
@pass_context
def link_references(ctx, text):
    references = ctx.get("references")
    if not references:
        return text
    dont_touch = {"a", "h1", "h2", "h3", "h4", "h5", "h6"}
    for pattern, url in references:
        tmp = ""
        for part, tags in _body_parts(text):
            if tags is None or dont_touch.intersection(tags):
                tmp += part
            else:
                tmp += pattern.sub(f'<a class="reference" href="{url}">\\1</a>', part)
        text = tmp
    return text


def _body_parts(text):
    tags = []
    tmp = text
    while tmp:
        i = tmp.find("<")
        if i < 0:
            break
        yield tmp[:i], tags
        tmp = tmp[i:]
        if tmp.startswith("</"):
            tags.pop()
        else:
            i = min(tmp.find(" "), tmp.find(">"))
            tags.append(tmp[1:i])
        i = tmp.find(">")
        if tmp[i - 1] == "/":
            tags.pop()
        yield tmp[: i + 1], None
        tmp = tmp[i + 1 :]
    yield tmp, tags


_md_img_pattern = re.compile(r"\!\[(.*?)\]\((.*?)\)")


@markdown_preprocessor
def link_images(text):
    return _md_img_pattern.sub(r"[![\1](\2)](\2)", text)


class Markdown(markdown2.Markdown):
    def __init__(self, *args, **kwargs):
        kwargs["extras"] = ["toc", "metadata", "smarty-pants"]
        markdown2.Markdown.__init__(self, *args, **kwargs)
        self.ctx = None

    def preprocess(self, text):
        for func in preprocessors:
            if hasattr(func, "pass_context"):
                text = func(self.ctx, text)
            else:
                text = func(text)
        return text

    def postprocess(self, text):
        for func in postprocessors:
            if hasattr(func, "pass_context"):
                text = func(self.ctx, text)
            else:
                text = func(text)
        return text

    def _extract_metadata(self, text):
        if text.startswith("---"):
            return markdown2.Markdown._extract_metadata(self, text)
        return text


markdowner = Markdown()


def markdown_to_html(
    text: str, ctx: Optional[Mapping] = None, skip_toc: bool = False
) -> str:
    """
    Convert Markdown text to HTML.
    """
    markdowner._toc = None
    markdowner.ctx = ctx
    html = markdowner.convert(text)
    markdowner.ctx = None
    toc = markdowner._toc
    if toc and skip_toc is False:
        ctx["store"]["toc_list"] = toc
        ctx["store"]["toc"] = markdown2.calculate_toc_html(toc)
    return html


def get_markdown_metadata(text: str) -> dict:
    markdowner.metadata = {}
    markdowner._extract_metadata(text)
    return markdowner.metadata
