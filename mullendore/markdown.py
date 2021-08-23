import html
import jinja2
import markdown2
import pathlib
import re

from mullendore.git import GitRepo, CommitMap

from typing import Callable, Dict, List


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
    setattr(func, "pass_context", True)
    return func


@markdown_preprocessor
@pass_context
def show_changes_since(ctx: jinja2.runtime.Context, text: str) -> str:
    """
    Show changes from the git blame data for each header. This preprocessor
    must run first, since it relies on the line numbers from the checked in
    file.
    """
    changes_since = ctx.get("show-changes-since")
    changes_repo = ctx.get("show-changes-repo")
    if not changes_since:
        return text
    file_path = pathlib.Path(ctx.get("body")).resolve()
    repo = GitRepo(file_path.parent)
    commits = repo.blame_file(file_path, changes_since=changes_since)
    lines = enumerate(text.splitlines(), ctx.get("metadata_linecount", 0) + 1)
    changes: CommitMap = {}
    out: List[str] = []
    body: List[str] = []
    header = None

    def add_section(header, body, changes, out):
        if header:
            if changes:
                change_list = "".join(
                    (
                        '<div class="change-item"><span class="change-author">'
                        f'{html.escape(commit["author"])}'
                        "</span> "
                        f'<span class="change-date">{commit["date"]}:</span>'
                        "<br/>"
                        '<span class="change-summary">'
                        f'<a href="{changes_repo.format(commit=commit["hash"])}">'
                        f'{html.escape(commit["summary"])}'
                        "</a></span></div>"
                    )
                    for commit in changes.values()
                )
                header += (
                    f'<div class="tooltip change">'
                    f'<div class="change-icon"><span>{len(changes)}</span></div>'
                    f'<div class="change-list">{change_list}</div>'
                    f"</div>"
                )
            out.append(header)
        out.extend(body)
        body.clear()
        changes.clear()

    for line_num, line in lines:
        if line.startswith("#"):
            add_section(header, body, changes, out)
            header = line
        else:
            body.append(line)
        if line:
            commit = commits.get(line_num)
            if commit:
                changes[commit["hash"]] = commit
    add_section(header, body, changes, out)
    out = "\n".join(out)
    return out


_md_plustable_pattern = re.compile(
    r"^\+\+\+(.*?)\n(.*?)\n\+\+\+\n", re.DOTALL | re.MULTILINE
)
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
        html = (
            f'<div class="scroll-x">\n'
            f'<table class="{"small" if "small" in options else ""}">\n<thead>\n'
        )
        header = True
        width = 0
        for line in table.split("\n"):
            if line == "++":
                html += "</tbody>\n<thead>\n"
                header = True
                continue
            cells = _md_plustable_cell_pattern.split(line)
            cells = [simple_markdown_to_html(cell) for cell in cells]
            cells.extend([""] * (width - len(cells)))
            if header:
                html += "<tr>"
                if "nowrap" in options and cells:
                    html += f'<th class="nowrap">{cells.pop(0)}</th>'
                html += "".join(f"<th>{cell}</th>" for cell in cells)
                html += "</tr>\n</thead>\n<tbody>\n"
                header = False
                width = len(cells)
            else:
                html += "<tr>"
                if "nowrap" in options and cells:
                    html += f'<td class="nowrap">{cells.pop(0)}</td>'
                html += "".join(f"<td>{cell}</td>" for cell in cells)
                html += "</tr>\n"
        html += "</tbody>\n</table>\n</div>\n"
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
    file_path = ctx.get("body")
    if not file_path:
        return text
    file_path = pathlib.Path(file_path).resolve()
    references = ctx.get("references")
    if not references:
        return text
    pattern, metadata = references
    dont_touch = {"a", "span", "h1", "h2", "h3", "h4", "h5", "h6"}
    linked_text = ""
    for pos, endpos, tags, headers in _body_parts(text):
        if tags is None or any(tag in dont_touch for tag in tags):
            linked_text += text[pos:endpos]
            continue
        for match in pattern.finditer(text, pos, endpos):
            matchpos, matchendpos = match.span()
            linked_text += text[pos:matchpos]
            url, path, anchor = metadata[match.lastgroup]
            if path == file_path and anchor in (a for _, a in headers):
                linked_text += f'<span class="self-reference">{match.group()}</span>'
            else:
                linked_text += f'<a class="reference" href="{url}">{match.group()}</a>'
            pos = matchendpos
        linked_text += text[pos:endpos]
    return linked_text


_html_id_pattern = re.compile(' id="(.*?)"')


def _body_parts(text):
    tags = []
    headers = []
    pos = 0
    while pos < len(text):
        tagpos = text.find("<", pos)
        if tagpos < 0:
            break
        yield pos, tagpos, tags, headers
        # Keep track of tags
        endpos = text.find(">", tagpos)
        if text[tagpos + 1] == "/":
            tags.pop()
        elif text[endpos - 1] != "/":
            try:
                tag, _ = text[tagpos + 1 : endpos].split(" ", 1)
            except ValueError:
                tag = text[tagpos + 1 : endpos]
            tags.append(tag)
            # Keep track of headers
            if tag[0] == "h":
                try:
                    level = int(tag[1])
                    header_id = _html_id_pattern.search(text, tagpos, endpos).group(1)
                    while headers and headers[-1][0] >= level:
                        headers.pop()
                    headers.append((level, header_id))
                except (ValueError, AttributeError):
                    pass
        yield tagpos, endpos, None, headers
        pos = endpos
    yield pos, len(text), tags, headers


_html_img_pattern = re.compile(r"<img .*?/>")
_html_img_src_pattern = re.compile('src="(.*?)"')
_html_img_alt_pattern = re.compile('alt="(.*?)"')
_html_img_hashtag_pattern = re.compile("#\\w+")


@markdown_postprocessor
def link_html_images(text):
    def repl(match):
        src = _html_img_src_pattern.search(match.group()).group(1)
        alt = _html_img_alt_pattern.search(match.group()).group(1)
        classes = []
        for hashtag in _html_img_hashtag_pattern.findall(alt):
            alt = alt.replace(hashtag, "")
            classes.append(hashtag.strip("#"))
        if not src.endswith(".png") and "noshadow" not in classes:
            classes.append("shadow")
        return (
            f'<a href="{src}">'
            f'<img class="{" ".join(classes)}" src="{src}" alt="{alt}" />'
            "</a>"
        )

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
            out += "</div>\n"
        out += '<div class="no-break-section">\n'
        last_pos = pos
        last_lvl = lvl
    out += text[last_pos:]
    if last_lvl:
        out += "</div>\n"
    return out


class Markdown(markdown2.Markdown):
    def __init__(self, *args, **kwargs):
        if "extras" not in kwargs:
            kwargs["extras"] = ["toc", "smarty-pants"]
        markdown2.Markdown.__init__(self, *args, **kwargs)
        self.ctx = None

    def header_id_from_text(self, text, prefix, n):
        if "/" in text:
            text, _ = text.split("/", 1)
        if "<" in text:
            text, _ = text.split("<", 1)
        return markdown2.Markdown.header_id_from_text(self, text, prefix, n)

    def _h_sub(self, match):
        html = markdown2.Markdown._h_sub(self, match)
        # Hide reference aliases
        start = html.find(">")
        end = html.find("<", start)
        slash = html.find("/", start, end)
        if slash >= 0:
            html = html[:slash] + html[end:]
        return html


markdowner = Markdown()


def markdown_to_html(text: str, ctx: Dict, skip_toc: bool = False) -> str:
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
        ctx["store"]["toc"] = _calculate_toc_html(toc, ol_levels={1, 2})
    return html


simple_markdowner = Markdown(extras=["smarty-pants"])


def simple_markdown_to_html(text: str) -> str:
    if not text.strip():
        return text
    html = simple_markdowner.convert(text)
    html = html.strip()
    if html.startswith("<p>"):
        html = html[len("<p>") :]
    if html.endswith("</p>"):
        html = html[: -len("</p>")]
    return html


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


def _calculate_toc_html(toc, ol_levels=None):
    if toc is None:
        return None

    lines = []
    start_level = min(level for level, _, _ in toc) - 1
    prev_level = start_level
    li_stack = []

    def elem(level):
        return "ol" if ol_levels and level in ol_levels else "ul"

    def close(from_level, to_level):
        # Close previous LI element
        if li_stack:
            lines.append("</li>")
            li_stack.pop()
        # Close UL elements to reach our level, if necessary
        for lvl in range(from_level, to_level, -1):
            lines.append(f"</{elem(lvl)}>")
            # Close LI element if there was one opened a this level
            if li_stack and lvl - 1 == li_stack[-1]:
                lines.append("</li>")
                li_stack.pop()

    for level, anchor, name in toc:
        if level > prev_level:
            # Open new UL elements to reach our level, if necessary
            for lvl in range(prev_level + 1, level + 1, 1):
                lines.append(f"<{elem(lvl)}>")
        else:
            close(prev_level, level)
        # Handle tags and metadata in headers
        if "<" in name:
            i = name.find("<")
            tag = name[i:]
            name = name[:i]
        else:
            tag = ""
        if "/" in name:
            name, _ = name.split("/", 1)
        # Open new LI element with link at this level
        lines.append(f'<li>\n<a href="#{anchor}">{name.strip()}</a>{tag}')
        li_stack.append(level)
        prev_level = level

    close(prev_level, start_level)

    return "\n" + "\n".join(lines)
