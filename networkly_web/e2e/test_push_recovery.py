"""Notification controls must reflect both browser and server outcomes."""
from pathlib import Path
import pytest
from playwright.sync_api import expect

SCRIPT = Path(__file__).resolve().parents[1] / "static/js/push-subscribe.js"


def prepare(page):
    page.set_content("""
    <div data-push-root data-vapid-public-key="AQ" data-csrf="test"
         data-subscribe-url="/subscribe" data-unsubscribe-url="/unsubscribe">
      <input type="checkbox" data-push-toggle checked>
      <span data-push-status></span>
    </div>""")
    page.evaluate("""() => {
      window.pushCalls = []; window.replyOK = false; window.redirected = false;
      window.browserOK = true;
      window.PushManager = function () {};
      Object.defineProperty(window, 'Notification', {configurable:true, value:{permission:'granted'}});
      const sub = {endpoint:'https://push.example/device', toJSON:()=>({endpoint:'https://push.example/device'}),
        unsubscribe:()=>{pushCalls.push('browser'); return Promise.resolve(browserOK);}};
      Object.defineProperty(navigator,'serviceWorker',{configurable:true,value:{
        getRegistration:()=>Promise.resolve({pushManager:{getSubscription:()=>Promise.resolve(sub)}}),
        register:()=>Promise.resolve({pushManager:{subscribe:()=>Promise.resolve(sub)}})
      }});
      window.fetch = (url, options) => {
        pushCalls.push(url);
        return Promise.resolve({ok:replyOK, redirected:redirected});
      };
    }""")
    page.add_script_tag(path=str(SCRIPT))


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
