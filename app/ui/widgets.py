"""画面の共通部品。

DropArea: ファイルをドラッグ＆ドロップで受け取る領域。
tkinterdnd2 が使える環境では D&D、使えなくても「参照」ボタンで選べる。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog

try:  # D&D が無い環境でも import 自体は失敗しないように
    from tkinterdnd2 import DND_FILES
except Exception:  # noqa: BLE001
    DND_FILES = None


class DropArea(tk.Frame):
    """ファイルを1つ受け取るドロップ領域。

    on_files(paths: list[str]) が、ドロップ／参照選択のたびに呼ばれる。
    """

    def __init__(
        self,
        master: tk.Misc,
        on_files,
        text: str = "ここにファイルをドラッグ＆ドロップ",
        button_text: str = "ファイルを選ぶ",
        filetypes=None,
        **kwargs,
    ):
        # 操作の中心だと一目で分かる、大きなドロップゾーン。
        super().__init__(
            master,
            bg="white",
            highlightbackground="#B8C7D9",
            highlightthickness=2,
            bd=0,
            cursor="hand2",
            padx=24,
            pady=18,
            **kwargs,
        )
        self._on_files = on_files
        self._base_text = text
        self._filetypes = filetypes or [
            ("名簿・文書", "*.csv *.xlsx *.txt"),
            ("すべてのファイル", "*.*"),
        ]

        formats: list[str] = []
        for _label, patterns in self._filetypes:
            for pattern in patterns.split():
                if pattern != "*.*":
                    value = pattern.replace("*", "").upper()
                    if value not in formats:
                        formats.append(value)

        self.eyebrow = tk.Label(
            self,
            text="DROP ZONE",
            font=("Yu Gothic UI", 9, "bold"),
            bg="white",
            fg="#2563EB",
        )
        self.eyebrow.pack(pady=(0, 3))

        self.icon_label = tk.Label(
            self,
            text="⇩",
            font=("Yu Gothic UI", 27, "bold"),
            bg="white",
            fg="#2563EB",
        )
        self.icon_label.pack()

        self.label = tk.Label(
            self,
            text=text,
            justify="center",
            font=("Yu Gothic UI", 13, "bold"),
            bg="white",
            fg="#172033",
        )
        self.label.pack(fill="x", pady=(2, 6))

        hint = "対応形式  " + "  /  ".join(formats) if formats else "ファイルを1つ選択"
        self.hint_label = tk.Label(
            self,
            text=hint,
            font=("Yu Gothic UI", 9),
            bg="white",
            fg="#68778C",
        )
        self.hint_label.pack(pady=(0, 12))

        # ttk.Button はWindowsの高DPI環境で日本語の描画位置が下へずれ、
        # 下端が切れる場合がある。ファイル選択だけはtk.Buttonを使い、
        # 文字の中央配置と上下余白を明示する。
        self.button = tk.Button(
            self,
            text=button_text,
            command=self._browse,
            font=("Yu Gothic UI", 11, "bold"),
            bg="#2563EB",
            fg="white",
            activebackground="#1D4ED8",
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=22,
            pady=10,
            anchor="center",
            cursor="hand2",
        )
        self.button.pack()

        for widget in (self, self.eyebrow, self.icon_label, self.label, self.hint_label):
            widget.bind("<Button-1>", lambda _event: self._browse())

        self._register_dnd()

    # --- ドラッグ＆ドロップ ---------------------------------------------
    def _register_dnd(self) -> None:
        if DND_FILES is None:
            return
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
            self.dnd_bind("<<DropEnter>>", lambda e: self._set_active(True))
            self.dnd_bind("<<DropLeave>>", lambda e: self._set_active(False))
        except Exception:  # noqa: BLE001 - D&D 未対応環境では参照ボタンだけ使う
            pass

    def _on_drop(self, event) -> None:
        self._set_active(False)
        try:
            paths = list(self.tk.splitlist(event.data))
        except Exception:  # noqa: BLE001
            paths = [event.data]
        paths = [p for p in paths if p]
        if paths:
            self._on_files(paths)

    def _set_active(self, active: bool) -> None:
        if active:
            background = "#EAF2FF"
            self.configure(highlightbackground="#2563EB", bg=background)
            self.eyebrow.configure(bg=background, fg="#1D4ED8")
            self.icon_label.configure(bg=background, fg="#1D4ED8", text="⇩")
        else:
            background = "white"
            self.configure(highlightbackground="#B8C7D9", bg=background)
            self.eyebrow.configure(bg=background, fg="#2563EB")
            self.icon_label.configure(bg=background, fg="#2563EB")
        self.label.configure(bg=background)
        self.hint_label.configure(bg=background)

    # --- 参照ボタン -----------------------------------------------------
    def _browse(self) -> None:
        paths = filedialog.askopenfilenames(
            title="ファイルを選ぶ",
            filetypes=self._filetypes,
        )
        if paths:
            self._on_files(list(paths))

    # --- 状態表示 -------------------------------------------------------
    def set_message(self, message: str) -> None:
        self.label.configure(text=message)
        self.icon_label.configure(text="✓", fg="#059669")
        self.eyebrow.configure(text="FILE READY", fg="#059669")

    def reset_message(self) -> None:
        self.label.configure(text=self._base_text)
        self.icon_label.configure(text="⇩", fg="#2563EB")
        self.eyebrow.configure(text="DROP ZONE", fg="#2563EB")
