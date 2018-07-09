from Tkinter import *
from PIL import Image
from PIL import ImageTk
from button_functions import *

# Widget Classes

class FullHeightSlider(Scale):
	def __init__(self, app, range_, default, i, name, row = 0, col = 0):
		Scale.__init__(self, app, from_ = range_[0], to_ = range_[1], resolution = i)

		screen_width = app.winfo_screenwidth()
		sliderWidth = screen_width*0.03

		self.set(default)
		self.config(background='white', troughcolor='SlateGray2')
		self.config(highlightthickness = 0, highlightcolor = "white")
		self.config(width = sliderWidth, font = ("Helvetica", 20), label = name)
		self.grid(row=row, column=col, sticky="nsew", pady = 30, padx = 30)

class GridBasedButton(Button):
	def __init__(self, app, name, row = 0, col = 0):
		Button.__init__(self, app, text = name)
		self.config(font = ("Helvetica", 20))
		self.config(activeforeground='Blue')
		self.config(activebackground='SlateGray3')

		self.setOff()
		self.grid(row=row, column=col, sticky="nsew", padx = 50, pady = 10)

	def setOn(self):
		self.config(background='SlateGray2')
		self.config(foreground='Blue')

	def setOff(self):
		self.config(background='ivory3')
		self.config(foreground='Black')

# Helper Functions

def equalSections(frame, rows, cols, rowsName, colsName):
	for i in range(rows):
		frame.rowconfigure(i, weight = 1, uniform = rowsName)

	for i in range(cols):
		frame.columnconfigure(i, weight = 1, uniform = colsName)

class TouchPanel():
	def __init__(self):

		# Create and Divide Window
		# ========================

		window = Tk()
		window.attributes("-fullscreen", True)
		window.configure(background='white')

		window.rowconfigure(0, weight = 1, uniform = "margin")
		window.rowconfigure(1, weight = 7)
		window.rowconfigure(2, weight = 0, uniform = "margin")
		window.columnconfigure(0, weight = 2, uniform = "half")
		window.columnconfigure(1, weight = 2, uniform = "half")

		# Create and Localize Panes
		# =========================

		sliderPane = Frame(window, bg = 'white')
		buttonPane = Frame(window, bg = 'white')
		headerPane = Label(window, bg = 'white')
		footerPane = Label(window, bg = 'white')

		sliderPane.grid(row = 1, column = 0, sticky = "nsew")
		buttonPane.grid(row = 1, column = 1, sticky = "nsew")
		headerPane.grid(row = 0, column = 0, sticky = "nsew", columnspan = 2)
		footerPane.grid(row = 2, column = 0, sticky = "nsew", columnspan = 2)

		# Header Pane
		# ===========

		path = "lesa_banner.png"
		img = ImageTk.PhotoImage(Image.open(path))
		headerPane.config(image = img)

		# Slider Pane
		# ===========

		equalSections(sliderPane, 1, 2, "rows", "cols")
		cctSlider = FullHeightSlider(sliderPane, (10000, 1800) , 5000, 100, "CCT",       row = 0, col = 0)
		intSlider = FullHeightSlider(sliderPane, (100,   0),	 100,  1,   "Intensity", row = 0, col = 1)

		# Button Pane
		# ===========

		equalSections(buttonPane, 4, 2, "brows", "bcols")
		buttons = []
		button_names = ["Auto", "Off", "Set CCT", "Set Sources", "Bright", "Dulling", "Gradient", "Amber"]
		button_functions = [button_auto, button_off, button_cct, button_sources, button_bright, button_dulling, button_gradient, button_amber]
		for i in range(8):
			buttons.append(GridBasedButton(buttonPane, button_names[i], row = int(i/2), col = i%2))
		for i in range(8):
			buttons[i].config(command = lambda arg=i : button_functions[arg](buttons, arg))

		# Footer pane
		# ===========

		# footerPane.config(image = img)

		mainloop()

if __name__ == "__main__":
	TouchPanel()
	mainloop()
