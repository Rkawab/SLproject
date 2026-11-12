# 買い物リスト

Python 3.10を使用します。ローカルではSQLiteが使われます。

Windows PowerShell（`05_ShoppingList` フォルダから）:

```powershell
py -3.10 -m venv slenv
& .\slenv\Scripts\Activate.ps1
cd SLproject
python -m pip install -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

表示されたキーを `.env` の `SECRET_KEY` に設定します。ローカルでは `dbname` と `FORCE_SCRIPT_NAME` を空欄にします。

```powershell
python manage.py migrate
python manage.py load_seed
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

`http://127.0.0.1:8000/` を開いてログインします。もう1人のアカウントは管理画面で作成します。
iPhoneから同じWi-Fiで開く場合は、PCのLAN IPを `.env` の `ALLOWED_HOSTS` にカンマ区切りで追加してサーバーを再起動してください。

開発PCの `slenv` はWindows用です。Raspberry Pi用のLinux仮想環境は、本番構築時に配置先で別途作成し、`requirements.txt` から依存関係をインストールします。

検証:

```text
ruff check .
ruff format --check .
python manage.py test
```

数量の操作:

- 追加画面の品目をタップすると1単位ずつ追加します。肉は基本100g刻みで、数量はチップに表示されます。
- 追加済みの品目を長押しすると全量解除できます。「元に戻す」は3秒間使えます。
- 1タップの単位は「品目の管理」→品目編集の「1タップの数量」で変更できます。数量・メモの直接編集はリスト画面の行メニューから行います。

買い物先・品目・選択操作:

- 買い物先は「業務スーパー」「イトーヨーカドー」「ドラッグストア」「その他」。トイレットペーパー・ウェットティッシュなどの日用品13品も候補に登録しています。既存環境には `migrate` で追加され、現在の買い物リストには自動追加しません。
- 追加画面の「選択を全解除」で、確認後に全店舗・カテゴリーの現在の選択を解除します。通信待ちのタップも順に処理します。品目の登録と購入完了履歴は残ります。
- カテゴリー内の品目は、漢字も読みを使った五十音順に表示します。追加画面・買い物リスト・品目管理で共通です。「よく買う」はお気に入り・使用回数優先です。
- 読みは外部APIを使わず自動入力します。読み違いがある場合は、品目編集の「読み（並び順）」で修正できます。空欄で保存すると自動入力し直します。
- 既存環境を更新する場合は、先に `python -m pip install -r requirements.txt`、次に `python manage.py migrate` を実行してください。本番では続けて `collectstatic --noinput` とサービスのreloadが必要です。

新品目のジャンル自動判定を有効にする場合、当アプリの `.env` に設定してサーバーを再起動します（キーは公開・コミットしません）:

```dotenv
OPENAI_API_KEY=自分のAPIキー
OPENAI_MODEL=gpt-4o-mini
```

APIを呼ぶのは新品目の分類時だけです。既存品目は保存済みのジャンルを使います。キー未設定・通信失敗時も「その他」に登録でき、ジャンルは後から編集できます。
GPT-4o miniは2027年1月14日にAPI提供終了予定のため、期日前に `OPENAI_MODEL` を利用可能な低価格モデルへ変更してください（[公式案内](https://developers.openai.com/api/docs/deprecations)）。高額モデルへの自動切替は行いません。
