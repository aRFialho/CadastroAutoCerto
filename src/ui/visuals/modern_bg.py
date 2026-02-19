from __future__ import annotations
import tkinter as tk
import random
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFilter, ImageChops
import customtkinter as ctk

@dataclass
class BgColors:
    base1: tuple[int,int,int] = (10, 14, 22)      # topo
    base2: tuple[int,int,int] = (8, 10, 14)       # base
    accent: tuple[int,int,int] = (46, 130, 255)   # azul
    accent2: tuple[int,int,int] = (160, 90, 255)  # roxo

class ModernBackground:
    """
    Fundo com:
      - gradiente (PIL) + noise leve
      - 2 camadas de "raios" com transparência (PIL)
      - flash ocasional (muito suave)
    Render: Canvas + CTkImage (leve, sem rotação por frame).
    """
    def __init__(self, root: ctk.CTk, colors: BgColors | None = None):
        self.root = root
        self.colors = colors or BgColors()

        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0, bg="#070b12")
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.canvas.lower()  # fica atrás de tudo

        self._w = 1200
        self._h = 800

        self._base_img = None
        self._ray1 = None
        self._ray2 = None

        self._base_ctk = None
        self._ray1_ctk = None
        self._ray2_ctk = None
        self._flash_ctk = None

        self._base_id = None
        self._ray1_id = None
        self._ray2_id = None
        self._flash_id = None

        self._t = 0
        self._flash = 0.0
        self._flash_target = 0.0

        self.root.bind("<Configure>", self._on_resize)
        self._rebuild(self._w, self._h)
        self._tick()

    def _on_resize(self, _evt=None):
        w = max(800, int(self.root.winfo_width() or 800))
        h = max(600, int(self.root.winfo_height() or 600))
        if abs(w - self._w) > 60 or abs(h - self._h) > 60:
            self._rebuild(w, h)

    def _rebuild(self, w: int, h: int):
        self._base_tk = ImageTk.PhotoImage(self._base_img)
        self._ray1_tk = ImageTk.PhotoImage(self._ray1)
        self._ray2_tk = ImageTk.PhotoImage(self._ray2)
        self._flash_img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        self._flash_tk = ImageTk.PhotoImage(self._flash_img)

        self.canvas.delete("all")
        self._base_id = self.canvas.create_image(0, 0, anchor="nw", image=self._base_tk)
        self._ray1_id = self.canvas.create_image(0, 0, anchor="nw", image=self._ray1_tk)
        self._ray2_id = self.canvas.create_image(0, 0, anchor="nw", image=self._ray2_tk)
        self._flash_id = self.canvas.create_image(0, 0, anchor="nw", image=self._flash_tk)

    def _make_gradient(self, w: int, h: int) -> Image.Image:
        img = Image.new("RGB", (w, h), self.colors.base2)
        draw = ImageDraw.Draw(img)

        # gradiente vertical simples
        for y in range(h):
            t = y / max(1, h - 1)
            r = int(self.colors.base1[0] * (1 - t) + self.colors.base2[0] * t)
            g = int(self.colors.base1[1] * (1 - t) + self.colors.base2[1] * t)
            b = int(self.colors.base1[2] * (1 - t) + self.colors.base2[2] * t)
            draw.line([(0, y), (w, y)], fill=(r, g, b))

        # noise leve (barato)
        noise = Image.effect_noise((w, h), 12).convert("L")
        noise = noise.point(lambda p: int(p * 0.22))
        img = Image.merge("RGB", (
            ImageChops.add(img.getchannel("R"), noise),
            ImageChops.add(img.getchannel("G"), noise),
            ImageChops.add(img.getchannel("B"), noise),
        ))
        return img

    def _make_rays(self, w: int, h: int, color: tuple[int,int,int], intensity: float, seed: int) -> Image.Image:
        random.seed(seed)
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)

        # raios diagonais largos (poucos, pra ficar leve)
        n = 7
        for i in range(n):
            x = random.randint(-w//3, w)
            width = random.randint(140, 260)
            alpha = int(255 * intensity * random.uniform(0.65, 1.05))
            d.polygon([(x, -50), (x + width, -50), (x + width + 260, h + 50), (x + 260, h + 50)],
                      fill=(color[0], color[1], color[2], alpha))

        overlay = overlay.filter(ImageFilter.GaussianBlur(radius=18))
        return overlay

    def _tick(self):
        self._t += 1

        # movimento sutil dos raios (só translate → barato)
        off1 = int((self._t * 0.6) % 220) - 110
        off2 = int((self._t * 0.35) % 260) - 130
        self.canvas.coords(self._ray1_id, off1, 0)
        self.canvas.coords(self._ray2_id, -off2, 0)

        # flash ocasional, bem suave e raro
        if self._t % 180 == 0 and random.random() < 0.35:
            self._flash_target = random.uniform(0.06, 0.12)

        # easing do flash
        self._flash += (self._flash_target - self._flash) * 0.12
        self._flash_target *= 0.92

        # atualiza alpha do flash (sem recriar tudo)
        a = int(255 * self._flash)
        self._flash_img = Image.new("RGBA", (self._w, self._h), (255, 255, 255, a))
        self._flash_tk = ImageTk.PhotoImage(self._flash_img)
        self.canvas.itemconfig(self._flash_id, image=self._flash_tk)

        self.root.after(33, self._tick)  # ~30 FPS, leve