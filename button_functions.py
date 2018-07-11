import sys, time, threading
sys.path.append("../catkin_ws/src/scr_control/scripts/blinds")
sys.path.append("../catkin_ws/src/scr_control/scripts/lights")
import SCR_blind_client as blind_control
import SCR_OctaLight_client as light_control

def button_on(touch):
	light_control.cct_all(3500, 1000)

def button_off(touch):
	light_control.cct_all(0, 0)

def button_sliders(touch):
	light_control.cct_all(int(touch.cctSlider.get()), int(touch.intSlider.get()))

def button_cct(touch):
	pass

def button_int(touch):
	pass

def button_auto(touch):
	pass

def button_grad(touch):
	pass

def button_sun(touch):
	pass

def button_circ(touch):
	pass

def button_sat(touch):
	pass

def button_lid(touch):
	pass

def button_dul(touch):
	pass

def button_lift(touch):
	blind_control.lift_all(100)
	
def button_open(touch):
	blind_control.lift_all(50)

def button_close(touch):
	blind_control.tilt_all(100)
	time.sleep(2)
	blind_control.lift_all(0)

	
def slider_cct(touch, value):
	if touch.slidersActive:
		light_control.cct_all(int(value), int(touch.intSlider.get()))

def slider_int(touch, value):
	if touch.slidersActive:
		light_control.cct_all(int(touch.cctSlider.get()), int(value))

def setButtons(buttons, i):
	if i in range(12, 15):
		for j in range(12, 15):
			buttons[j].setOff()
	else:
		for j in range(0, 12):
			buttons[j].setOff()

	buttons[i].setOn()

def setSliders(touch, i):
	if i < 12:
		if i==2:
			touch.cctSlider.config(troughcolor='SlateGray2')
			touch.intSlider.config(troughcolor='SlateGray2')
			touch.slidersActive = True
		else:
			touch.cctSlider.config(troughcolor='ivory3')
			touch.intSlider.config(troughcolor='ivory3')
			touch.slidersActive = False

def pressButton(touch, i):
	setButtons(touch.buttons, i)
	setSliders(touch, i)
	button_functions[i](touch)

button_functions = [button_on, button_off, button_sliders, button_cct, button_int, button_auto, button_grad, button_sun, button_circ, button_sat, button_lid, button_dul, button_open, button_tilt, button_close]
button_names = ["On", "Off", "Enable\nSliders",
				"Dynamic\nCCT", "Dynamic\nInt", "Auto",
				"Gradient", "Sun", "Circ",
				"Sat", "Lid","Dul",
				"Lift Blinds", "Toggle Tilt", "Close\nBlinds"]