import sys, time, threading
sys.path.append("../catkin_ws/src/scr_control/scripts/blinds")
sys.path.append("../catkin_ws/src/scr_control/scripts/lights")
import SCR_blind_client as blind_control
import SCR_OctaLight_client as light_control

start = 0
stop = 10000

step = 190

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
	sun()

def button_circ(touch):
	circ()

def button_sat(touch):
	light_control.sources_all(21, 14, 4, 73, 22, 100, 22, 4)

def button_fid(touch):
	light_control.sources_all(39, 6, 25, 56, 57, 100, 3, 6)

def button_dul(touch):
	light_control.sources_all(41, 2, 25, 53, 38, 100, 2, 0)

def button_lift(touch):
	blind_control.lift_all(100)
	
def button_open(touch):
	blind_control.tilt_all(50)

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

def get_data(x):
	cct = 0
	lumens = 0
	x = float(x)
	cct = stop/2.0 - 0.00013 * (x - stop/2.0)**2
	lumens = 1900 - 0.00008 * (x - stop/2.0)**2
	return cct, lumens

def circ():
	for x in range(start, stop, step):
		x = float(x)
		cct, lumens = get_data(x)
		light_control.cct_all(int(cct),int(lumens))
		time.sleep(0.001)

def circ_one(x, y):
	for i in range(start, stop, step):
		i = float(i)
		cct, lumens = get_data(i)
		light_control.cct(x, y, int(cct),int(lumens))
		time.sleep(0.01)

def sun():
	row = 0
	lights = light_control.get_lights()
	lights.sort()
	cct, lumens, row = 0, 0, 0
	current_changing = []
	for light in lights:
		if(light[0] != row):
			current_changing = []
			row += 1
			time.sleep(0.2)
		current_changing.append(light)		
		for l in current_changing:
			t = threading.Thread(name = str(l), target = circ_one, args = (l[0], l[1]))
			t.start()


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