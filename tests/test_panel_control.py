"""The browser may submit only bounded commands to the existing UI owner."""
import queue
import threading
import time
from types import SimpleNamespace
import pytest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from panel_control import command, Bridge
from panel_remote import execute
from design_tokens import THEMES


def envelope(action='off',arguments=None,revision='current',id='test-command-00001'):
    return {'id':id,'revision':revision,'action':action,'arguments':arguments or {}}


def test_commands_reject_blinds_shell_paths_extra_fields_and_invalid_numbers():
    for value in [envelope('blinds'),envelope('shell',{'command':'echo hi'}),
                  dict(envelope(),path='/tmp/x'),envelope('cct',{'cct':True,'intensity':1000}),
                  envelope('channels',{'values':[100]*7}),envelope('channels',{'values':[101]*8}),
                  envelope('idle',{'value':True}),envelope('blinds_display',{'value':'enabled'}),
                  envelope([],{}),envelope('cct',{'cct':3500,'intensity':1901})]:
        with pytest.raises(ValueError):command(value)
    assert command(envelope('cct',{'cct':3500,'intensity':1000}))['action']=='cct'


def test_stale_expired_and_duplicate_commands_never_dispatch_twice():
    bridge=Bridge.__new__(Bridge)
    import collections
    bridge.requests=queue.Queue();bridge.receipts=collections.OrderedDict();bridge.fingerprints={}
    bridge.lock=threading.Lock();calls=[]
    def put(value,expired=False):
        item={'value':value,'deadline':time.monotonic()+(-1 if expired else 2),'cancelled':False,'done':threading.Event()}
        bridge.requests.put(item)
        bridge.drain(lambda:{'revision':'current'},lambda value:calls.append(value) or {'ok':True,'code':202})
        return item['reply']
    assert put(envelope(revision='old'))['code']==409 and not calls
    assert put(envelope(),True)['code']==408 and not calls
    first=put(envelope());assert first['ok'] and len(calls)==1
    assert put(envelope())==first and len(calls)==1
    assert put(envelope('on'))['code']==409 and len(calls)==1


def test_remote_light_action_is_blocked_when_owner_busy_uncertain_legacy_or_studying(monkeypatch):
    import panel_remote
    owner=SimpleNamespace(lights_on=lambda:pytest.fail('Must not call the owner'))
    for state in ({'busy':True,'can_control':True},{'busy':False,'can_control':False}):
        monkeypatch.setattr(panel_remote,'snapshot',lambda panel:state)
        with pytest.raises(RuntimeError):execute(owner,envelope('on'))
    sent=[]
    monkeypatch.setattr(panel_remote,'snapshot',lambda panel:{'busy':False,'can_control':True})
    owner=SimpleNamespace(idle_active=False,lights_on=lambda:sent.append('existing owner'),
                          emit=lambda *a,**kw:None,activity=lambda *a:None,pending=None)
    assert execute(owner,envelope('on'))['ok'] and sent==['existing owner']


def test_theme_text_contrast_and_strictly_neutral_dark_roles():
    def rgb(value):return [int(value[i:i+2],16)/255 for i in (1,3,5)]
    def light(value):return sum(c*w for c,w in zip([c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb(value)],(.2126,.7152,.0722)))
    def ratio(a,b):
        high,low=sorted((light(a),light(b)),reverse=True);return (high+.05)/(low+.05)
    for theme in THEMES.values():
        for fg,bg in [('ink','bg'),('muted','bg'),('ink','control'),('muted','control'),
                      ('selected_ink','accent'),('selected_ink','accent_pressed'),('ink','pressed'),
                      ('good','control'),('warning','control'),('warning','bg')]:
            assert ratio(theme[fg],theme[bg])>=4.5,(fg,bg,theme)
    assert all(len(set(rgb(value)))==1 for value in THEMES['dark'].values())


def test_blind_permission_is_strict_and_independent_of_visibility_and_connection():
    import preferences
    from scr_touch_panel import Panel
    assert preferences.validated({}) == {}  # old files retain the disabled default
    assert preferences.validated({'blinds_enabled':False}) == {'blinds_enabled':False}
    for invalid in (1, 0, 'true', None):
        with pytest.raises(ValueError):preferences.validated({'blinds_enabled':invalid})
        with pytest.raises(ValueError):command(envelope('blinds_enabled', {'value':invalid}))
    state = Panel.__new__(Panel)
    state.pending=state.queued_intent=state.release_target=state.closing=None
    state.running=False;state.mode='room';state.blinds_display='hidden'
    state.blinds_enabled=False;state.blind_controller=None
    messages=[];calls=[];state.status_text=SimpleNamespace(set=messages.append)
    for name in ('lift','open','close'):
        assert command(envelope('blind', {'name':name}))
        assert not state.blind_command(name)
    assert state.blind_state()['detail']=='Disabled in settings'
    state.blinds_enabled=True
    assert not state.blind_command('open')
    assert state.blind_state()['detail']=='Controller not connected'
    state.blind_controller=SimpleNamespace(connected=True,submit=calls.append)
    for field, value in [('pending',{}),('queued_intent',True),('release_target','original'),('closing',True),('running',True),('mode','original')]:
        previous=getattr(state,field);setattr(state,field,value or True)
        assert not state.blind_command('lift')
        setattr(state,field,previous)
    assert calls==[]
    for name in ('lift','open','close'):assert state.blind_command(name)
    assert calls==['lift','open','close']
    with pytest.raises(ValueError):state.blind_command('shell')
    state.blinds_enabled=False
    assert not state.blind_command('open') and len(calls)==3


def test_remote_blind_action_uses_owner_readiness_and_never_bypasses_setting(monkeypatch):
    import panel_remote
    calls=[]
    owner=SimpleNamespace(blind_command=lambda name:calls.append(name) or True,
                          emit=lambda *a,**kw:None,activity=lambda *a:None,pending=None)
    for available in (False,True):
        monkeypatch.setattr(panel_remote,'snapshot',lambda panel:{'busy':False,'blinds':{'available':available,'detail':'Disabled in settings'}})
        if not available:
            with pytest.raises(RuntimeError):execute(owner,envelope('blind',{'name':'lift'}))
            assert not calls
        else:assert execute(owner,envelope('blind',{'name':'lift'}))['ok']
    assert calls==['lift']
