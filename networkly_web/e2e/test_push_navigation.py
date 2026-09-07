"""Notification clicks retain the navigation promise and stay in the app."""
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "static/service-worker.js"


def install_worker(page, target="/opportunities/mine/", reject=False):
    page.evaluate("""({script, target, reject}) => {
      window.workerCalls = [];
      window.clickFinished = false;
      const handlers = {};
      const client = {
        url: 'https://networkly.example/app/',
        navigate: url => {
          workerCalls.push(['navigate', url]);
          return reject ? Promise.reject(new Error('closed tab')) :
            new Promise(resolve => { window.finishNavigation = () => resolve(client); });
        },
        focus: () => { workerCalls.push(['focus']); return Promise.resolve(client); },
      };
      const worker = {location:{origin:'https://networkly.example'},
        addEventListener: (name, handler) => { handlers[name] = handler; }};
      const windows = {matchAll: () => Promise.resolve([client]),
        openWindow: url => { workerCalls.push(['open', url]); return Promise.resolve(); }};
      new Function('self', 'clients', script)(worker, windows);
      handlers.notificationclick({notification:{close:()=>{}, data:{url:target}},
        waitUntil: promise => { window.clickResult = promise.then(() => { clickFinished = true; }); }});
    }""", {"script": SCRIPT.read_text(), "target": target, "reject": reject})


def test_click_waits_for_navigation_before_focusing(session):
    page = session.page
    install_worker(page)
    assert page.evaluate("workerCalls") == [["navigate", "https://networkly.example/opportunities/mine/"]]
    assert page.evaluate("clickFinished") is False
    page.evaluate("finishNavigation()")
    page.evaluate("clickResult")
    assert page.evaluate("workerCalls")[1:] == [["focus"]]


def test_external_destination_falls_back_to_app(session):
    page = session.page
    install_worker(page, target="https://unrelated.example/")
    assert page.evaluate("workerCalls")[0] == ["navigate", "https://networkly.example/opportunities/mine/"]
    page.evaluate("finishNavigation()")
    page.evaluate("clickResult")


def test_closed_tab_opens_the_requested_app_page(session):
    page = session.page
    install_worker(page, target="/opportunities/mine/?stage=saved", reject=True)
    page.evaluate("clickResult")
    assert page.evaluate("workerCalls") == [
        ["navigate", "https://networkly.example/opportunities/mine/?stage=saved"],
        ["open", "https://networkly.example/opportunities/mine/?stage=saved"],
    ]
