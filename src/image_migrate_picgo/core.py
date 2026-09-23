import mimetypes
from collections.abc import Mapping
from contextlib import nullcontext
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote
from urllib.request import urlopen

from markdown_it import MarkdownIt
from markdown_it.rules_inline import backtick as parse_backtick
from markdown_it.rules_inline import image as parse_image

from .uploaders import Uploader


@dataclass(frozen=True)
class MigrationResult:
    source_path: Path
    output_path: Path
    migrated_images: int
    uploaded_images: int
    urls: tuple[str, ...]


@dataclass(frozen=True)
class _Image:
    source: str
    alt: str
    title: str | None
    start: int
    end: int
    attributes: tuple[tuple[str, str | None], ...] | None = None
    self_closing: bool = False


class _HtmlImageParser(HTMLParser):
    def __init__(self, content: str) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[_Image] = []
        self.line_offsets = [0]
        for line in content.splitlines(keepends=True):
            self.line_offsets.append(self.line_offsets[-1] + len(line))

    def _record(
        self,
        tag: str,
        attributes: list[tuple[str, str | None]],
        self_closing: bool,
    ) -> None:
        if tag != "img":
            return
        source = next((value for name, value in attributes if name == "src"), None)
        if not source:
            return
        line, column = self.getpos()
        start = self.line_offsets[line - 1] + column
        self.images.append(
            _Image(
                source=source,
                alt=next(
                    (value or "" for name, value in attributes if name == "alt"),
                    "",
                ),
                title=next(
                    (value for name, value in attributes if name == "title"),
                    None,
                ),
                start=start,
                end=start + len(self.get_starttag_text()),
                attributes=tuple(attributes),
                self_closing=self_closing,
            )
        )

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self._record(tag, attrs, False)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self._record(tag, attrs, True)


def _parse_image_with_span(state, silent: bool) -> bool:
    start = state.pos
    token_count = len(state.tokens)
    matched = parse_image(state, silent)
    if matched and not silent and len(state.tokens) > token_count:
        state.tokens[-1].meta.update(source_start=start, source_end=state.pos)
    return matched


def _parse_backtick_with_span(state, silent: bool) -> bool:
    start = state.pos
    token_count = len(state.tokens)
    matched = parse_backtick(state, silent)
    if matched and not silent and len(state.tokens) > token_count:
        state.tokens[-1].meta.update(source_start=start, source_end=state.pos)
    return matched


_markdown = MarkdownIt("commonmark")
_markdown.inline.ruler.at("image", _parse_image_with_span)
_markdown.inline.ruler.at("backticks", _parse_backtick_with_span)


def _images(content: str) -> list[_Image]:
    line_offsets = [0]
    for line in content.splitlines(keepends=True):
        line_offsets.append(line_offsets[-1] + len(line))

    images: list[_Image] = []
    protected: list[tuple[int, int]] = []
    for token in _markdown.parse(content):
        if token.type in {"fence", "code_block"} and token.map is not None:
            protected.append((line_offsets[token.map[0]], line_offsets[token.map[1]]))
            continue
        if token.type != "inline" or token.children is None or token.map is None:
            continue
        block_start = line_offsets[token.map[0]]
        block_end = line_offsets[token.map[1]]
        inline_start = content.find(token.content, block_start, block_end)
        fallback_cursor = block_start
        for child in token.children:
            if child.type not in {"image", "code_inline"}:
                continue
            relative_start = child.meta["source_start"]
            relative_end = child.meta["source_end"]
            if inline_start < 0:
                markup = token.content[relative_start:relative_end]
                start = content.find(markup, fallback_cursor, block_end)
                if start < 0:
                    raise ValueError("无法确定 Markdown 图片的位置")
                end = start + len(markup)
                fallback_cursor = end
            else:
                start = inline_start + relative_start
                end = inline_start + relative_end
            if child.type == "code_inline":
                protected.append((start, end))
                continue
            images.append(
                _Image(
                    source=child.attrGet("src"),
                    alt=child.content,
                    title=child.attrGet("title"),
                    start=start,
                    end=end,
                )
            )

    html_parser = _HtmlImageParser(content)
    html_parser.feed(content)
    html_parser.close()
    protected.extend((image.start, image.end) for image in images)
    images.extend(
        image
        for image in html_parser.images
        if not any(image.start < end and start < image.end for start, end in protected)
    )
    return sorted(images, key=lambda image: image.start)


def image_sources(content: str) -> list[str]:
    return [image.source for image in _images(content)]


def rewrite_markdown(content: str, replacements: Mapping[str, str]) -> str:
    edits: list[tuple[int, int, str]] = []
    for image in _images(content):
        if image.source not in replacements:
            continue
        title = ""
        if image.title:
            escaped_title = image.title.replace("\\", "\\\\").replace('"', '\\"')
            title = f' "{escaped_title}"'
        if image.attributes is None:
            markup = f"![{image.alt}](<{replacements[image.source]}>{title})"
        else:
            attributes = " ".join(
                name
                if value is None
                else f'{name}="{escape(replacements[image.source] if name == "src" else value, quote=True)}"'
                for name, value in image.attributes
            )
            ending = " />" if image.self_closing else ">"
            markup = f"<img {attributes}{ending}"
        edits.append((image.start, image.end, markup))

    for start, end, markup in reversed(edits):
        content = content[:start] + markup + content[end:]
    return content


def _decode_data_image(
    source: str,
    directory: Path,
    index: int,
) -> Path:
    with urlopen(source) as response:
        content_type = response.headers.get_content_type()
        if not content_type.startswith("image/"):
            raise ValueError("Data URL 的媒体类型需要为 image/*")
        target = (
            directory
            / f"data-{index}{mimetypes.guess_extension(content_type) or '.img'}"
        )
        target.write_bytes(response.read())
    return target


def _upload_source(
    source: str,
    markdown_path: Path,
    directory: Path,
    index: int,
) -> str | Path:
    if source.startswith("data:"):
        return _decode_data_image(source, directory, index)
    if source.startswith(("http://", "https://", "//")):
        return f"https:{source}" if source.startswith("//") else source
    path = Path(unquote(source.split("#", 1)[0].split("?", 1)[0])).expanduser()
    if not path.is_absolute():
        path = markdown_path.parent / path
    return path.resolve(strict=True)


def migrate_markdown(
    markdown_path: str | Path,
    uploader: Uploader,
    *,
    output_path: str | Path | None = None,
) -> MigrationResult:
    source_path = Path(markdown_path).expanduser().resolve(strict=True)
    target_path = (
        Path(output_path).expanduser().resolve()
        if output_path is not None
        else source_path
    )
    content = source_path.read_text(encoding="utf-8")
    all_sources = image_sources(content)
    sources = list(dict.fromkeys(all_sources))

    if sources:
        with (
            TemporaryDirectory(
                prefix=".image-migrate-picgo-", dir=source_path.parent
            )
            if any(source.startswith("data:") for source in sources)
            else nullcontext(source_path.parent)
        ) as directory:
            upload_sources = [
                _upload_source(source, source_path, Path(directory), index)
                for index, source in enumerate(sources)
            ]
            urls = tuple(uploader.upload(upload_sources))
        if len(urls) != len(sources):
            raise RuntimeError("PicGo 返回的 URL 数量与图片数量不一致")
        replacements = dict(zip(sources, urls, strict=True))
        migrated = rewrite_markdown(content, replacements)
    else:
        urls = ()
        migrated = content

    target_path.write_text(migrated, encoding="utf-8")
    return MigrationResult(
        source_path=source_path,
        output_path=target_path,
        migrated_images=len(all_sources),
        uploaded_images=len(sources),
        urls=urls,
    )
