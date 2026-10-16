"""Shared theme roles: neutral dark surfaces with restrained semantic accents."""
THEMES = {
    'light': {'bg':'#ffffff','surface':'#ffffff','ink':'#12384b','muted':'#476373',
              'control':'#edf1f4','border':'#cbd6df','accent':'#176b72','selected_ink':'#ffffff',
              'accent_pressed':'#10575e','pressed':'#dde8e8','icon_colour':'#386a73',
              'good':'#23794c','warning':'#875709','weather_warm':'#a16a24','weather_cool':'#3b7590'},
    'dark': {'bg':'#171717','surface':'#171717','ink':'#f2f2f2','muted':'#bdbdbd',
             'control':'#292929','border':'#454545','accent':'#76cfc5','selected_ink':'#172624',
             'accent_pressed':'#a2dfd8','pressed':'#414141','icon_colour':'#8ccfc8',
             'good':'#89caa2','warning':'#e8b86a','weather_warm':'#e5b874','weather_cool':'#8cb8db'},
}

WEATHER_ACCENTS = {name:'weather_warm' for name in ('sun','moon','cloud-sun','cloud-moon')}
WEATHER_ACCENTS.update({name:'weather_cool' for name in ('cloud-rain','cloud-snow','cloud-lightning')})
