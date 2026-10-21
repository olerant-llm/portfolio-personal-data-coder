"""②コード化タブ。

流れ:
  1. ファイルをドロップ（txt / CSV / Excel / Word / PDF）。
  2. 「何を・何箇所」置き換えるかのプレビューを表示。
  3. 同姓が複数で迷うものがあれば、どの人かを選んでもらう（要確認）。
  4. 「コード化する」で実行し、別ファイルに保存＋点検レポートを表示。

元ファイルは書き換えず、必ず「元名_coded.拡張子」で別保存する。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.core import codec, fileio

_ENCODE_FILETYPES = [
    ("対応ファイル", "*.txt *.csv *.xlsx *.docx *.pdf *.md"),
    ("すべてのファイル", "*.*"),
]


class EncodeTab(ttk.Frame):
    def __init__(self, master: tk.Misc, state):
        super().__init__(master, padding=20)
        self.state = state
        self._doc: fileio.Document | None = None
        self._preview: dict | None = None
        self._review_choices: dict = {}  # (seg, pos) -> (選択値, 確認項目)

        ttk.Label(self, text="コード化", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="名前や学年・組・番号を、推測しにくいコードへ置き換えます。",
            style="Info.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        from app.ui.widgets import DropArea

        self.drop = DropArea(
            self,
            on_files=self._on_files,
            text="コード化したいファイルをここにドロップ",
            button_text="ファイルを選ぶ",
            filetypes=_ENCODE_FILETYPES,
        )
        self.drop.pack(fill="x", pady=(0, 10))

        # プレビュー表（置換する対象と箇所数）
        ttk.Label(self, text="置き換える内容", style="SubHeader.TLabel").pack(
            anchor="w"
        )
        self.tree = ttk.Treeview(
            self, columns=("disp", "code", "count"), show="headings", height=6
        )
        for c, title, w in (
            ("disp", "元の表記", 220),
            ("code", "外部コード", 190),
            ("count", "箇所数", 70),
        ):
            self.tree.heading(c, text=title)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True, pady=(0, 6))

        # 要確認・点検メッセージ
        self.notice = ttk.Label(self, text="", foreground="#A30000", justify="left", font=("Yu Gothic UI", 10, "bold"))
        self.notice.pack(anchor="w", pady=(0, 4))

        # 要確認の選択エリア（同姓が複数のとき出す）
        self.review_frame = ttk.LabelFrame(
            self, text="確認が必要な箇所（意味を確認して選んでください）", padding=8
        )
        self.review_canvas = tk.Canvas(
            self.review_frame,
            height=160,
            background="#EEF3F8",
            highlightthickness=0,
            borderwidth=0,
        )
        self.review_scrollbar = ttk.Scrollbar(
            self.review_frame, orient="vertical", command=self.review_canvas.yview
        )
        self.review_canvas.configure(yscrollcommand=self.review_scrollbar.set)
        self.review_content = ttk.Frame(self.review_canvas)
        self._review_window = self.review_canvas.create_window(
            (0, 0), window=self.review_content, anchor="nw"
        )
        self.review_content.bind(
            "<Configure>",
            lambda _event: self.review_canvas.configure(
                scrollregion=self.review_canvas.bbox("all")
            ),
        )
        self.review_canvas.bind(
            "<Configure>",
            lambda event: self.review_canvas.itemconfigure(
                self._review_window, width=event.width
            ),
        )
        self.review_canvas.pack(side="left", fill="both", expand=True)
        self.review_scrollbar.pack(side="right", fill="y")
        # pack は必要時のみ

        # 実行ボタン
        self.run_btn = ttk.Button(
            self, text="この内容でコード化する", command=self._run, state="disabled"
        )
        self.run_btn.pack(anchor="e", pady=(6, 0))

        self.info = ttk.Label(
            self, text="ファイルを読み込むと、ここに置き換え内容が出ます。"
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
                "「① 名簿登録」で名簿を登録してから、コード化してください。",
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
            preview = codec.preview(doc.segments, self.state.master)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "うまくいきませんでした", f"内容を調べられませんでした。（{exc}）"
            )
            return

        self._doc = doc
        self._preview = preview
        self._show_preview(preview, doc)

    # ------------------------------------------------------------------
    def _show_preview(self, preview: dict, doc: fileio.Document) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in preview["replacements"]:
            self.tree.insert(
                "", "end", values=(r["display"], r["code"], r["count"])
            )

        # 点検メッセージ
        lines = []
        if doc.note:
            lines.append(doc.note)
        if preview["not_found"]:
            names = "、".join(preview["not_found"][:10])
            more = " ほか" if len(preview["not_found"]) > 10 else ""
            lines.append(f"名簿にあるのに見つからなかった名前: {names}{more}")
        self.notice.configure(text="\n".join(lines))

        self._build_review_ui(preview["reviews"])

        total = sum(r["count"] for r in preview["replacements"])
        self.info.configure(
            text=(
                f"置き換える箇所: {total} 件"
                + (
                    f" ／ 要確認: {len(preview['reviews'])} 件"
                    if preview["reviews"]
                    else ""
                )
                + "。内容を確認して実行してください。"
            )
        )
        self.run_btn.configure(state="normal")
        self.drop.set_message("別のファイルを読み込む場合は、もう一度ドロップしてください。")

    # ------------------------------------------------------------------
    def _build_review_ui(self, reviews: list[dict]) -> None:
        # 既存の中身を消す
        for child in self.review_content.winfo_children():
            child.destroy()
        self._review_choices = {}

        if not reviews:
            self.review_frame.pack_forget()
            return

        for row, rv in enumerate(reviews):
            key = (rv["seg"], rv["position"])
            ttk.Label(
                self.review_content, text=rv["context"], width=30
            ).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=2)
            if rv.get("review_kind") == "attribute":
                options = [
                    "（置き換えない）",
                    f"{rv['label']}として置き換える → {rv['code']}",
                ]
            else:
                options = ["（置き換えない）"] + [
                    f"{c['name']} → {c['code']}" for c in rv["candidates"]
                ]
            var = tk.StringVar(value=options[0])
            cb = ttk.Combobox(
                self.review_content,
                values=options,
                textvariable=var,
                state="readonly",
                width=28,
            )
            cb.grid(row=row, column=1, sticky="w", pady=2)
            self._review_choices[key] = (var, rv)

        self.review_canvas.configure(height=min(180, max(54, len(reviews) * 34)))
        self.review_content.update_idletasks()
        self.review_canvas.configure(scrollregion=self.review_canvas.bbox("all"))
        self.review_canvas.yview_moveto(0.0)
        self.review_frame.pack(fill="x", pady=(4, 4), before=self.run_btn)

    # ------------------------------------------------------------------
    def _collect_selections(self) -> dict:
        selections: dict = {}
        for key, (var, review) in self._review_choices.items():
            value = var.get()
            if review.get("review_kind") == "attribute":
                expected = f"{review['label']}として置き換える → {review['code']}"
                if value == expected:
                    selections[key] = codec.ATTRIBUTE_APPROVAL
                continue
            for c in review["candidates"]:
                if value == f"{c['name']} → {c['code']}":
                    selections[key] = c["id"]
                    break
        return selections

    # ------------------------------------------------------------------
    def _run(self) -> None:
        if not self._doc:
            return
        selections = self._collect_selections()
        try:
            new_segments, report = codec.apply(
                self._doc.segments, self.state.master, selections=selections
            )
            out = fileio.save(self._doc, new_segments, "coded")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "保存できません", f"コード化を保存できませんでした。（{exc}）"
            )
            return

        msg_lines = [
            f"保存先: {out}",
            f"置き換えた箇所: {report['replaced']} 件",
        ]
        if report["review_total"]:
            msg_lines.append(
                f"要確認: {report['review_total']} 件"
                f"（うち {report['review_resolved']} 件を置き換え）"
            )
        if report["not_found"]:
            msg_lines.append(
                "見つからなかった名前: " + "、".join(report["not_found"][:10])
            )
        self.info.configure(text="\n".join(msg_lines))
        messagebox.showinfo("コード化しました", "\n".join(msg_lines))
