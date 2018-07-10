import sys
sys.path.append("../catkin_ws/src/scr_control/scripts/blinds")
sys.path.append("../catkin_ws/src/scr_control/scripts/lights")
import SCR_blind_client as blind_control
import SCR_OctaLight_client as light_control

def button_auto():
	pass

def button_off():
	pass

def button_cct():
	pass

def button_sources():
	pass

def button_bright():
	pass

def button_dulling():
	pass

def button_open():
	blind_control.tilt_all(50)
	blind_control.lift_all(100)

def button_close():
	blind_control.lift_all(0)
	blind_control.tilt_all(100)

def slider_cct(scale, value):
	light_control.cct_all(int(value), int(scale.get()))

def slider_int(scale, value):
	light_control.cct_all(int(scale.get()), int(value))

def setButtons(buttons, i):
	for j in range(len(buttons)):
		if j == i:
			buttons[j].setOn()
		else:
			buttons[j].setOff()

def pressButton(buttons, i):
	setButtons(buttons, i)
	button_functions[i]()

button_functions = [button_auto, button_off, button_cct, button_sources, button_bright, button_dulling, button_open, button_close]