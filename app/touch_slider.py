"""Flat touch slider with the same geometry and feedback in both themes."""
import tkinter as tk


def selected_value(fraction, start, end, step):
    low, high = sorted((start, end))
    raw = start + max(0, min(1, fraction)) * (end - start)
    return max(low, min(high, low + int((raw - low) / step + .5) * step))


class TouchSlider(tk.Canvas):
    def __init__(self, parent, variable, from_, to, resolution, orient, background,
                 track, accent, border, ink, length=200):
        vertical = orient == 'vertical'
        super().__init__(parent, width=48 if vertical else length,
                         height=length if vertical else 48, bg=background,
                         highlightthickness=0, bd=0, takefocus=True)
        self.variable, self.start, self.end, self.step = variable, from_, to, resolution
        self.vertical, self.track, self.accent = vertical, track, accent
        self.border, self.ink = border, ink
        self.command = self.on_start = self.on_end = lambda *args: None
        self.pressed = False
        self.items = None
        self.drawn = None
        self.trace = variable.trace_add('write', lambda *args: self.draw())
        self.bind('<Configure>', lambda event: self.draw())
        self.bind('<ButtonPress-1>', self.press)
        self.bind('<B1-Motion>', self.move)
        self.bind('<ButtonRelease-1>', self.release)
        self.bind('<FocusIn>', lambda event: self.draw())
        self.bind('<FocusOut>', lambda event: self.draw())
        self.bind('<KeyPress>', self.key)
        self.bind('<Destroy>', self.cleanup, add='+')

    def configure(self, cnf=None, **options):
        if 'command' in options:
            self.command = options.pop('command')
        if options.get('state') == self.cget('state'):
            options.pop('state')
        result = super().configure(cnf, **options)
        if options and hasattr(self, 'variable'):
            self.draw()
        return result

    config = configure

    def draw(self):
        width, height = self.winfo_width(), self.winfo_height()
        if min(width, height) < 2:
            return
        disabled = self.cget('state') == 'disabled'
        focused = self.focus_get() == self
        state = (width, height, self.variable.get(), disabled, focused, self.pressed,
                 self.track, self.accent, self.border, self.ink, self.cget('bg'))
        if state == self.drawn:
            return
        self.drawn = state
        if self.items is None:
            self.items = (self.create_line(0, 0, 0, 0, width=6, capstyle='round'),
                          self.create_line(0, 0, 0, 0, width=6, capstyle='round'),
                          self.create_rectangle(0, 0, 0, 0),
                          self.create_line(0, 0, 0, 0), self.create_line(0, 0, 0, 0))
        track, fill, thumb, *grips = self.items
        fraction = (self.variable.get() - self.start) / float(self.end - self.start)
        fraction = max(0, min(1, fraction))
        low, high = 26, max(27, (height if self.vertical else width) - 26)
        position = low + (high - low) * fraction
        cross = (width if self.vertical else height) / 2
        def coords(a, b):
            return (cross, a, cross, b) if self.vertical else (a, cross, b, cross)
        self.coords(track, *coords(low, high))
        self.itemconfigure(track, fill=self.track)
        self.coords(fill, *coords(low, position))
        self.itemconfigure(fill, fill=self.accent,
                           state='normal' if not disabled and position > low else 'hidden')
        x, y = (cross, position) if self.vertical else (position, cross)
        edge = self.border if disabled else self.accent if self.pressed or focused else self.ink
        # A 44px grip remains inside the 48px touch area, including at either endpoint.
        self.coords(thumb, x-22, y-18, x+22, y+18)
        self.itemconfigure(thumb, fill=self.track if not self.pressed or disabled else self.accent,
                           outline=edge, width=2 if self.pressed or focused else 1)
        grip = self.cget('bg') if self.pressed and not disabled else self.border if disabled else self.ink
        for item, offset in zip(grips, (-3, 3)):
            self.coords(item, x+offset, y-6, x+offset, y+6)
            self.itemconfigure(item, fill=grip)

    def set_pointer(self, event):
        length = self.winfo_height() if self.vertical else self.winfo_width()
        point = event.y if self.vertical else event.x
        value = selected_value((point-26)/float(max(1, length-52)), self.start, self.end, self.step)
        if value != self.variable.get():
            self.variable.set(value)
        self.command(str(value))

    def press(self, event):
        if self.cget('state') == 'disabled':
            return 'break'
        self.focus_set()
        self.pressed = True
        self.on_start()
        self.set_pointer(event)
        self.draw()

    def move(self, event):
        if self.pressed and self.cget('state') != 'disabled':
            self.set_pointer(event)

    def release(self, event):
        if self.pressed:
            self.pressed = False
            if self.cget('state') != 'disabled':
                self.set_pointer(event)
                self.on_end()
            self.draw()

    def key(self, event):
        if not self.winfo_ismapped() or self.cget('state') == 'disabled' or event.keysym not in ('Left','Right','Up','Down','Home','End'):
            return
        low, high = sorted((self.start, self.end))
        value = low if event.keysym == 'Home' else high if event.keysym == 'End' else (
            self.variable.get() + self.step * (1 if event.keysym in ('Right','Up') else -1))
        self.on_start()
        self.variable.set(max(low, min(high, value)))
        self.command(str(self.variable.get()))
        self.on_end()
        return 'break'

    def cleanup(self, event):
        if event.widget == self:
            self.variable.trace_remove('write', self.trace)
