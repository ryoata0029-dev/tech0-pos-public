# 担当者IDのHTML形式検査：修正と検証

2026-10-04。Mac通常ChromeのConsoleで、担当者IDのHTML `pattern` がvモードの構文エラーとなる問題を確認。通常ログインは成功しており、API検証を回避した証拠ではない。

対象：[page.tsx](../../frontend/app/page.tsx)の通常ログイン／再認証共通form、担当者ID inputの1属性。未escapeのリテラルハイフンをescapeしたJS文字列式へ変更した。

```tsx
pattern={'[A-Za-z0-9_\\-]{1,32}'}
```

回帰で取得した属性props値は `[A-Za-z0-9_\-]{1,32}`。英大小文字・数字・アンダースコア・ハイフンの1〜32文字という条件、required、API側の検証、通常ログイン／再認証の処理は変更していない。HTML patternはvで解釈され、リテラルのハイフンにはescapeが必要。不正なpatternは形式検査に適用されない。[MDN](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Attributes/pattern)、[HTML Standard](https://html.spec.whatwg.org/multipage/input.html#the-pattern-attribute)

## 自動回帰

[home-pattern.test.mjs](../../frontend/tests/home-pattern.test.mjs)は実Home TSXから未認証のログインformを出し、実staff_id inputのpattern propsを取得してvでコンパイルする。手書きの修正後定数だけを検査する方式ではない。

- 修正前：1件失敗。実属性のvコンパイルで `Invalid character in character class` を再現。
- 修正後：新規1件と既存復帰19件、計20件成功。1／32文字、先頭ゼロ、大小文字、`_`・`-`を受理。空・33文字・空白・全角・不正記号・末尾改行を拒否し、required属性も維持。
- コマンド：`sh tools/frontend.sh exec -- node --test tests/home-pattern.test.mjs tests/register-recovery-remaining.test.mjs`。
- 対象ESLint：`sh tools/frontend.sh exec -- eslint app/page.tsx tests/home-pattern.test.mjs tests/support/recovery-ui-harness.mjs --max-warnings 0`、成功。
- 専用harnessにはinput属性を観測するアクセサだけを追加した。依存導入なし。既存のMODULE_TYPELESS_PACKAGE_JSON警告は残る。

## 適用範囲と未確認

主担当が修正後の全`make check`を実施し、Python78件・Node119件、計197件成功。OpenAPI22操作、lint・型、buildも成功。[実行ログ](evidence/mac-parallel/check-pattern-fix-retry.log)、[buildログ](evidence/mac-parallel/build-pattern-fix.log)、[対象buildとソースの記録](evidence/mac-parallel/runtime-pattern-fix.json)。最初の検査は検証helperの行長で停止し、その文字列分割後の再検査を成功根拠とする。

Macの実Chromeシークレット画面で、今回の専用originの通常HomeログインformをネイティブUIから確認した。担当者ID入力→送信操作後のフォーカスとブラウザの検証bubbleを証拠とする。[各入力の観測](evidence/mac-parallel/pattern-native-cases.json)、[BAD@IDの画面状態](evidence/mac-parallel/pattern-invalid-native.txt)。

| 入力 | 実Chromeでの観測 |
|---|---|
| `BAD@ID`、33文字、全角`Ａ` | 担当者IDへフォーカスし「指定されている形式で入力してください」。形式を拒否。 |
| ASCII英数字・`_`・`-`を含む32文字、ハイフン1文字 | 担当者IDの検査を通り、空のパスワードへフォーカスしてrequiredの「このフィールドを入力してください」。 |

パスワードは入力せず、認証POSTを行わずに検査用シークレットwindowを閉じた。既存の通常windowのCookieは変更していない。[修正後Console](evidence/mac-parallel/pattern-console.txt)は未認証の`/api/auth/status`の401のみで、pattern構文エラーは表示されていない。BAD@IDの個別UTCは記録されておらず、正確な時刻を補わない。他の境界値はJSONに観測時刻を記録した。

シークレットwindowは既存extension APIから参照できなかったため、実DOMの`getAttribute('pattern')`・`checkValidity()`・`validity.patternMismatch`の直接読取は未実施。今回の実Chrome証拠はネイティブの拒否／次項目への移動であり、DOM値やvalidityフラグを取得済みと扱わない。ブラウザのtext入力正規化、末尾改行、空白など全入力条件の実機確認も未網羅。Nodeの末尾改行検査は文字列の完全一致検査であり、実text inputの改行除去と同一の試験ではない。

今回の修正後buildは`5_wgTZOtPLE3as7vfiFAN`。先行するMac TC-01〜03は旧build `_6zNKKv-evmUKeL_8XYLh` の証拠であり、本修正後buildの結果と混同しない。本票の担当者はソース・自動回帰と証跡の読取／文書更新のみを行い、build・server・GUI・DBは主担当が扱った。iPhone・カメラの再検証、要件変更、commit・push・公開は本修正では行っていない。

戻す場合は今回のpattern1属性と専用回帰／アクセサ／本結果票だけを対象とし、既存の復帰やカメラ修正を戻さない。
