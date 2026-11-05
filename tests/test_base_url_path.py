"""base_url_path / result_url_host must work with or without slashes."""
import re
from pathlib import Path

import pytest

from app import main as main_module
from app import scheduler as scheduler_module
from app.config import Settings
from app.models import Job

# (value given in the environment, normalized value)
BASE_VARIANTS = [
    ("", ""),
    ("/", ""),
    ("//", ""),
    ("blast", "/blast"),
    ("/blast", "/blast"),
    ("blast/", "/blast"),
    ("/blast/", "/blast"),
    ("  /blast//  ", "/blast"),
    ("/tools/blast/", "/tools/blast"),
    ("//tools///blast//", "/tools/blast"),
]
HOST_VARIANTS = ["", "https://my.server", "https://my.server/", "https://my.server///"]


def _no_double_slash(url: str) -> bool:
    return "//" not in re.sub(r"^[a-z]+://", "", url)


@pytest.mark.parametrize("given,expected", BASE_VARIANTS)
def test_base_url_path_is_normalized(given, expected):
    assert Settings(base_url_path=given).base_url_path == expected


def test_base_url_path_normalized_from_environment(monkeypatch):
    monkeypatch.setenv("BASE_URL_PATH", "blast/")
    assert Settings().base_url_path == "/blast"


@pytest.mark.parametrize("host", HOST_VARIANTS)
def test_result_url_host_loses_trailing_slash(host):
    assert not Settings(result_url_host=host).result_url_host.endswith("/")


@pytest.mark.parametrize("host", HOST_VARIANTS)
@pytest.mark.parametrize("given,norm", BASE_VARIANTS)
def test_url_helpers(given, norm, host):
    s = Settings(base_url_path=given, result_url_host=host)
    h = host.rstrip("/")
    assert s.url() == f"{norm}/"
    assert s.url("job/status/x") == f"{norm}/job/status/x"
    assert s.url("/job/status/x") == f"{norm}/job/status/x"      # leading slash ignored
    assert s.external_url("job/results/x") == f"{h}{norm}/job/results/x"
    assert s.result_url == f"{h}{norm}/tmp/"
    for u in (s.url(), s.url("a/b"), s.external_url("a/b"), s.result_url):
        assert _no_double_slash(u), u


@pytest.mark.parametrize("host", HOST_VARIANTS)
@pytest.mark.parametrize("given,norm", BASE_VARIANTS)
def test_scheduler_result_url(monkeypatch, given, norm, host):
    s = Settings(base_url_path=given, result_url_host=host)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: s)
    job = Job()
    job.program_name, job.job_uid = "blast", "blast-abc"
    url = scheduler_module.Scheduler().get_result_url(job)
    assert url == f"{host.rstrip('/')}{norm}/tmp/blast/blast-abc/"
    assert _no_double_slash(url)


def test_empty_base_path_result_url_is_absolute_not_relative(monkeypatch):
    """Regression: with no prefix this used to be the relative URL 'tmp/...'."""
    s = Settings(base_url_path="")
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: s)
    job = Job()
    job.program_name, job.job_uid = "blast", "u"
    assert scheduler_module.Scheduler().get_result_url(job).startswith("/")


# ---- end to end through the application --------------------------------------

def _urls(html: str):
    return re.findall(r'(?:href|src|action)="([^"]+)"', html)


@pytest.mark.parametrize("host", ["", "https://my.server/"])
@pytest.mark.parametrize("given,norm", BASE_VARIANTS)
def test_application_urls(client, db_session, monkeypatch, given, norm, host):
    c, fake = client
    s = Settings(base_url_path=given, result_url_host=host)
    h = host.rstrip("/")
    monkeypatch.setattr(main_module, "settings", s)

    # index: form action and static assets
    index = c.get("/").text
    urls = _urls(index)
    assert f'action="{norm}/"' in index
    statics = [u for u in urls if "/static/" in u]
    assert statics and all(u.startswith(f"{norm}/static/") for u in statics), statics
    assert all(_no_double_slash(u) for u in urls if u.startswith("/")), urls

    # submit with an e-mail so the mail body is written too
    r = c.post("/", data={"program": "blastn", "pastedSeq": ">s\nACGT", "dbPath": "/db/some/bank",
                          "email": "me@example.com"}, follow_redirects=False)
    assert r.status_code == 303
    uid = r.headers["location"].rsplit("/", 1)[-1]
    assert r.headers["location"] == f"{norm}/job/status/{uid}"

    work_dir = Path(fake.get_work_dir(db_session.get(Job, uid)))
    body = (work_dir / "mail_body.txt").read_text()
    assert f"{h}{norm}/job/results/{uid}" in body
    assert _no_double_slash(re.search(r"address: (\S+)", body).group(1))
    back = re.search(r"launch another job, go to (\S+)", body).group(1)
    assert back.endswith(f"{norm}/") and _no_double_slash(back)

    # status page + its JSON endpoint
    status = c.get(f"/job/status/{uid}")
    assert f'{norm}/job/status/{uid}.js' in status.text
    assert f'href="{norm}/job/status/{uid}"' in status.text
    js = c.get(f"/job/status/{uid}.js").json()
    assert js["resultsUrl"] == f"{norm}/job/results/{uid}"

    # results: redirect target while running, then download links
    r2 = c.get(f"/job/results/{uid}", follow_redirects=False)
    assert r2.headers["location"] == f"{norm}/job/status/{uid}"
    fake.finished = True
    r3 = c.get(f"/job/status/{uid}", follow_redirects=False)
    assert r3.headers["location"] == f"{norm}/job/results/{uid}"
    assert c.get(f"/job/results/{uid}").status_code == 200


@pytest.mark.parametrize("given,norm", [("blast/", "/blast"), ("/blast", "/blast"), ("", "")])
def test_custom_static_url(given, norm):
    assert Settings(base_url_path=given).url("static/custom/my.css") == f"{norm}/static/custom/my.css"
