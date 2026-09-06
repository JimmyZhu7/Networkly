"""Categorical relationship stages preserve the domain state and accessible label.

The retired percentage meter implied numerical progress. The replacement marks
one named current stage and leaves domain values and status classes unchanged.
"""
from types import SimpleNamespace
import re
import pytest
from django.template.loader import render_to_string
from core.templatetags.textstyle import relationship_label
from crm.utils import WARMTH_ORDER

@pytest.mark.parametrize('state,label', [('cold','New'),('replied','Replied'),('chatted','Had a chat'),('advocate','Advocate')])
def test_current_relationship_is_named_without_inventing_progress(state,label):
    contact=SimpleNamespace(pk=1,id=1,warmth=state,name='Test contact')
    html=render_to_string('crm/_contact_live.html',{'contact':contact,'warmth_order':WARMTH_ORDER})
    stages=re.search(r'<ol class="relationship-stages".*?</ol>',html,re.S).group(0)
    assert f'<li aria-current="step">{label}</li>' in stages
    assert stages.count('aria-current="step"')==1
    assert 'progressbar' not in stages and 'meter-fill' not in html
    assert contact.warmth==state

def test_unknown_relationship_label_is_not_invented():
    assert relationship_label('unrecognized')=='unrecognized'

def test_chip_keeps_machine_state_and_human_label_separate():
    html=render_to_string('crm/_act_card.html',{'a':{'contact':{'id':1,'name':'Test contact','warmth':'chatted'},'action':'maintain'}})
    assert 'class="chip warmth-chatted"' in html
    assert '>Had a chat</span>' in html


def test_role_people_dot_retains_css_state_key():
    html = render_to_string('directory/_role_people.html', {'net': {
        'firm_name': 'Example', 'firm_slug': 'example', 'total': 1,
        'people': [{'id': 1, 'name': 'Test contact', 'warmth': 'chatted',
                    'warmth_label': 'Had a chat', 'days_since': 2}],
    }})
    assert 'class="rp-dot warmth-dot-chatted"' in html
    assert 'Had a chat' in html
