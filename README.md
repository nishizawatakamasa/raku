# raku

## Overview - 概要

raku is a scraping utility library built on Patchright and selectolax.
rakuはPatchrightとselectolaxをベースにしたスクレイピングユーティリティライブラリです。

- **QuickPage** — Patchright `Page` のラッパー。スクレイピング用。
- **QuickParser** — selectolax `HTMLParser` のラッパー。ローカル抽出用。
- **browse_patchright()** — Patchright（Chrome）起動ランナー。
- **browse_camoufox()** — Camoufox（Firefox）起動ランナー。bot検知対策向け。
- その他ユーティリティ

## Requirements - 必要条件

- Python 3.12 or higher
- Libraries: playwright, selectolax, pandas, camoufox（自動インストール）
- `write_parquet` を使う場合は pandas の Parquet エンジンとして `pyarrow`（または `fastparquet`）が必要です。
- Browser binaries（別途インストールが必要）

## Installation - インストール

### pip

```
pip install raku
```

### uv (推奨)

```
uv add raku
```

ブラウザバイナリを別途インストールしてください。

### Patchright（Chromium）

#### pip

```
python -m patchright install chromium
```

#### uv (推奨)

```
uv run patchright install chromium
```

### Camoufox（Firefox）

#### pip

```
camoufox fetch
```

#### uv (推奨)

```
uv run camoufox fetch
```

## Quick Reference - 主要メソッド一覧

### QuickPage のメソッド

- **`ss(selector: str) -> list[ElementHandle]`**  
  指定したCSSセレクタにマッチする**すべての要素**をリストで返します。  
  _例:_ `links = p.ss('a')`

- **`s(selector: str) -> ElementHandle | None`**  
  指定したCSSセレクタにマッチする**最初の要素**を返します。見つからなければ `None`。  
  _例:_ `title_elem = p.s('h1')`

- **`text(elem: ElementHandle | None) -> str | None`**  
  要素からテキスト内容を取得します（前後の空白は除去されます）。  
  _例:_ `title = p.text(p.s('h1'))`

- **`attr(attr_name: str, elem: ElementHandle | None) -> str | None`**  
  要素の指定された属性値を取得します。  
  _例:_ `href = p.attr('href', link_elem)`

- **`url(elem: ElementHandle | None) -> str | None`**  
  リンク要素 (`<a>`) の `href` を**絶対URL**に正規化して返します。無効なリンク（`javascript:` など）は除外されます。  
  _例:_ `next_url = p.url(p.s('a.next'))`

- **`goto(url: str | None) -> bool`**  
  指定したURLに移動します。成功すれば `True`、失敗すれば `False` を返します。  
  _例:_ `if p.goto('https://example.com'): ...`

### QuickParser のメソッド

- **`nxt(self, selector: str, node: LexborNode | None) -> LexborNode | None`**  
  ノードから、セレクタに一致する最初の弟ノードを取得します。  

- **`txt(self, node: LexborNode | None) -> str | None`**  
  ノードからテキスト内容を(子孫ノードまで全て含め)取得します（前後の空白は除去されます）。  

### ユーティリティ関数

- **`sleep_between(a: float, b: float) -> None`**  
  `a` 〜 `b` 秒の間でランダムに待機します。サーバーに負荷をかけないための基本的なマナーです。  
  _例:_ `sleep_between(1, 2)`

- **`append_csv(path: Path | str, row: dict) -> None`**  
  `dict` 形式のデータを1行としてCSVファイルに追記します。ファイルが存在しない場合はヘッダーも自動で書き込みます。  
  _例:_ `append_csv('data.csv', {'name': '太郎', 'age': 20})`

- **`write_parquet(path: Path | str, rows: list[dict]) -> None`**  
  `dict` のリストを1つの Parquet ファイルに書き出します。  
  _例:_ `write_parquet('data.parquet', [{'name': '太郎', 'age': 20}])`

- **`browse_patchright(fn: Callable[[Page], None], ...) -> None`**  
  Patchrightのブラウザを起動し、引数で渡した関数を実行します。
  _例:_ `browse_patchright(scrape, user_data_dir='C:\Users\あなたのユーザ名\AppData\Local\Google\Chrome\User Data')`  
  _引数:_

  ```py
  def browse_patchright(
      # scrape(page) のような関数を渡す。
      fn: Callable[[Page], None],
      # 'C:\Users\あなたのユーザ名\AppData\Local\Google\Chrome\User Data'のような文字列。
      # chrome://version/で確認できる。
      user_data_dir: str | Path,
  ) -> None:
  ```

- **`browse_camoufox(fn: Callable[[Page], None], ...) -> None`**  
  Camoufox（Firefox）でブラウザを起動し、引数で渡した関数を実行します。bot検知が厳しいサイト向け。  
  _例:_ `browse_camoufox(scrape)`  
   _引数:_
  ```py
  def browse_camoufox(
      # scrape(page) のような関数を渡す。
      fn: Callable[[Page], None],
      # ブラウザのロケール（言語・地域設定）を指定
      # 英語サイト中心なら `'en-US,en'` への変更を検討
      locale: str | list[str] | None = 'ja-JP,ja',
  ) -> None:
  ```

## Basic Usage - 基本的な使い方

```python
from raku import *

fh = FromHere(__file__)
add_log_file(fh('log/scraping.log'))

def scrape(page):
    p = QuickPage(page)
    p.goto('https://www.foobarbaz1.jp')

    pref_urls = [p.url(e) for e in p.ss('li.item > ul > li > a')]

    classroom_urls = []
    for i, url in enumerate(pref_urls, 1):
        print(f'{i}/{len(pref_urls)} pref_urls')
        if not p.goto(url):
            continue
        sleep_between(1, 2)
        links = [p.url(e) for e in p.ss('.school-area h4 a')]
        classroom_urls.extend(links)

    for i, url in enumerate(classroom_urls, 1):
        print(f'{i}/{len(classroom_urls)} classroom_urls')
        if not p.goto(url):
            continue
        sleep_between(1, 2)
        append_csv(fh('csv/out.csv'), {
            'URL': page.url,
            '教室名': p.text(p.s('h1 .text01')),
            '住所': p.text(p.s('.item .mapText')),
            '電話番号': p.text(p.s('.item .phoneNumber')),
            'HP': p.url(p.s_in('a', p.next(p.s_re('th', 'ホームページ')))),
        })


if __name__ == '__main__':
    browse_patchright(
        scrape,
        user_data_dir=r'C:\Users\あなたのユーザ名\AppData\Local\Google\Chrome\User Data',
    )
```

## Save HTML while scraping - スクレイピングしながらHTMLを保存する

```python
from raku import *

fh = FromHere(__file__)
add_log_file(fh('log/scraping.log'))

def scrape(page):
    ctx = {}
    p = QuickPage(page)
    p.goto('https://www.foobarbaz1.jp')

    ctx['アイテムURLs'] = [p.url(e) for e in p.ss('ul.items > li > a')]

    for i, url in enumerate(ctx['アイテムURLs'], 1):
        print(f'{i}/{len(ctx['アイテムURLs'])} アイテムURLs')
        if not p.goto(url):
            continue
        sleep_between(1, 2)
        if not p.wait('#logo', timeout=10000):
            continue
        file_name = f'{hash_name(url)}.html'
        if not save_html(fh('html') / file_name, page.content()):
            continue
        append_csv(fh('outurlhtml.csv'), {
            'URL': url,
            'HTML': file_name,
        })

if __name__ == '__main__':
    browse_patchright(
      scrape, 
      user_data_dir=r'C:\Users\あなたのユーザ名\AppData\Local\Google\Chrome\User Data',
    )
```

## Scrape from local HTML files - 保存済みHTMLからスクレイピングしてParquetに出力する

```python
import pandas as pd

from raku import *

fh = FromHere(__file__)
add_log_file(fh('log/scraping.log'))

df = pd.read_csv(fh('outurlhtml.csv'))
results = []
for i, (url, path) in enumerate(zip(df['URL'], df['HTML']), 1):
    print(i)
    if not (parser := parse_html(fh('html') / path)):
        continue
    p = QuickParser(parser)
    results.append({
        'URL': url,
        '教室名': p.txt(p.s('h1 .text02')),
        '住所': p.txt(p.s('.item .mapText')),
        '所在地': p.txt(p.nxt('dd', p.s_re('dt', r'所在地'))),
    })
write_parquet(fh('outhtml.parquet'), results)
```

## License - ライセンス

[MIT](./LICENSE)
