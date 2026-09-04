from html.parser import HTMLParser


class VisibleHtmlParser(HTMLParser):
    _suppressed_tags = {"script", "style", "noscript", "template", "svg", "form"}
    _block_tags = {
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "nav",
        "p",
        "section",
        "td",
        "th",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._suppressed_depth = 0
        self._in_title = False
        self._in_head = False
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []
        self.author: str | None = None
        self.canonical_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {name.lower(): value for name, value in attrs if value is not None}
        if tag in self._suppressed_tags:
            self._suppressed_depth += 1
        if tag == "head":
            self._in_head = True
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            name = (values.get("name") or values.get("property") or "").lower()
            if name in {"author", "article:author"} and self.author is None:
                self.author = values.get("content")
        if tag == "link" and "canonical" in (values.get("rel") or "").lower().split():
            self.canonical_url = values.get("href")
        if tag in self._block_tags and self._suppressed_depth == 0 and not self._in_head:
            self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag == "head":
            self._in_head = False
        if tag in self._block_tags and self._suppressed_depth == 0 and not self._in_head:
            self.text_parts.append("\n")
        if tag in self._suppressed_tags and self._suppressed_depth > 0:
            self._suppressed_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
        if self._suppressed_depth == 0 and not self._in_head:
            self.text_parts.append(data)


def visible_html_fields(value: str) -> tuple[str, str | None, str | None]:
    parser = VisibleHtmlParser()
    parser.feed(value)
    parser.close()
    return "".join(parser.text_parts), "".join(parser.title_parts), parser.author


def visible_html_text(value: str) -> str:
    text, _, _ = visible_html_fields(value)
    return text
