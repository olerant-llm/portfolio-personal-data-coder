"""③復元タブ。

流れ:
  1. コード化済みファイルをドロップ。
  2. 対応表で、コードを元の名前・年組に戻す（迷いは無いので確認は不要）。
  3. 「元名_restored.拡張子」で別保存し、保存先を表示。

元ファイルは書き換えず、必ず別ファイルに保存する。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.core import codec, fileio

_DECODE_FILETYPES = [
    ("対応ファイル", "*.txt *.csv *.xlsx *.md"),
    ("すべてのファイル", "*.*"),
]


class DecodeTab(ttk.Frame):
    def __init__(self, master: tk.Misc, state):
        super().__init__(master, padding=20)
        self.state = state

        ttk.Label(self, text="元に戻す", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="コードに置き換えたファイルを、元の名前や学年・組・番号に戻します。",
            style="Info.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        from app.ui.widgets import DropArea

        self.drop = DropArea(
            self,
            on_files=self._on_files,
            text="元に戻したいファイルをここにドロップ",
            button_text="コード化済みファイルを選ぶ",
            filetypes=_DECODE_FILETYPES,
        )
        self.drop.pack(fill="x", pady=(0, 10))

        self.info = ttk.Label(
            self,
            text="ファイルを読み込むと、自動で元に戻して別ファイルに保存します。",
            justify="left",
        )
        self.info.pack(anchor="w", pady=(6, 0))

    # ------------------------------------------------------------------
    def _has_students(self) -> bool:
        return bool(self.state.master and self.state.master.get("students"))

    # ------------------------------------------------------------------
    def _on_files(self, paths: list[str]) -> None:
        if not self._has_students():
            messagebox.showwarning(
                "先に名簿を登録してください",
                "対応表がまだありません。「① 名簿登録」で名簿を登録してください。",
            )
            return
        path = paths[0]
        try:
            doc = fileio.load(path)
        except fileio.FileIOError as exc:
            messagebox.showerror("読み込みできません", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "読み込みできません", f"ファイルを読めませんでした。（{exc}）"
            )
            return

        try:
            new_segments, report = codec.decode(doc.segments, self.state.master)
            out = fileio.save(doc, new_segments, "restored")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "保存できません", f"元に戻せませんでした。（{exc}）"
            )
            return

        info_lines = [f"保存先: {out}", f"元に戻した箇所: {report['replaced']} 件"]
        header_lines = [f"元に戻した箇所: {report['replaced']} 件"]
        if doc.note:
            info_lines.append(doc.note)
            header_lines.append(doc.note)
        if report["replaced"] == 0:
            no_hit = "戻せるコードが見つかりませんでした。ファイルを確認してください。"
            info_lines.append(no_hit)
            header_lines.append(no_hit)
        self.info.configure(text="\n".join(info_lines))
        self.drop.set_message("別のファイルを読み込む場合は、もう一度ドロップしてください。")

        # 保存先・件数はビューアー上部に統合し、ポップアップは出さない。
        # ビューアーが開けなくても保存は成功しているので、そのときだけ案内を出す。
        try:
            from app.ui import viewer

            viewer.open_viewer(self.winfo_toplevel(), out, doc.kind, header_lines)
        except Exception as exc:  # noqa: BLE001
            messagebox.showinfo(
                "元に戻しました",
                f"保存先: {out}\n（内容の表示は開けませんでした: {exc}）",
            )
