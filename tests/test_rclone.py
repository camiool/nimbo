import pytest

from nimbo import rclone
from nimbo import settings as st


def test_parse_version():
    assert rclone.parse_version("rclone v1.76.0\n- os/version: arch") == (1, 76, 0)
    assert rclone.parse_version("rclone v1.70.3-DEV") == (1, 70, 3)
    assert rclone.parse_version("algo raro") is None


@pytest.mark.parametrize(
    "msg",
    [
        "trust token expired, please reauth",
        'missing icloud trust token: try refreshing it with "rclone config reconnect icloud:"',
        "HTTP error 401 (401 Unauthorized)",
        "421 Misdirected Request",
    ],
)
def test_auth_errors_detected(msg):
    assert rclone.looks_like_auth_error(msg)


@pytest.mark.parametrize("msg", ["", "connection reset by peer", "file 4010.txt not found"])
def test_non_auth_errors(msg):
    assert not rclone.looks_like_auth_error(msg)


def test_common_args_plain_and_encrypted():
    cfg = st.Settings()
    assert rclone.common_args(cfg) == ["--config", str(st.rclone_config_path())]
    cfg.config_encrypted = True
    args = rclone.common_args(cfg)
    assert args[2] == "--password-command"
    assert "nimbo" in args[3]


def test_config_step_from_rc_2fa():
    out = {
        "State": "2fa_do",
        "Option": {
            "Name": "config_2fa",
            "Help": "Two-factor authentication: enter your 2FA code",
            "IsPassword": False,
            "Examples": None,
        },
        "Error": "",
    }
    step = rclone.ConfigStep.from_rc(out)
    assert step.state == "2fa_do"
    assert step.name == "config_2fa"
    assert step.choices == []


def test_config_step_from_rc_choices():
    out = {
        "State": "2fa_sms_select",
        "Option": {
            "Name": "config_2fa_phone",
            "Help": "Select phone",
            "Examples": [{"Value": "1:sms", "Help": "+34 ••• •• 12"}],
        },
    }
    step = rclone.ConfigStep.from_rc(out)
    assert step.choices == [("1:sms", "+34 ••• •• 12")]


def test_config_step_done_and_error():
    assert rclone.ConfigStep.from_rc({"State": "", "Option": None, "Error": ""}) is None
    with pytest.raises(rclone.RcloneError):
        rclone.ConfigStep.from_rc({"Option": None, "Error": "bad code"})


def test_rc_client_roundtrip(fake_rc):
    fake_rc.reply("core/stats", {"transferring": [{"name": "a"}], "speed": 2048})
    fake_rc.reply("vfs/stats", {"diskCache": {"uploadsInProgress": 1, "uploadsQueued": 2}})
    status = rclone.mount_status(rclone.RcClient(fake_rc.path))
    assert status.transferring == 1
    assert status.queued_uploads == 3
    assert status.busy
    assert fake_rc.calls[1] == ("vfs/stats", {"fs": "icloud:"})


def test_rc_client_auth_error(fake_rc):
    fake_rc.reply("operations/list", {"error": "trust token expired, please reauth"}, 500)
    with pytest.raises(rclone.AuthExpiredError):
        rclone.RcClient(fake_rc.path).call("operations/list")


def test_setup_session_sends_password_in_body_not_argv(fake_rc):
    session = rclone.SetupSession(st.Settings())
    session.rc = rclone.RcClient(fake_rc.path)
    fake_rc.reply("config/create", {"State": "2fa_do", "Option": {"Name": "config_2fa"}})
    step = session.create("yo@icloud.com", "secreto")
    method, params = fake_rc.calls[-1]
    assert method == "config/create"
    assert params["type"] == "iclouddrive"
    assert params["parameters"] == {
        "apple_id": "yo@icloud.com", "password": "secreto", "service": "drive"}
    assert params["opt"] == {"nonInteractive": True, "obscure": True}

    fake_rc.reply("config/update", {"State": "", "Option": None})
    assert session.answer(step, "123456") is None
    method, params = fake_rc.calls[-1]
    assert params["opt"] == {"continue": True, "state": "2fa_do", "result": "123456"}


def test_reconnect_without_password(fake_rc):
    session = rclone.SetupSession(st.Settings())
    session.rc = rclone.RcClient(fake_rc.path)
    fake_rc.reply("config/update", {"State": "2fa_do", "Option": {"Name": "config_2fa"}})
    session.reconnect()
    _, params = fake_rc.calls[-1]
    assert params["parameters"] == {}
    assert params["opt"] == {"nonInteractive": True, "obscure": False}
