"""Notification controls must reflect both browser and server outcomes."""
from pathlib import Path
import pytest
from playwright.sync_api import expect

SCRIPT = Path(__file__).resolve().parents[1] / "static/js/push-subscribe.js"


def prepare(page, *, subscribed=True, browser_subscription=True, status_ok=True):
    page.set_content("""
    <div data-push-root data-vapid-public-key="AQ" data-csrf="test"
         data-subscribe-url="/subscribe" data-unsubscribe-url="/unsubscribe" data-status-url="/status">
      <input type="checkbox" data-push-toggle checked>
      <span data-push-status></span>
    </div>""")
    page.evaluate("""({subscribed, browserSubscription, statusOK}) => {
      window.pushCalls = []; window.replyOK = false; window.redirected = false;
      window.browserOK = true;
      window.PushManager = function () {};
      Object.defineProperty(window, 'Notification', {configurable:true, value:{permission:'granted'}});
      const sub = {endpoint:'https://push.example/device', toJSON:()=>({endpoint:'https://push.example/device'}),
        unsubscribe:()=>{pushCalls.push('browser'); return Promise.resolve(browserOK);}};
      Object.defineProperty(navigator,'serviceWorker',{configurable:true,value:{
        getRegistration:()=>Promise.resolve({pushManager:{getSubscription:()=>Promise.resolve(browserSubscription ? sub : null)}}),
        register:()=>Promise.resolve({pushManager:{subscribe:()=>Promise.resolve(sub)}})
      }});
      window.fetch = (url, options) => {
        if (url === "/status") return Promise.resolve({ok:statusOK, json:()=>Promise.resolve({subscribed})});
        pushCalls.push(url);
        return Promise.resolve({ok:replyOK, redirected:redirected});
      };
    }""", {"subscribed":subscribed, "browserSubscription":browser_subscription, "statusOK":status_ok})
    page.add_script_tag(path=str(SCRIPT))
    expect(page.locator("[data-push-toggle]")).to_be_enabled()


def test_failed_unsubscribe_keeps_endpoint_for_retry(session):
    page = session.page
    prepare(page)
    page.locator('[data-push-toggle]').click()
    expect(page.locator('[data-push-status]')).to_contain_text("Couldn't turn this off")
    expect(page.locator('[data-push-toggle]')).to_be_checked()
    assert page.evaluate("pushCalls") == ["/unsubscribe"]
    page.evaluate("replyOK=true")
    page.locator('[data-push-toggle]').click()
    expect(page.locator('[data-push-status]')).to_have_text("Off.")
    assert page.evaluate("pushCalls") == ["/unsubscribe", "/unsubscribe", "browser"]


def test_browser_decline_does_not_claim_unsubscribed(session):
    page = session.page
    prepare(page)
    page.evaluate("replyOK=true; browserOK=false")
    page.locator('[data-push-toggle]').click()
    expect(page.locator('[data-push-status]')).to_contain_text("Couldn't turn this off")
    expect(page.locator('[data-push-toggle]')).to_be_checked()


def test_signin_redirect_does_not_claim_subscription_saved(session):
    page = session.page
    prepare(page)
    page.evaluate("replyOK=true; redirected=true; document.querySelector('[data-push-toggle]').checked=false")
    page.locator('[data-push-toggle]').click()
    expect(page.locator('[data-push-status]')).to_contain_text("Couldn't turn this on")
    expect(page.locator('[data-push-toggle]')).not_to_be_checked()


def test_permission_failure_restores_a_retryable_toggle(session):
    page = session.page
    prepare(page)
    page.evaluate("""() => {
      Notification.permission = 'default';
      Notification.requestPermission = () => Promise.reject(new Error('permission unavailable'));
      document.querySelector('[data-push-toggle]').checked = false;
    }""")
    page.locator('[data-push-toggle]').click()
    expect(page.locator('[data-push-status]')).to_contain_text("Couldn't request permission")
    expect(page.locator('[data-push-toggle]')).not_to_be_checked()
    expect(page.locator('[data-push-toggle]')).to_be_enabled()
    assert page.evaluate("pushCalls") == []


@pytest.mark.parametrize("subscribed,browser_subscription,expected", [
    (True, True, True), (False, True, False), (True, False, False),
])
def test_initial_state_requires_both_browser_subscription_and_account_ownership(
    session, subscribed, browser_subscription, expected,
):
    page = session.page
    prepare(page, subscribed=subscribed, browser_subscription=browser_subscription)
    expect(page.locator('[data-push-toggle]')).to_be_checked(checked=expected)
    expect(page.locator('[data-push-status]')).to_contain_text("On." if expected else "Off.")
    assert page.evaluate("pushCalls") == []


def test_failed_initial_check_is_not_presented_as_a_confirmed_state(session):
    page = session.page
    prepare(page, status_ok=False)
    expect(page.locator('[data-push-toggle]')).not_to_be_checked()
    expect(page.locator('[data-push-status]')).to_contain_text("Couldn't check this device")
    assert page.evaluate("pushCalls") == []
