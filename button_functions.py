import sys
sys.path.append("../catkin_ws/src/scr_control/scripts/blinds")
import SCR_blind_client as blind_control

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
	blind_control.lift_all(100)

def button_close():
	blind_control.lift_all(0)

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
