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

# Main Touchpanel class

class TouchPanel():

	def __init__(self):

		# Create and Divide Window
		# ========================

		self.window = Tk()
		self.window.attributes("-fullscreen", True)
		self.window.configure(background='white')

		self.window.rowconfigure(0, weight = 1, uniform = "margin")
		self.window.rowconfigure(1, weight = 7)
		self.window.rowconfigure(2, weight = 0, uniform = "margin")
		self.window.columnconfigure(0, weight = 2, uniform = "half")
		self.window.columnconfigure(1, weight = 2, uniform = "half")

		# Create and Localize Panes
		# =========================

		self.sliderPane = Frame(self.window, bg = 'white')
		self.buttonPane = Frame(self.window, bg = 'white')
		self.headerPane = Label(self.window, bg = 'white')
		self.footerPane = Label(self.window, bg = 'white')

		self.sliderPane.grid(row = 1, column = 0, sticky = "nsew")
		self.buttonPane.grid(row = 1, column = 1, sticky = "nsew")
		self.headerPane.grid(row = 0, column = 0, sticky = "nsew", columnspan = 2)
		self.footerPane.grid(row = 2, column = 0, sticky = "nsew", columnspan = 2)

		# Header Pane
		# ===========

		path = "lesa_banner.png"
		self.img = ImageTk.PhotoImage(Image.open(path))
		self.headerPane.config(image = self.img)

		# Slider Pane
		# ===========

		equalSections(self.sliderPane, 1, 2, "rows", "cols")
		self.cctSlider = FullHeightSlider(self.sliderPane, (10000, 1800) , 5000, 100, "CCT",       row = 0, col = 0)
		self.intSlider = FullHeightSlider(self.sliderPane, (100,   0),	 100,  1,   "Intensity", row = 0, col = 1)
		self.cctSlider.config(command = (lambda value, name = self.intSlider: slider_cct(name, value)) )
		self.intSlider.config(command = (lambda value, name = self.cctSlider: slider_int(name, value)) )

		# Button Pane
		# ===========

		equalSections(self.buttonPane, 4, 2, "brows", "bcols")
		self.buttons = []
		button_names = ["Auto", "Off", "Set CCT", "Set Sources", "Bright", "Dulling", "Open Blinds", "Close Blinds"]
		for i in range(8):
			self.buttons.append(GridBasedButton(self.buttonPane, button_names[i], row = int(i/2), col = i%2))
		for i in range(8):
			self.buttons[i].config(command = lambda arg=i : pressButton(self.buttons, arg))

		# Footer pane
		# ===========

		# self.footerPane.config(image = self.img)