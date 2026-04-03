import hashlib
import random
import re
import time
import unicodedata as ud
from loguru import logger
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit, urlunsplit

import pandas as pd
from camoufox.sync_api import Camoufox
from patchright.sync_api import sync_playwright, Page, ElementHandle
from selectolax.lexbor import LexborHTMLParser, LexborNode


class QuickPage:
    def __init__(self, page: Page) -> None:
        self._page = page

    def first(self, elems: list[ElementHandle]) -> ElementHandle | None:
        return elems[0] if elems else None

    def re_filter(self, pattern: str, elems: list[ElementHandle]) -> list[ElementHandle]:
        texts = self._page.evaluate("""
        els => els.map(el => {
            if (!el || !el.isConnected) return null;
            const t = el.textContent;
            return t ? t.normalize('NFKC').trim() : null;
        })
        """, elems)
        prog = re.compile(pattern)
        return [
            e for e, t in zip(elems, texts)
            if t and prog.search(t)
        ]

    def ss(self, selector: str) -> list[ElementHandle]:
        return self._page.query_selector_all(selector)

    def s(self, selector: str) -> ElementHandle | None:
        return self.first(self.ss(selector))

    def ss_re(self, selector: str, pattern: str) -> list[ElementHandle]:
        return self.re_filter(pattern, self.ss(selector))

    def s_re(self, selector: str, pattern: str) -> ElementHandle | None:
        return self.first(self.ss_re(selector, pattern))

    def ss_in(self, selector: str, from_: ElementHandle | None) -> list[ElementHandle]:
        return [] if from_ is None else from_.query_selector_all(selector)

    def s_in(self, selector: str, from_: ElementHandle | None) -> ElementHandle | None:
        return self.first(self.ss_in(selector, from_))

    def ss_re_in(self, selector: str, pattern: str, from_: ElementHandle | None) -> list[ElementHandle]:
        return self.re_filter(pattern, self.ss_in(selector, from_))

    def s_re_in(self, selector: str, pattern: str, from_: ElementHandle | None) -> ElementHandle | None:
        return self.first(self.ss_re_in(selector, pattern, from_))

    def next(self, elem: ElementHandle | None) -> ElementHandle | None:
        return None if elem is None else elem.evaluate_handle('el => el.nextElementSibling').as_element()

    def text(self, elem: ElementHandle | None) -> str | None:
        if elem is None:
            return None
        return t.strip() if (t := elem.evaluate('el => el.textContent')) else t

    def inner_text(self, elem: ElementHandle | None) -> str | None:
        if elem is None:
            return None
        return t.strip() if (t := elem.evaluate('el => el.innerText')) else t

    def attr(self, attr_name: str, elem: ElementHandle | None) -> str | None:
        if elem is None:
            return None
        return a.strip() if (a := elem.get_attribute(attr_name)) else a

    def url(self, elem: ElementHandle | None) -> str | None:
        if not (href := self.attr('href', elem)):
            return None
        if re.search(r'(?i)^(?:#|javascript:|mailto:|tel:|data:)', href):
            return None
        url = urljoin(self._page.url, href)
        parts = urlsplit(url)
        if not parts.netloc:
            return None
        parts = parts._replace(path=re.sub(r'/{2,}', '/', parts.path))
        url = urlunsplit(parts)
        return url

    def urls(self, elems: list[ElementHandle]) -> list[str]:
        return [u for e in elems if (u := self.url(e))]

    def _has_body_content(self) -> bool:
        try:
            parser = LexborHTMLParser(self._page.content())
            body = parser.css_first('body')
            return body is not None and bool(body.text(strip=True))
        except Exception:
            return False

    def goto(
        self,
        url: str | None,
        try_cnt: int = 3,
        wait_range: tuple[float, float] = (3, 5),
    ) -> bool:
        if not url or try_cnt < 1:
            return False
        for i in range(try_cnt):
            try:
                if (res := self._page.goto(url)) is not None:
                    if self._has_body_content():
                        return True
                    if 400 <= res.status < 500:
                        logger.error(f"[goto] {url} | HTTP {res.status}")
                        return False
                    reason = f"status: {res.status} (empty body)"
                else:
                    reason = "response is None"
            except Exception as e:
                reason = f"{type(e).__name__}: {e}"
            logger.warning(f"[goto] {url} ({i+1}/{try_cnt}) {reason}")
            if i + 1 < try_cnt:
                time.sleep(random.uniform(*wait_range))
        logger.error(f"[goto] giving up: {url}")
        return False

    def wait(self, selector: str, timeout: int = 15000) -> ElementHandle | None:
        try:
            return self._page.wait_for_selector(selector, timeout=timeout)
        except Exception as e:
            logger.warning(f"[wait] selector={selector!r} not found | url={self._page.url}")
            return None

def parse_html(path: Path | str) -> LexborHTMLParser | None:
    try:
        return LexborHTMLParser(Path(path).read_text(encoding='utf-8'))
    except Exception as e:
        logger.error(f"[parse_html] {path} {type(e).__name__}: {e}")
        return None

class QuickParser:
    def __init__(self, parser: LexborHTMLParser) -> None:
        self._parser = parser

    def first(self, nodes: list[LexborNode]) -> LexborNode | None:
        return nodes[0] if nodes else None

    def re_filter(self, pattern: str, nodes: list[LexborNode]) -> list[LexborNode]:
        prog = re.compile(pattern)
        return [n for n in nodes if (t := self.txt(n)) is not None and prog.search(ud.normalize('NFKC', t))]

    def ss(self, selector: str) -> list[LexborNode]:
        return self._parser.css(selector)

    def s(self, selector: str) -> LexborNode | None:
        return self.first(self.ss(selector))

    def ss_re(self, selector: str, pattern: str) -> list[LexborNode]:
        return self.re_filter(pattern, self.ss(selector))

    def s_re(self, selector: str, pattern: str) -> LexborNode | None:
        return self.first(self.ss_re(selector, pattern))

    def ss_in(self, selector: str, from_: LexborNode | None) -> list[LexborNode]:
        return [] if from_ is None else from_.css(selector)

    def s_in(self, selector: str, from_: LexborNode | None) -> LexborNode | None:
        return self.first(self.ss_in(selector, from_))

    def ss_re_in(self, selector: str, pattern: str, from_: LexborNode | None) -> list[LexborNode]:
        return self.re_filter(pattern, self.ss_in(selector, from_))

    def s_re_in(self, selector: str, pattern: str, from_: LexborNode | None) -> LexborNode | None:
        return self.first(self.ss_re_in(selector, pattern, from_))

    def nxt(self, selector: str, node: LexborNode | None) -> LexborNode | None:
        if node is None:
            return None
        cur: LexborNode | None = node.next
        while cur is not None:
            if cur.is_element_node and cur.css_matches(selector):
                return cur
            cur = cur.next
        return None

    def txt(self, node: LexborNode | None) -> str | None:
        if node is None:
            return None
        return node.text(strip=True)

    def attr(self, attr_name: str, node: LexborNode | None) -> str | None:
        if node is None:
            return None
        return a.strip() if (a := node.attributes.get(attr_name)) else a

class _NSelectBase:
    _re_cache: dict[str, re.Pattern[str]] = {}

    def get_prog(self, pattern: str) -> re.Pattern[str]:
        if pattern not in _NSelectBase._re_cache:
            _NSelectBase._re_cache[pattern] = re.compile(pattern)
        return _NSelectBase._re_cache[pattern]

    def first(self, nodes: list[LexborNode]) -> LexborNode | None:
        return nodes[0] if nodes else None

    def re_filter(self, pattern: str, nodes: list[LexborNode]) -> list[LexborNode]:
        prog = self.get_prog(pattern)
        return [n for n in nodes if (t := n.text(strip=True)) and prog.search(ud.normalize('NFKC', t))]

def nparser(parser: LexborHTMLParser) -> NParser:
    return NParser(parser)

class NParser(_NSelectBase):
    def __init__(self, parser: LexborHTMLParser) -> None:
        self._parser = parser
    
    def us(self, selector: str, pattern: str | None = None) -> list[NNode]:
        if pattern is None:
            return self.ss(selector)
        return self.ss_re(selector, pattern)
    
    def u(self, selector: str, pattern: str | None = None) -> NNode:
        if pattern is None:
            return self.s(selector)
        return self.s_re(selector, pattern)

    def ss(self, selector: str) -> list[NNode]:
        nodes = self._parser.css(selector)
        return [NNode(n) for n in nodes]
    
    def s(self, selector: str) -> NNode:
        node = self._parser.css_first(selector)
        return NNode(node)

    def ss_re(self, selector: str, pattern: str) -> list[NNode]:
        nodes = self.re_filter(pattern, self._parser.css(selector))
        return [NNode(n) for n in nodes]
    
    def s_re(self, selector: str, pattern: str) -> NNode:
        node = self.first(self.re_filter(pattern, self._parser.css(selector)))
        return NNode(node)

def nnode(node: LexborNode | None) -> NNode:
    return NNode(node)

class NNode(_NSelectBase):
    def __init__(self, node: LexborNode | None) -> None:
        self._node = node

    def unwrap(self) -> LexborNode | None:
        return self._node
        
    def us(self, selector: str, pattern: str | None = None) -> list[NNode]:
        if pattern is None:
            return self.ss(selector)
        return self.ss_re(selector, pattern)
    
    def u(self, selector: str, pattern: str | None = None) -> NNode:
        if pattern is None:
            return self.s(selector)
        return self.s_re(selector, pattern)
    
    def ss(self, selector: str) -> list[NNode]:
        nodes = self._node.css(selector) if self._node else []
        return [NNode(n) for n in nodes]
    
    def s(self, selector: str) -> NNode:
        node = self._node.css_first(selector) if self._node else None
        return NNode(node)

    def ss_re(self, selector: str, pattern: str) -> list[NNode]:
        nodes = self.re_filter(pattern, self._node.css(selector)) if self._node else []
        return [NNode(n) for n in nodes]
    
    def s_re(self, selector: str, pattern: str) -> NNode:
        node = self.first(self.re_filter(pattern, self._node.css(selector))) if self._node else None
        return NNode(node)

    def n(self, selector: str) -> NNode:
        if self._node is None:
            return NNode(None)
        cur = self._node.next
        while cur is not None:
            if cur.is_element_node and cur.css_matches(selector):
                return NNode(cur)
            cur = cur.next
        return NNode(None)

    def txt(self) -> str | None:
        if self._node is None:
            return None
        return self._node.text(strip=True)
    
    def attr(self, attr_name: str) -> str | None:
        if self._node is None:
            return None
        return a.strip() if (a := self._node.attributes.get(attr_name)) else a

class FromHere:
    def __init__(self, file: str) -> None:
        self._base = Path(file).resolve().parent

    def __call__(self, path: str) -> Path:
        return self._base / path

def random_sleep(a: float, b: float) -> None:
    time.sleep(random.uniform(a, b))

def append_csv(path: Path | str, row: dict) -> None:
    p = Path(path)
    try:
        pd.DataFrame([row]).to_csv(
            p,
            mode='a',
            index=False,
            header=True if not p.exists() else p.stat().st_size == 0,
            encoding='utf-8-sig',
        )
    except Exception as e:
        logger.error(f"[append_csv] {path} {row} {type(e).__name__}: {e}")

def write_parquet(path: Path | str, rows: list[dict]) -> None:
    try:
        pd.DataFrame(rows).to_parquet(
            Path(path),
            index=False,
        )
    except Exception as e:
        logger.error(f"[write_parquet] {path} {type(e).__name__}: {e}")

def hash_name(key: str) -> str:
    return hashlib.md5(key.encode()).hexdigest()

def save_html(filepath: Path, html: str) -> bool:
    try:
        filepath.write_text(html, encoding="utf-8", errors="replace")
        return True
    except Exception as e:
        logger.error(f"[save_html] {filepath} {type(e).__name__}: {e}")
        return False

def add_log_file(path: Path | str) -> None:
    logger.add(Path(path), level="WARNING", encoding="utf-8")

def browse_patchright(
    fn: Callable[[Page], None],
    user_data_dir: str | Path,
) -> None:
    with sync_playwright() as pw:
        with pw.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            channel='chrome',
            headless=False,
            no_viewport=True,
        ) as context:
            page = context.new_page()
            fn(page)

def browse_camoufox(
    fn: Callable[[Page], None],
    locale: str | list[str] = 'ja-JP,ja',
) -> None:
    with Camoufox(
        headless=False,
        humanize=True,
        locale=locale,
    ) as browser:
        page = browser.new_page()
        fn(page)
