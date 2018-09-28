import sys, time, threading, requests
sys.path.append("../catkin_ws/src/scr_control/scripts/blinds")
sys.path.append("../catkin_ws/src/scr_control/scripts/lights")
import SCR_blind_client as blind_control
import SCR_OctaLight_client as light_control

server_ip   = 'http://192.168.0.2:5000'
log_presses = True

def log(arg):
	requests.post(server_ip + '/Script_Run', json={"name": "log", "arg": arg})

def button_on(touch):
	log("on")
	light_control.cct_all(3500, 1000)

def button_off(touch):
	log("off")
	light_control.cct_all(0, 0)

def button_sliders(touch):
	log("cct:" + str(touch.cctSlider.get()))
	log("int:" + str(touch.intSlider.get()))
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
	log("sun")
	requests.post(server_ip + '/Script_Run', json={"name": "sun"})

def button_circ(touch):
	log("circ")
	requests.post(server_ip + '/Script_Run', json={"name": "circ"})

def button_sat(touch):
	log("sat")
	light_control.sources_all(21, 14, 4, 73, 22, 100, 22, 4)

def button_fid(touch):
	log("fid")
	light_control.sources_all(39, 6, 25, 56, 57, 100, 3, 6)

def button_dul(touch):
	log("dul")
	light_control.sources_all(41, 2, 25, 53, 38, 100, 2, 0)

def button_lift(touch):
	log("lift")
	blind_control.lift_all(100)
	
def button_open(touch):
	log("open")
	blind_control.tilt_all(50)

def button_close(touch):
	log("close")
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
	requests.post(server_ip + '/Script_Kill', json={"name": "sun"})
	requests.post(server_ip + '/Script_Kill', json={"name": "circ"})
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

button_functions = [button_on, button_off, button_sliders,
					button_cct, button_int, button_auto,
					button_grad, button_sun, button_circ,
					button_sat, button_fid, button_dul,
					button_lift, button_open, button_close]

button_names = ["On", "Off", "Enable\nSliders",
				"Dynamic\nCCT", "Dynamic\nInt", "Auto",
				"Gradient", "Sun", "Circ",
				"Sat", "Fid","Dul",
				"Lift\nBlinds", "Open\nBlinds", "Close\nBlinds"]