"""BOT.CTL backend API tests - auth, bot lifecycle, logs, system stats."""
import os
import io
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:8001"
# Use frontend env for external testing
try:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
except Exception:
    pass

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "9800102496Uu"

SAMPLE_BOT_PY = b"""import time, sys
print('hello', flush=True)
i = 0
while True:
    print(f'beat {i}', flush=True)
    i += 1
    time.sleep(2)
"""


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
                      timeout=15)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    data = r.json()
    assert "access_token" in data and data["username"] == ADMIN_USERNAME
    return data["access_token"]


@pytest.fixture(scope="session")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---------- AUTH ----------

class TestAuth:
    def test_login_invalid(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"username": "admin", "password": "wrongpass"},
                          timeout=10)
        assert r.status_code == 401

    def test_login_valid_sets_cookie(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
                          timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["username"] == "admin"
        assert isinstance(body["access_token"], str) and len(body["access_token"]) > 20
        # httpOnly cookie should be present
        assert "access_token" in r.cookies

    def test_me_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/auth/me", timeout=10)
        assert r.status_code == 401

    def test_me_with_token(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        assert r.json().get("username") == "admin"

    def test_bots_unauthorized(self):
        r = requests.get(f"{BASE_URL}/api/bots", timeout=10)
        assert r.status_code == 401


# ---------- SYSTEM ----------

class TestSystem:
    def test_system_stats(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/system/stats", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        for k in ("total_bots", "running_bots", "system_cpu_percent", "system_ram_percent"):
            assert k in d


# ---------- BOT LIFECYCLE ----------

@pytest.fixture(scope="class")
def created_bot(auth_headers):
    files = {"file": ("TEST_heartbeat.py", io.BytesIO(SAMPLE_BOT_PY), "text/x-python")}
    data = {"name": "TEST_bot_heartbeat", "description": "test bot", "auto_restart": "false"}
    r = requests.post(f"{BASE_URL}/api/bots", headers=auth_headers,
                      files=files, data=data, timeout=20)
    assert r.status_code == 200, r.text
    bot = r.json()
    assert bot["name"] == "TEST_bot_heartbeat"
    assert bot["entry_file"] == "TEST_heartbeat.py"
    assert "id" in bot
    yield bot
    # Teardown
    requests.delete(f"{BASE_URL}/api/bots/{bot['id']}", headers=auth_headers, timeout=15)


class TestBotLifecycle:
    def test_list_includes_created(self, auth_headers, created_bot):
        r = requests.get(f"{BASE_URL}/api/bots", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        ids = [b["id"] for b in r.json()]
        assert created_bot["id"] in ids

    def test_get_bot(self, auth_headers, created_bot):
        r = requests.get(f"{BASE_URL}/api/bots/{created_bot['id']}", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["bot"]["id"] == created_bot["id"]
        assert "stats" in d

    def test_start_stop_cycle(self, auth_headers, created_bot):
        bid = created_bot["id"]
        # Start
        r = requests.post(f"{BASE_URL}/api/bots/{bid}/start", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        time.sleep(3)
        # Stats running
        r = requests.get(f"{BASE_URL}/api/bots/{bid}/stats", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        st = r.json()
        assert st["status"] == "running"
        assert st["pid"] is not None
        # Logs
        r = requests.get(f"{BASE_URL}/api/bots/{bid}/logs?lines=50", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        assert "beat" in r.json()["logs"] or "hello" in r.json()["logs"]
        # Stop
        r = requests.post(f"{BASE_URL}/api/bots/{bid}/stop", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        time.sleep(1)
        r = requests.get(f"{BASE_URL}/api/bots/{bid}/stats", headers=auth_headers, timeout=10)
        assert r.json()["status"] == "stopped"

    def test_restart(self, auth_headers, created_bot):
        bid = created_bot["id"]
        r = requests.post(f"{BASE_URL}/api/bots/{bid}/restart", headers=auth_headers, timeout=20)
        assert r.status_code == 200
        time.sleep(2)
        r = requests.get(f"{BASE_URL}/api/bots/{bid}/stats", headers=auth_headers, timeout=10)
        assert r.json()["status"] == "running"
        # cleanup stop
        requests.post(f"{BASE_URL}/api/bots/{bid}/stop", headers=auth_headers, timeout=10)

    def test_update_bot_cron(self, auth_headers, created_bot):
        bid = created_bot["id"]
        r = requests.put(f"{BASE_URL}/api/bots/{bid}", headers=auth_headers,
                         json={"description": "updated desc",
                               "start_cron": "0 9 * * *",
                               "stop_cron": "0 18 * * *",
                               "auto_restart": True}, timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["description"] == "updated desc"
        assert d["start_cron"] == "0 9 * * *"
        assert d["auto_restart"] is True
        # Verify via GET
        r = requests.get(f"{BASE_URL}/api/bots/{bid}", headers=auth_headers, timeout=10)
        assert r.json()["bot"]["description"] == "updated desc"

    def test_clear_logs(self, auth_headers, created_bot):
        bid = created_bot["id"]
        r = requests.post(f"{BASE_URL}/api/bots/{bid}/logs/clear",
                          headers=auth_headers, timeout=10)
        assert r.status_code == 200


class TestValidation:
    def test_create_bot_rejects_non_py(self, auth_headers):
        files = {"file": ("bad.txt", io.BytesIO(b"hi"), "text/plain")}
        data = {"name": "TEST_bad", "description": "", "auto_restart": "false"}
        r = requests.post(f"{BASE_URL}/api/bots", headers=auth_headers,
                          files=files, data=data, timeout=10)
        assert r.status_code == 400

    def test_nonexistent_bot_404(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bots/nonexistent-id",
                         headers=auth_headers, timeout=10)
        assert r.status_code == 404


class TestDelete:
    def test_delete_bot_removes(self, auth_headers):
        # Create
        files = {"file": ("TEST_del.py", io.BytesIO(SAMPLE_BOT_PY), "text/x-python")}
        data = {"name": "TEST_to_delete", "description": "", "auto_restart": "false"}
        r = requests.post(f"{BASE_URL}/api/bots", headers=auth_headers,
                          files=files, data=data, timeout=15)
        assert r.status_code == 200
        bid = r.json()["id"]
        # Delete
        r = requests.delete(f"{BASE_URL}/api/bots/{bid}", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        # Confirm gone
        r = requests.get(f"{BASE_URL}/api/bots/{bid}", headers=auth_headers, timeout=10)
        assert r.status_code == 404


# ---------- ZIP UPLOAD + MULTI-FILE ----------

import zipfile

def _build_multi_zip(include_json=True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.py", "import time;print('a',flush=True);time.sleep(60)")
        z.writestr("b.py", "import time;print('b',flush=True);time.sleep(60)")
        if include_json:
            z.writestr("config.json", '{"k":"v"}')
    return buf.getvalue()


def _build_single_py_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("only.py", "import time;print('only',flush=True);time.sleep(60)")
    return buf.getvalue()


class TestZipUpload:
    """Multi-file zip upload should return needs_entry_selection when ambiguous."""

    def test_zip_ambiguous_returns_needs_entry_selection(self, auth_headers):
        zbytes = _build_multi_zip()
        files = {"file": ("multi.zip", io.BytesIO(zbytes), "application/zip")}
        data = {"name": "TEST_zip_multi", "description": "", "auto_restart": "false"}
        r = requests.post(f"{BASE_URL}/api/bots", headers=auth_headers,
                          files=files, data=data, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("needs_entry_selection") is True
        assert "a.py" in d["py_files"] and "b.py" in d["py_files"]
        assert d["entry_file"] == ""
        bid = d["id"]
        # Files endpoint should list all 3 (a.py, b.py, config.json)
        r = requests.get(f"{BASE_URL}/api/bots/{bid}/files", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        paths = [f["path"] for f in r.json()["files"]]
        assert "a.py" in paths and "b.py" in paths and "config.json" in paths

        # Cannot start without entry_file
        r = requests.post(f"{BASE_URL}/api/bots/{bid}/start", headers=auth_headers, timeout=10)
        assert r.status_code == 400

        # PUT entry_file = a.py
        r = requests.put(f"{BASE_URL}/api/bots/{bid}", headers=auth_headers,
                         json={"entry_file": "a.py"}, timeout=10)
        assert r.status_code == 200
        assert r.json()["entry_file"] == "a.py"

        # PUT invalid entry_file -> 400
        r = requests.put(f"{BASE_URL}/api/bots/{bid}", headers=auth_headers,
                         json={"entry_file": "nope.py"}, timeout=10)
        assert r.status_code == 400

        # cleanup
        requests.delete(f"{BASE_URL}/api/bots/{bid}", headers=auth_headers, timeout=15)

    def test_zip_with_explicit_entry_file(self, auth_headers):
        zbytes = _build_multi_zip(include_json=False)
        files = {"file": ("multi2.zip", io.BytesIO(zbytes), "application/zip")}
        data = {"name": "TEST_zip_entry", "description": "", "auto_restart": "false",
                "entry_file": "b.py"}
        r = requests.post(f"{BASE_URL}/api/bots", headers=auth_headers,
                          files=files, data=data, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("needs_entry_selection") is None or d.get("needs_entry_selection") is False
        assert d["entry_file"] == "b.py"
        bid = d["id"]
        requests.delete(f"{BASE_URL}/api/bots/{bid}", headers=auth_headers, timeout=15)

    def test_zip_single_py_auto_picks(self, auth_headers):
        zbytes = _build_single_py_zip()
        files = {"file": ("solo.zip", io.BytesIO(zbytes), "application/zip")}
        data = {"name": "TEST_zip_solo", "description": "", "auto_restart": "false"}
        r = requests.post(f"{BASE_URL}/api/bots", headers=auth_headers,
                          files=files, data=data, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["entry_file"] == "only.py"
        bid = d["id"]
        requests.delete(f"{BASE_URL}/api/bots/{bid}", headers=auth_headers, timeout=15)


class TestFileManagement:
    """Per-bot file add/list/delete with path traversal guard."""

    def test_add_and_delete_file(self, auth_headers, created_bot):
        bid = created_bot["id"]
        # Add a json file
        files = {"file": ("TEST_extra.json", io.BytesIO(b'{"a":1}'), "application/json")}
        r = requests.post(f"{BASE_URL}/api/bots/{bid}/files",
                          headers=auth_headers, files=files, timeout=10)
        assert r.status_code == 200, r.text
        rel = r.json()["path"]
        assert rel == "TEST_extra.json"
        # Verify present
        r = requests.get(f"{BASE_URL}/api/bots/{bid}/files", headers=auth_headers, timeout=10)
        paths = [f["path"] for f in r.json()["files"]]
        assert "TEST_extra.json" in paths
        # Delete it
        r = requests.delete(f"{BASE_URL}/api/bots/{bid}/files",
                            headers=auth_headers,
                            params={"path": "TEST_extra.json"}, timeout=10)
        assert r.status_code == 200
        # Confirm gone
        r = requests.get(f"{BASE_URL}/api/bots/{bid}/files", headers=auth_headers, timeout=10)
        paths = [f["path"] for f in r.json()["files"]]
        assert "TEST_extra.json" not in paths

    def test_cannot_delete_entry_file(self, auth_headers, created_bot):
        bid = created_bot["id"]
        entry = created_bot["entry_file"]
        r = requests.delete(f"{BASE_URL}/api/bots/{bid}/files",
                            headers=auth_headers, params={"path": entry}, timeout=10)
        assert r.status_code == 400


class TestSeededBots:
    """The 8 real user bots should be present after the recent cleanup/seed."""

    EXPECTED = {
        "Reaction Botu", "Post Botu", "Police Botu", "Kod Botu",
        "Info Botu", "Dup Botu", "Aff Buton Botu", "Buton Botu",
    }

    def test_eight_bots_present(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bots", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        names = {b["name"] for b in r.json()}
        missing = self.EXPECTED - names
        assert not missing, f"Missing seeded bots: {missing}. Got: {names}"

    def test_buton_botu_has_entry(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/bots", headers=auth_headers, timeout=10)
        bot = next((b for b in r.json() if b["name"] == "Buton Botu"), None)
        assert bot is not None
        # Has a python entry file set
        assert bot.get("entry_file"), f"Buton Botu has no entry_file: {bot}"
