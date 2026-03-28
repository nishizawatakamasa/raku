import hashlib
import random
import re
import time
import unicodedata as ud
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit, urlunsplit

import pandas as pd
from camoufox.sync_api import Camoufox
from loguru import logger
from patchright.sync_api import sync_playwright, Page, ElementHandle
from selectolax.lexbor import LexborHTMLParser, LexborNode


# ---------------------------------------------------------------------------
# NullNode — None の代わりに返すセンチネル
# ---------------------------------------------------------------------------

class NullNode:
    """
    要素が見つからなかった場合に None の代わりに返すセンチネルオブジェクト。

    - チェーン中に何を呼んでも自分自身を返すので AttributeError にならない
    - bool() が False になるので `if node:` の判定はそのまま使える
    - for ループも安全（空のイテラブル）
    - 生成時に reason を渡すとログに記録される
    """

    def __init__(self, reason: str = '') -> None:
        if reason:
            logger.warning(f"[NullNode] {reason}")

    def __call__(self, *args, **kwargs) -> 'NullNode':
        return self

    def __getattr__(self, name: str) -> 'NullNode':
        return self

    def __bool__(self) -> bool:
        return False

    def __iter__(self):
        return iter([])

    def __repr__(self) -> str:
        return 'NullNode()'


NULL = NullNode.__new__(NullNode)  # ログを出さないデフォルト NullNode


def _null(reason: str) -> NullNode:
    """ログ付き NullNode を返す"""
    return NullNode(reason)


# ---------------------------------------------------------------------------
# LexborNode へのモンキーパッチ
# ---------------------------------------------------------------------------

def _node_s(self: LexborNode, selector: str) -> LexborNode | NullNode:
    """`css_first` のショートハンド"""
    result = self.css_first(selector)
    return result if result is not None else _null(f"s({selector!r}) not found")


def _node_ss(self: LexborNode, selector: str) -> list[LexborNode]:
    """`css` のショートハンド"""
    return self.css(selector)


def _node_s_re(self: LexborNode, selector: str, pattern: str) -> LexborNode | NullNode:
    """セレクタ + 正規表現で最初にマッチするノードを返す"""
    prog = re.compile(pattern)
    for node in self.css(selector):
        t = node.text(strip=True)
        if t and prog.search(ud.normalize('NFKC', t)):
            return node
    return _null(f"s_re({selector!r}, {pattern!r}) not found")


def _node_ss_re(self: LexborNode, selector: str, pattern: str) -> list[LexborNode]:
    """セレクタ + 正規表現でマッチするノードをリストで返す"""
    prog = re.compile(pattern)
    return [
        node for node in self.css(selector)
        if (t := node.text(strip=True)) and prog.search(ud.normalize('NFKC', t))
    ]


def _node_nxt(self: LexborNode, selector: str) -> LexborNode | NullNode:
    """セレクタにマッチする最初の次兄弟要素ノードを返す"""
    cur: LexborNode | None = self.next
    while cur is not None:
        if cur.is_element_node and cur.css_matches(selector):
            return cur
        cur = cur.next
    return _null(f"nxt({selector!r}) not found")


def _node_txt(self: LexborNode) -> str | None:
    """`text(strip=True)` のショートハンド。空文字は None を返す"""
    return t if (t := self.text(strip=True)) else None


def _node_attr(self: LexborNode, attr_name: str) -> str | None:
    """`attributes.get()` のショートハンド。空文字は None を返す"""
    return a.strip() if (a := self.attributes.get(attr_name)) else None


LexborNode.s     = _node_s
LexborNode.ss    = _node_ss
LexborNode.s_re  = _node_s_re
LexborNode.ss_re = _node_ss_re
LexborNode.nxt   = _node_nxt
LexborNode.txt   = _node_txt
LexborNode.attr  = _node_attr


# ---------------------------------------------------------------------------
# LexborHTMLParser へのモンキーパッチ
# ---------------------------------------------------------------------------

def _parser_s(self: LexborHTMLParser, selector: str) -> LexborNode | NullNode:
    """`css_first` のショートハンド"""
    result = self.css_first(selector)
    return result if result is not None else _null(f"s({selector!r}) not found")


def _parser_ss(self: LexborHTMLParser, selector: str) -> list[LexborNode]:
    """`css` のショートハンド"""
    return self.css(selector)


def _parser_s_re(self: LexborHTMLParser, selector: str, pattern: str) -> LexborNode | NullNode:
    """セレクタ + 正規表現で最初にマッチするノードを返す"""
    prog = re.compile(pattern)
    for node in self.css(selector):
        t = node.text(strip=True)
        if t and prog.search(ud.normalize('NFKC', t)):
            return node
    return _null(f"s_re({selector!r}, {pattern!r}) not found")


def _parser_ss_re(self: LexborHTMLParser, selector: str, pattern: str) -> list[LexborNode]:
    """セレクタ + 正規表現でマッチするノードをリストで返す"""
    prog = re.compile(pattern)
    return [
        node for node in self.css(selector)
        if (t := node.text(strip=True)) and prog.search(ud.normalize('NFKC', t))
    ]


LexborHTMLParser.s     = _parser_s
LexborHTMLParser.ss    = _parser_ss
LexborHTMLParser.s_re  = _parser_s_re
LexborHTMLParser.ss_re = _parser_ss_re


# ---------------------------------------------------------------------------
# Page へのモンキーパッチ
# ---------------------------------------------------------------------------

def _page_ss(self: Page, selector: str) -> list[ElementHandle]:
    """`query_selector_all` のショートハンド"""
    return self.query_selector_all(selector)


def _page_s(self: Page, selector: str) -> ElementHandle | None:
    """`query_selector` のショートハンド"""
    return self.query_selector(selector)


def _page_ss_re(self: Page, selector: str, pattern: str) -> list[ElementHandle]:
    """セレクタ + 正規表現でマッチする要素をリストで返す"""
    elems = self.query_selector_all(selector)
    texts = self.evaluate("""
        els => els.map(el => {
            if (!el || !el.isConnected) return null;
            const t = el.textContent;
            return t ? t.normalize('NFKC').trim() : null;
        })
    """, elems)
    prog = re.compile(pattern)
    return [e for e, t in zip(elems, texts) if t and prog.search(t)]


def _page_s_re(self: Page, selector: str, pattern: str) -> ElementHandle | None:
    """セレクタ + 正規表現で最初にマッチする要素を返す"""
    results = _page_ss_re(self, selector, pattern)
    return results[0] if results else None


def _page_visit(self: Page, url: str | None, try_cnt: int = 3) -> bool:
    """リトライ付き goto。成功で True、失敗で False を返す"""
    if not url or try_cnt < 1:
        return False
    for i in range(try_cnt):
        try:
            if (res := self.goto(url)) is not None:
                if res.ok:
                    return True
                if 400 <= res.status < 500:
                    logger.error(f"[visit] {url} | HTTP {res.status}")
                    return False
                reason = f"status: {res.status}"
            else:
                reason = "response is None"
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
        logger.warning(f"[visit] {url} ({i+1}/{try_cnt}) {reason}")
        if i + 1 < try_cnt:
            time.sleep(random.uniform(3, 5))
    logger.error(f"[visit] giving up: {url}")
    return False


def _page_wait(self: Page, selector: str, timeout: int = 15000) -> ElementHandle | None:
    """セレクタが現れるまで待機。タイムアウト時は None を返してログを出す"""
    try:
        return self.wait_for_selector(selector, timeout=timeout)
    except Exception:
        logger.warning(f"[wait] selector={selector!r} not found | url={self.url}")
        return None


Page.ss    = _page_ss
Page.s     = _page_s
Page.ss_re = _page_ss_re
Page.s_re  = _page_s_re
Page.visit = _page_visit
Page.wait  = _page_wait


# ---------------------------------------------------------------------------
# ElementHandle へのモンキーパッチ
# ---------------------------------------------------------------------------

def _elem_ss(self: ElementHandle, selector: str) -> list[ElementHandle]:
    """`query_selector_all` のショートハンド"""
    return self.query_selector_all(selector)


def _elem_s(self: ElementHandle, selector: str) -> ElementHandle | None:
    """`query_selector` のショートハンド"""
    return self.query_selector(selector)


def _elem_ss_re(self: ElementHandle, selector: str, pattern: str) -> list[ElementHandle]:
    """セレクタ + 正規表現でマッチする子要素をリストで返す"""
    elems = self.query_selector_all(selector)
    # ElementHandle.evaluate は self を第一引数として受け取る形式で動かない
    # ので1件ずつ取得する
    prog = re.compile(pattern)
    result = []
    for el in elems:
        t = el.evaluate('el => el.textContent')
        if t:
            t = ud.normalize('NFKC', t).strip()
            if prog.search(t):
                result.append(el)
    return result


def _elem_s_re(self: ElementHandle, selector: str, pattern: str) -> ElementHandle | None:
    """セレクタ + 正規表現で最初にマッチする子要素を返す"""
    results = _elem_ss_re(self, selector, pattern)
    return results[0] if results else None


def _elem_next_elem(self: ElementHandle) -> ElementHandle | None:
    """`nextElementSibling` を返す"""
    return self.evaluate_handle('el => el.nextElementSibling').as_element()


def _elem_text(self: ElementHandle) -> str | None:
    """`textContent` のショートハンド。空文字は None を返す"""
    t = self.evaluate('el => el.textContent')
    return t.strip() if t else None


def _elem_attr(self: ElementHandle, attr_name: str) -> str | None:
    """`get_attribute` のショートハンド。空文字は None を返す"""
    a = self.get_attribute(attr_name)
    return a.strip() if a else None


def _elem_url(self: ElementHandle, base_url: str) -> str | None:
    """href を絶対URLに正規化して返す。無効なリンクは None を返す"""
    href = self.get_attribute('href')
    if not href or re.search(r'(?i)^(?:#|javascript:|mailto:|tel:|data:)', href):
        return None
    url = urljoin(base_url, href)
    parts = urlsplit(url)
    if not parts.netloc:
        return None
    parts = parts._replace(path=re.sub(r'/{2,}', '/', parts.path))
    return urlunsplit(parts)


ElementHandle.ss        = _elem_ss
ElementHandle.s         = _elem_s
ElementHandle.ss_re     = _elem_ss_re
ElementHandle.s_re      = _elem_s_re
ElementHandle.next_elem = _elem_next_elem
ElementHandle.text      = _elem_text
ElementHandle.attr      = _elem_attr
ElementHandle.url       = _elem_url


# ---------------------------------------------------------------------------
# load_html — HTML ファイルをパースして LexborHTMLParser を返すユーティリティ
# ---------------------------------------------------------------------------

def load_html(path: Path | str) -> LexborHTMLParser | None:
    """
    HTML ファイルを読み込んで LexborHTMLParser を返す。
    失敗時は None を返してログを出す。
    """
    try:
        return LexborHTMLParser(Path(path).read_text(encoding='utf-8'))
    except Exception as e:
        logger.error(f"[load_html] {path} {type(e).__name__}: {e}")
        return None


# ---------------------------------------------------------------------------
# ユーティリティ関数（変更なし）
# ---------------------------------------------------------------------------

class FromHere:
    def __init__(self, file: str) -> None:
        self._base = Path(file).resolve().parent

    def __call__(self, path: str) -> Path:
        return self._base / path


def sleep_between(a: float, b: float) -> None:
    time.sleep(random.uniform(a, b))


def append_csv(path: Path | str, row: dict) -> None:
    p = Path(path)
    pd.DataFrame([row]).to_csv(
        p,
        mode='a',
        index=False,
        header=not p.exists(),
        encoding='utf-8-sig',
    )


def write_parquet(path: Path | str, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_parquet(
        Path(path),
        index=False,
    )


def hash_name(key: str) -> str:
    return hashlib.md5(key.encode()).hexdigest()


def save_html(filepath: Path, html: str) -> bool:
    try:
        filepath.write_text(html, encoding='utf-8', errors='replace')
        return True
    except Exception as e:
        logger.error(f"[save_html] {filepath} {type(e).__name__}: {e}")
        return False


def add_log_file(path: Path | str) -> None:
    logger.add(Path(path), level='WARNING', encoding='utf-8')


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