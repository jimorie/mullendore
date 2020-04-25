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


_md_plustable_pattern = re.compile(r"^\+\+\+(.*?)\n(.*?)\n\+\+\+\n", re.DOTALL|re.MULTILINE)
_md_plustable_cell_pattern = re.compile("  +")


@markdown_preprocessor
def plustables(text):
    """
    Support for thist type of table syntax:

        +++
        Header 1    Header 2
        R1C1        R1C2
        R2C1        R2C2
        +++
    """
    def process_table(match):
        options = [opt.strip() for opt in match.group(1).split(",")]
        table = match.group(2)
        html = f'<table class="{"small" if "small" in options else ""}">\n<thead>\n'
        header = True
        width = 0
        for line in table.split("\n"):
            if line == "++":
                html += "</tbody>\n<thead>\n"
                header = True
                continue
            cells = _md_plustable_cell_pattern.split(line)
            cells.extend([""] * (width - len(cells)))
            if header:
                html += "<tr>"
                html += "".join(f"<th>{cell}</th>" for cell in cells)
                html += "</tr>\n</thead>\n<tbody>\n"
                header = False
                width = len(cells)
            else:
                html += "<tr>"
                html += "".join(f"<td>{cell}</td>" for cell in cells)
                html += "</tr>\n"
        html += "</tbody>\n</table>\n"
        return html
    return _md_plustable_pattern.sub(process_table, text)


@markdown_postprocessor
def swedish_quotes(text):
    return text.replace("&#8216;", "&#8217;").replace("&#8220;", "&#8221;")


@markdown_postprocessor
@pass_context
def link_references(ctx, text):
    if ctx.get("no-refs"):
        return text
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


_html_img_pattern = re.compile(r'<img .*?/>')
_html_img_src_pattern = re.compile('src="(.*?)"')
_html_img_alt_pattern = re.compile('alt="(.*?)"')
_html_img_hashtag_pattern = re.compile('#\\w+')


@markdown_postprocessor
def link_html_images(text):
    def repl(match):
        src = _html_img_src_pattern.search(match.group()).group(1)
        alt = _html_img_alt_pattern.search(match.group()).group(1)
        classes = []
        for hashtag in _html_img_hashtag_pattern.findall(alt):
            alt = alt.replace(hashtag, "")
            classes.append(hashtag.strip("#"))
        if not src.endswith(".png"):
            classes.append("shadow")
        return f'<a href="{src}"><img class="{" ".join(classes)}" src="{src}" alt="{alt}" /></a>'
    return _html_img_pattern.sub(repl, text)


_html_header_pattern = re.compile("<h([0-9]).*?>")


@markdown_postprocessor
def header_sections(text):
    out = ""
    last_pos = 0
    last_lvl = 0
    for match in _html_header_pattern.finditer(text):
        pos = match.start()
        lvl = int(match.group(1))
        if last_lvl and lvl > last_lvl and pos < last_pos + 500:
            continue
        out += text[last_pos:pos]
        if last_lvl:
            out += '</div>\n'
        out += '<div class="no-break-section">\n'
        last_pos = pos
        last_lvl = lvl
    out += text[last_pos:]
    if last_lvl:
        out += '</div>\n'
    return out


class Markdown(markdown2.Markdown):
    def __init__(self, *args, **kwargs):
        kwargs["extras"] = ["toc", "metadata", "smarty-pants"]
        markdown2.Markdown.__init__(self, *args, **kwargs)
        self.ctx = None

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
    text = _preprocess(ctx, text)
    html = markdowner.convert(text)
    html = _postprocess(ctx, html)
    markdowner.ctx = None
    toc = markdowner._toc
    if toc and skip_toc is False:
        ctx["store"]["toc_list"] = toc
        ctx["store"]["toc"] = "</ol>".join(markdown2.calculate_toc_html(toc).replace("<ul>", "<ol>", 1).rsplit("</ul>", 1))
    return html


def get_markdown_metadata(text: str) -> dict:
    markdowner.metadata = {}
    markdowner._extract_metadata(text)
    return markdowner.metadata


def _preprocess(ctx, text):
    for func in preprocessors:
        if hasattr(func, "pass_context"):
            text = func(ctx, text)
        else:
            text = func(text)
    return text


def _postprocess(ctx, text):
    for func in postprocessors:
        if hasattr(func, "pass_context"):
            text = func(ctx, text)
        else:
            text = func(text)
    return text
