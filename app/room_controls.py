"""Shared room-control labels and readiness. No hardware access or discovery."""
LIGHTING_TABS = (('White light','white'),('Scenes','scenes'),('Programmes','programmes'),('Channels','channels'))
SCENES = (
    {'id':'Fid','label':'Fid','detail':'Original eight-channel room mixture.'},
    {'id':'Sat','label':'Sat','detail':'Original eight-channel room mixture.'},
    {'id':'Dul','label':'Dul','detail':'Original eight-channel room mixture.'},
    {'id':'Gradient','label':'Gradient','detail':'A static colour pattern across individual fixtures.'},
)
PROGRAMMES = (
    {'id':'Sun','label':'Sun','subtitle':'Travelling light',
     'detail':'Colour temperature and light level move through fixture groups in sequence.'},
    {'id':'Circ','label':'Circ','subtitle':'Whole-room cycle',
     'detail':'All fixtures follow the same colour-temperature and light-level cycle together.'},
)
BLIND_ACTIONS = (('lift','Lift blinds'),('open','Open slats'),('close','Close & lower'))


def blind_readiness(enabled, connected, busy=False):
    if not enabled:return {'enabled':False,'connected':bool(connected),'available':False,'detail':'Disabled in settings'}
    if not connected:return {'enabled':True,'connected':False,'available':False,'detail':'Controller not connected'}
    if busy:return {'enabled':True,'connected':True,'available':False,'detail':'Room controls busy'}
    return {'enabled':True,'connected':True,'available':True,'detail':'Ready'}
