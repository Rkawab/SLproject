# 買い物リスト

Python 3.10を使用します。ローカルではSQLiteが使われます。

Windows PowerShell（`05_ShoppingList` フォルダから）:

```powershell
py -3.10 -m venv slenv
& .\slenv\Scripts\Activate.ps1
cd SLproject
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
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

Linux / WSLでは最初に `python3.10 -m venv slenv` と `source slenv/bin/activate` を実行し、同じ `SLproject` で上記のPythonコマンドを実行します（`.env` のコピーは `cp .env.example .env`）。Windows用とLinux用のvenvは共用できません。

検証:

```text
ruff check .
ruff format --check .
python manage.py test
```
