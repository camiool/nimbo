import os
import stat
import subprocess

from nimbo import keyring, service, status
from nimbo import settings as st
from nimbo.status import Status


def test_systemd_quote():
    assert service.systemd_quote("/home/a b/iCloud") == '"/home/a b/iCloud"'
    assert service.systemd_quote('50%"x') == '"50%%\\"x"'


def test_build_unit(tmp_path):
    cfg = st.Settings(mount_point=str(tmp_path / "Mi iCloud"), cache_max_size_gb=7,
                      config_encrypted=True)
    unit = service.build_unit(cfg, "/usr/bin/rclone")
    assert "Type=notify" in unit
    assert f'"{tmp_path}/Mi iCloud"' in unit
    assert '"--vfs-cache-max-size" "7G"' in unit
    assert '"--password-command"' in unit
    assert f'"unix://{st.mount_rc_socket()}"' in unit
    assert "RuntimeDirectoryMode=0700" in unit
    # Nunca debe contener credenciales.
    assert "password=" not in unit


def test_settings_roundtrip_private():
    cfg = st.Settings(apple_id="yo@icloud.com", cache_max_size_gb=3)
    cfg.save()
    mode = stat.S_IMODE(os.stat(st.settings_path()).st_mode)
    assert mode == 0o600
    assert stat.S_IMODE(os.stat(st.config_dir()).st_mode) == 0o700
    assert st.Settings.load() == cfg


def test_status_unconfigured():
    assert status.StatusProbe().poll(st.Settings()).status is Status.UNCONFIGURED


def _configured():
    st.ensure_private_dir(st.config_dir())
    st.rclone_config_path().write_text("")
    return st.Settings(apple_id="yo@icloud.com")


def test_status_failed_auth(monkeypatch):
    monkeypatch.setattr(service, "state", lambda: "failed")
    monkeypatch.setattr(service, "recent_log",
                        lambda n=80: "CRITICAL: Failed to create file system: trust token expired")
    assert status.StatusProbe().poll(_configured()).status is Status.AUTH


def test_status_failed_other(monkeypatch):
    monkeypatch.setattr(service, "state", lambda: "failed")
    monkeypatch.setattr(service, "recent_log", lambda n=80: "ERROR: mountpoint is not empty")
    assert status.StatusProbe().poll(_configured()).status is Status.ERROR


def test_status_paused(monkeypatch):
    monkeypatch.setattr(service, "state", lambda: "inactive")
    assert status.StatusProbe().poll(_configured()).status is Status.PAUSED


def test_status_active(monkeypatch, fake_rc):
    monkeypatch.setattr(service, "state", lambda: "active")
    probe = status.StatusProbe()
    probe.rc.socket_path = fake_rc.path
    fake_rc.reply("core/stats", {"transferring": [], "speed": 0})
    assert probe.poll(_configured()).status is Status.OK
    assert any(m == "operations/list" for m, _ in fake_rc.calls)  # comprobación de salud

    fake_rc.reply("core/stats", {"transferring": [{"name": "x"}], "speed": 10})
    assert probe.poll(_configured()).status is Status.SYNCING

    fake_rc.reply("core/stats", {"transferring": [], "lastError": "401 Unauthorized"})
    assert probe.poll(_configured()).status is Status.AUTH


def test_keyring_helper(monkeypatch, capsys):
    store = {}

    def fake_run(cmd, **kw):
        if cmd[1] == "lookup":
            return subprocess.CompletedProcess(cmd, 0 if "k" in store else 1,
                                               store.get("k", ""), "")
        if cmd[1] == "store":
            store["k"] = kw["input"]
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(keyring, "available", lambda: True)
    monkeypatch.setattr(keyring.subprocess, "run", fake_run)

    monkeypatch.delenv("RCLONE_PASSWORD_CHANGE", raising=False)
    assert keyring.main() == 1  # sin clave y sin permiso para crearla

    monkeypatch.setenv("RCLONE_PASSWORD_CHANGE", "1")
    assert keyring.main() == 0
    created = capsys.readouterr().out.strip()
    assert len(created) >= 40

    monkeypatch.delenv("RCLONE_PASSWORD_CHANGE")
    assert keyring.main() == 0
    assert capsys.readouterr().out.strip() == created
