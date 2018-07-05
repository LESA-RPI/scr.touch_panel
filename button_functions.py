def button_auto(buttons, i):
	setButtons(buttons, i)

def button_off(buttons, i):
	setButtons(buttons, i)

def button_cct(buttons, i):
	setButtons(buttons, i)

def button_sources(buttons, i):
	setButtons(buttons, i)

def button_bright(buttons, i):
	setButtons(buttons, i)

def button_dulling(buttons, i):
	setButtons(buttons, i)

def button_gradient(buttons, i):
	setButtons(buttons, i)

def button_amber(buttons, i):
	setButtons(buttons, i)

def setButtons(buttons, i):
	for j in range(len(buttons)):
		if j == i:
			buttons[j].setOn()
		else:
			buttons[j].setOff()