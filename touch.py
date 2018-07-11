from Tkinter import *
from PIL import Image
from PIL import ImageTk
from button_functions import *

# Widget Classes
# ==============

class FullHeightSlider(Scale):
	def __init__(self, app, range_, default, i, name, row = 0, col = 0):
		Scale.__init__(self, app, from_ = range_[0], to_ = range_[1], resolution = i)

		screen_width = app.winfo_screenwidth()
		sliderWidth = screen_width*0.03

		self.set(default)
		self.config(background='white', troughcolor='ivory3')
		self.config(highlightthickness = 0, highlightcolor = "white")
		self.config(width = sliderWidth, font = ("Helvetica", 20), label = name)
		self.grid(row=row, column=col, sticky="nsew", pady = 30, padx = 30)

class GridBasedButton(Button):
	def __init__(self, app, name, row = 0, col = 0):
		Button.__init__(self, app, text = name)
		self.config(font = ("Helvetica", 20))

		self.onColors =  ['SlateGray2', 'Blue']
		self.offColors = ['ivory3', 'Black']
		self.config(activebackground=self.offColors[0], activeforeground=self.offColors[1])
		self.config(background=self.offColors[0],       foreground=self.offColors[1])

		self.setOff()
		self.grid(row=row, column=col, sticky="nsew", padx = 50, pady = 10)

	def setOn(self):
		self.config(activebackground=self.onColors[0], activeforeground=self.onColors[1])
		self.config(background=self.onColors[0],       foreground=self.onColors[1])

	def setOff(self):
		self.config(activebackground=self.offColors[0], activeforeground=self.offColors[1])
		self.config(background=self.offColors[0],       foreground=self.offColors[1])

	def setColorScheme(self, scheme):
		if scheme == "green":
			self.onColors = ['OliveDrab1', 'green4']
		elif scheme == 'red':
			self.onColors = ['light salmon', 'red4']
		else:
			self.onColors = ['SlateGray2', 'Blue']
			self.offColors = ['ivory3', 'Black']
		self.config(activebackground=self.offColors[0], activeforeground=self.offColors[1])
		self.config(background=self.offColors[0],       foreground=self.offColors[1])

# Helper Functions
# ================

def equalSections(frame, rows, cols, rowsName, colsName):
	for i in range(rows):
		frame.rowconfigure(i, weight = 1, uniform = rowsName)

	for i in range(cols):
		frame.columnconfigure(i, weight = 1, uniform = colsName)

# Main Touch Panel class
# =====================

class TouchPanel():

	def __init__(self):


		# Member Variables / Settings
		# ===========================

		self.slidersActive = False

		# Create and Divide Window
		# ========================

		self.window = Tk()
		self.window.attributes("-fullscreen", True)
		self.window.configure(background='white')

		self.window.rowconfigure(0, weight = 1, uniform = "margin")
		self.window.rowconfigure(1, weight = 7)
		self.window.rowconfigure(2, weight = 0, uniform = "margin")
		self.window.columnconfigure(0, weight = 2)
		self.window.columnconfigure(1, weight = 3, uniform = "half")

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

		equalSections(self.sliderPane, 1, 2, "srows", "scols")
		self.cctSlider = FullHeightSlider(self.sliderPane, (10000, 1800) , 5000, 100, "CCT",       row = 0, col = 0)
		self.intSlider = FullHeightSlider(self.sliderPane, (100,   0),	 100,  1,   "Intensity", row = 0, col = 1)
		self.cctSlider.config(command = (lambda value, touch = self: slider_cct(touch, value)) )
		self.intSlider.config(command = (lambda value, touch = self: slider_int(touch, value)) )

		# Button Pane
		# ===========

		equalSections(self.buttonPane, 5, 3, "brows", "bcols")
		self.buttons = []
		for i in range(15):
			self.buttons.append(GridBasedButton(self.buttonPane, button_names[i], row = int(i/3), col = i%3))
		for i in range(15):
			self.buttons[i].config(command = lambda arg=i : pressButton(self, arg))

		# self.buttons[0].setColorScheme("green")
		self.buttons[1].setColorScheme("red")

		# Footer pane
		# ===========

		# equalSections(self.footerPane, 1, 3, "trows", "tcols")
		# self.footer = []
		# button_names = ["Lights", "Blinds", "HVAC"]
		# for i in range(3):
		#	self.footer.append(GridBasedButton(self.footerPane, button_names[i], row = 0, col = i))

		# self.footerPane.config(image = self.img)