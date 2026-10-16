"""Export the panel-owned guide/help text for browser fallback and offline review."""
import argparse
import json
from pathlib import Path
from panel_guides import DEMO, SUPPORT
from design_tokens import THEMES, WEATHER_ACCENTS
from help_reference import reference
from command_reference import command_tokens
from room_controls import LIGHTING_TABS, SCENES, PROGRAMMES, BLIND_ACTIONS
from panel_version import VERSION
import xml.etree.ElementTree as ET


def content():
    names={'tools':'sliders-horizontal','home':'house','lighting':'lightbulb','white':'lightbulb','off':'lightbulb-off','scenes':'layers',
           'experiment':'flask-conical','appearance':'sun-moon','clock':'calendar-days',
           'screen':'monitor','system':'activity','about':'info','guide':'book-open','legacy':'external-link'}
    names.update({'weather-'+name:name for name in ('sun','moon','cloud-sun','cloud-moon','cloud','cloud-rain','cloud-snow','cloud-lightning','cloud-fog','circle-question-mark')})
    icons={}
    for key,name in names.items():
        svg=ET.parse(Path(__file__).resolve().parents[1]/'assets/icons/svg'/(name+'.svg')).getroot()
        icons[key]=[{'tag':node.tag.split('}')[-1],'attributes':node.attrib} for node in svg]
    return {'version':1,'app_version':VERSION,'icons':icons,'themes':THEMES,'weather_accents':WEATHER_ACCENTS,
            'lighting_tabs':LIGHTING_TABS,'scenes':SCENES,'programmes':PROGRAMMES,'blind_actions':BLIND_ACTIONS,
            'guide':[{'title':title,'icon':kind,'text':text} for title,kind,text in DEMO],
            'help':[{'title':title,'text':text,'commands':commands,'command_tokens':command_tokens(commands),
                     'reference':reference(title)} for title,kind,text,commands in SUPPORT]}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('output');args=parser.parse_args()
    Path(args.output).write_text(json.dumps(content(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
