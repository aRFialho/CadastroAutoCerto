import customtkinter as ctk

class GlassCard(ctk.CTkFrame):
    def __init__(
        self,
        parent,
        corner_radius=16,
        fg_color=("#0f172a", "#0b1220"),
        border_color=("#23314d", "#23314d"),
        border_width=1,
        hover=True,
        hover_border_color=("#3b82f6", "#3b82f6"),
        hover_fg_color=("#111d36", "#0d162b"),
        **kwargs
    ):
        super().__init__(
            parent,
            corner_radius=corner_radius,
            fg_color=fg_color,
            border_color=border_color,
            border_width=border_width,
            **kwargs
        )

        self._hover_enabled = bool(hover)
        self._fg_default = fg_color
        self._border_default = border_color
        self._fg_hover = hover_fg_color
        self._border_hover = hover_border_color

        if self._hover_enabled:
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.after(50, self._bind_children_recursive)

    def _bind_children_recursive(self):
        for w in self.winfo_children():
            try:
                w.bind("<Enter>", self._on_enter, add="+")
                w.bind("<Leave>", self._on_leave, add="+")
            except Exception:
                pass

    def _on_enter(self, _evt=None):
        try:
            self.configure(fg_color=self._fg_hover, border_color=self._border_hover)
        except Exception:
            pass

    def _on_leave(self, _evt=None):
        try:
            self.configure(fg_color=self._fg_default, border_color=self._border_default)
        except Exception:
            pass