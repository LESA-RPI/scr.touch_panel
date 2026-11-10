"""Small, shared Tk primitives for the sharp panel design (pixel fonts)."""

import tkinter as tk
from design_tokens import SCALE
from panel_common import FONT

S = SCALE["panel"]


def font(size="text", bold=False):
    return (FONT, -size if isinstance(size, int) else -S[size],
            "bold" if bold else "normal")


def label(ui, parent, text="", size="text", muted=False, **options):
    return tk.Label(parent, text=text, font=font(size), bg=parent.cget("bg"),
                    fg=ui.muted if muted else ui.ink, anchor="w", justify="left",
                    bd=0, padx=0, pady=0, **options)


class ValueLabel(tk.Label):
    def __init__(self, ui, parent, variable, size="heading", suffix=""):
        super().__init__(parent, bg=parent.cget("bg"), fg=ui.ink, font=font(size), bd=0, padx=0, pady=0)
        def update(*args):
            self.configure(text=format(variable.get(), ",") + suffix)
        trace = variable.trace_add("write", update)
        self.bind("<Destroy>", lambda e: variable.trace_remove("write", trace) if e.widget == self else None)
        update()


class Button(tk.Button):
    def __init__(self, ui, parent, text, command, kind="secondary"):
        self.ui, self.kind = ui, kind
        self.blocked = False
        super().__init__(parent, text=text, command=lambda: None if self.blocked else command(), font=font(),
                         relief="flat", bd=0, highlightthickness=S["line"],
                         padx=S["space"], pady=0, takefocus=True)
        # Native Windows buttons ignore highlightbackground in some Tk builds.
        # Explicit one-pixel edges keep the shared border crisp on both platforms.
        self._edges = [tk.Frame(self, bd=0, height=S["line"], width=S["line"]) for _ in range(4)]
        self._edges[0].place(x=0, y=0, relwidth=1, height=S["line"])
        self._edges[1].place(x=0, rely=1, y=-S["line"], relwidth=1, height=S["line"])
        self._edges[2].place(x=0, y=0, width=S["line"], relheight=1)
        self._edges[3].place(relx=1, x=-S["line"], y=0, width=S["line"], relheight=1)
        for edge in self._edges:
            edge.bind("<ButtonRelease-1>", lambda e: self.invoke())
        self.style()
        self.bind("<FocusIn>", lambda e: self.configure(highlightcolor=ui.ink))
        self.bind("<FocusOut>", lambda e: self.configure(highlightcolor=self.cget("highlightbackground")))

    def style(self, selected=False, sending=False):
        ui = self.ui
        self.blocked = sending
        solid = selected or self.kind == "primary"
        bg = ui.ink if selected else ui.accent if solid else ui.bg
        fg = ui.bg if solid else ui.ink
        edge = bg if solid or self.kind == "link" else ui.border
        self.configure(bg=bg, fg=fg, activebackground=bg if solid else ui.pressed_colour(),
                       activeforeground=fg, disabledforeground=fg if sending else ui.muted,
                       highlightbackground=edge, highlightcolor=edge)
        for line in self._edges:
            line.configure(bg=edge)
        if sending:
            # Native disabled images are stippled. Keep the sending action solid
            # while its command wrapper rejects further touches and key presses.
            self.configure(state="normal")


def slot(ui, parent, text, command, kind="secondary", height=None, **pack):
    area = tk.Frame(parent, bg=parent.cget("bg"), height=height or S["tap"])
    area.pack(fill="x", **pack)
    area.pack_propagate(False)
    button = Button(ui, area, text, command, kind)
    button.pack(fill="both", expand=True)
    return button


class Card(tk.Frame):
    def __init__(self, ui, parent, **options):
        super().__init__(parent, bg=ui.surface, highlightthickness=S["line"],
                         highlightbackground=ui.border, **options)


class Segmented(tk.Frame):
    def __init__(self, ui, parent, choices, current, choose):
        super().__init__(parent, bg=ui.surface, height=S["tap"],
                         highlightthickness=S["line"], highlightbackground=ui.border)
        self.ui, self.choices = ui, choices
        self.pack_propagate(False)
        self.grid_propagate(False)
        self.buttons = []
        for index, (text, value) in enumerate(choices):
            self.columnconfigure(index, weight=1, uniform="segment")
            button = Button(ui, self, text, lambda v=value: choose(v), "link")
            button.grid(row=0, column=index, sticky="nsew", padx=4, pady=4)
            self.buttons.append(button)
        self.rowconfigure(0, weight=1)
        self.select(current)

    def select(self, current):
        for button, (_, value) in zip(self.buttons, self.choices):
            selected = value == current
            bg = self.ui.control if selected else self.ui.surface
            button.configure(bg=bg, fg=self.ui.ink if selected else self.ui.muted,
                             activebackground=bg, activeforeground=self.ui.ink,
                             highlightbackground=bg, highlightcolor=bg,
                             font=font("text", selected))
            for edge in button._edges:
                edge.configure(bg=bg)


class ListRow(Button):
    def __init__(self, ui, parent, text, command, selected=False, icon=None):
        super().__init__(ui, parent, text, command, "link")
        self.configure(anchor="w", wraplength=250, justify="left", padx=S["space"] // 2)
        self.style(selected=selected)
        self.configure(font=font("text", selected))
        if icon:
            self.configure(image=ui.icon(icon, ui.bg if selected else ui.ink, 28),
                           compound="left", text="  " + text, wraplength=230)


class PrefRow(tk.Frame):
    """A single current-value control; its sheet reads live state when opened."""
    def __init__(self, ui, parent, title, detail, value, command):
        super().__init__(parent, bg=ui.bg, height=98)
        self.pack_propagate(False)
        tk.Frame(self, bg=ui.border, height=S["line"]).pack(side="bottom", fill="x")
        button = Button(ui, self, value + "  ›", command, "link")
        button.configure(anchor="e", padx=0)
        button.place(relx=1, x=0, y=12, width=240, height=S["tap"], anchor="ne")
        label(ui, self, title).place(x=0, y=17)
        label(ui, self, detail, "small", True, wraplength=370).place(x=0, y=45)
        self.value_button = button


class Sheet(tk.Frame):
    def __init__(self, ui, title):
        super().__init__(ui.root, bg=ui.surface)
        self.place(x=0, y=0, relwidth=1, relheight=1)
        self.lift()
        panel = Card(ui, self)
        panel.place(relx=1, x=-S["pad"], y=S["pad"], width=680, relheight=1,
                    height=-2 * S["pad"], anchor="ne")
        heading = tk.Frame(panel, bg=ui.surface, height=S["tap"])
        heading.pack(fill="x", padx=S["pad"], pady=(S["space"], 0))
        heading.pack_propagate(False)
        close = Button(ui, heading, "Close ×", ui.close_sheet)
        close.pack(side="right", fill="y")
        label(ui, heading, title, "title").pack(side="left")
        self.content = tk.Frame(panel, bg=ui.surface)
        self.content.pack(fill="both", expand=True, padx=S["pad"], pady=S["space"])
        self.bind("<Escape>", lambda e: ui.close_sheet())
        close.focus_set()
