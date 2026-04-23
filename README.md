# Study Group Finder (Flask + MySQL)

## Database Configuration
The app reads DB settings from environment variables first, then from a local config file.

## Run Locally
1. Create and activate a virtualenv.
2. Install dependencies.
3. Set `DB_PASS` and `FLASK_SECRET_KEY` (or use `db_credentials.py`).
4. Start Flask.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
$env:DB_PASS="your_mysql_password"
$env:FLASK_SECRET_KEY="change-this-secret"
python app.py
```

Then open:
- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/setup` (initialize schema/seed)
- `http://127.0.0.1:8000/test-connection`

## Deploy On PythonAnywhere (Flask Website)
1. Upload or clone this project into your home directory.

```bash
cd /home/CHANGWEN919
git clone <your-repo-url> project
cd project
python3.11 -m venv /home/CHANGWEN919/venv-study-group
source /home/CHANGWEN919/venv-study-group/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

2. In PythonAnywhere Web tab:
- Add a new web app.
- Choose Manual configuration.
- Select Python 3.11.
- Set virtualenv path to `/home/CHANGWEN919/venv-study-group`.

3. Edit WSGI file at `/var/www/CHANGWEN919_pythonanywhere_com_wsgi.py`:

```python
import os
import sys

project_home = "/home/CHANGWEN919/project"
if project_home not in sys.path:
	sys.path.insert(0, project_home)

os.environ["DB_PASS"] = "your_mysql_password"
os.environ["FLASK_SECRET_KEY"] = "your-long-random-secret"

from app import app as application
```

4. Reload the web app.
5. Open `/setup` once to create/reset schema and seed data.
6. Verify `/test-connection`, then use `/`.

## Notes
- Free PythonAnywhere accounts can only access PythonAnywhere MySQL from PythonAnywhere-hosted code.
- If you set `DB_NAME` manually, quote values containing `$`.
