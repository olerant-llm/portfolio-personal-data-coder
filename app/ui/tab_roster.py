"""①名簿登録タブ。

流れ: ファイルをドロップ → 中身を読んでプレビュー → 内容を確認して「登録」。
登録するとマスターへ追加され、暗号化して保存される（既存IDは変えない）。
"""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, ttk

from app.core import roster, storage

_FIELD_LABELS = {
    "grade": "学年",
    "class": "組",
    "number": "番号",
    "name": "氏名",
}


class RosterTab(ttk.Frame):
    def __init__(self, master: tk.Misc, state):
        super().__init__(master, padding=20)
        self.state = state
        self._pending = None  # (headers, body, mapping, records)

        ttk.Label(self, text="名簿登録", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="名簿は暗号化してこのパソコンだけに保存します。",
            style="Info.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        # 上部: 現在の登録人数と、登録済み一覧への明確な入口
        summary_row = ttk.Frame(self)
        summary_row.pack(fill="x", pady=(0, 8))
        self.summary = ttk.Label(
            summary_row,
            text="",
            font=("Yu Gothic UI", 11, "bold"),
            foreground="#2563EB",
        )
        self.summary.pack(side="left", anchor="w")
        self.view_roster_btn = ttk.Button(
            summary_row,
            text="登録済み名簿を見る・削除する",
            command=self._open_roster_viewer,
        )
        self.view_roster_btn.pack(side="right")

        # ドロップ領域
        from app.ui.widgets import DropArea

        self.drop = DropArea(
            self,
            on_files=self._on_files,
            text="名簿ファイルをここにドロップ",
            button_text="名簿ファイルを選ぶ",
            filetypes=[
                ("名簿ファイル", "*.csv *.xlsx *.xlsm"),
                ("すべてのファイル", "*.*"),
            ],
        )
        self.drop.pack(fill="x", pady=(0, 10))

        # テンプレート保存ボタン
        self.template_btn = ttk.Button(
            self,
            text="登録用テンプレート（CSV）を保存",
            command=self._save_template,
            style="Secondary.TButton",
        )
        self.template_btn.pack(anchor="e", pady=(0, 10))

        # プレビュー表
        cols = ("status", "grade", "class", "number", "name", "code")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=8)
        for c, title, width in (
            ("status", "判定", 75),
            ("grade", "学年", 50),
            ("class", "組", 50),
            ("number", "番号", 50),
            ("name", "氏名", 140),
            ("code", "外部コード", 180),
        ):
            self.tree.heading(c, text=title)
            self.tree.column(c, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True, pady=(0, 8))

        self.info = ttk.Label(self, text="ファイルを読み込むと、ここに一覧が出ます。")
        self.info.pack(anchor="w", pady=(0, 8))

        # 登録ボタン
        self.register_btn = ttk.Button(
            self, text="この内容で登録する", command=self._register, state="disabled"
        )
        self.register_btn.pack(anchor="e")

        self.refresh_summary()

    # ------------------------------------------------------------------
    def refresh_summary(self) -> None:
        count = len(self.state.master.get("students", [])) if self.state.master else 0
        self.summary.configure(text=f"現在 {count} 人が登録されています")

    # ------------------------------------------------------------------
    def _open_roster_viewer(self) -> None:
        RegisteredRosterViewer(
            self.winfo_toplevel(), self.state, on_change=self.refresh_summary
        )

    # ------------------------------------------------------------------
    def _on_files(self, paths: list[str]) -> None:
        path = paths[0]
        try:
            headers, body = roster.read_table(path)
        except roster.RosterError as exc:
            messagebox.showerror("読み込みできません", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "読み込みできません", f"ファイルを読めませんでした。（{exc}）"
            )
            return

        mapping = roster.guess_columns(headers)
        # 学年・組・番号・氏名 が推測できなければ、列を選んでもらう
        if any(mapping.get(k) is None for k in ("grade", "class", "number", "name")):
            mapping = self._ask_columns(headers, mapping)
            if mapping is None:
                return

        try:
            start_seq = int(self.state.master.get("next_seq", 1))
            records = roster.build_student_records(
                headers, body, mapping, start_seq
            )
        except roster.RosterError as exc:
            messagebox.showerror("内容を確認してください", str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "内容を確認してください", f"名簿を整えられませんでした。（{exc}）"
            )
            return

        plan = roster.classify_student_records(self.state.master, records)
        self._pending = (headers, body, mapping, records, plan)
        self._show_preview(records, plan)

    # ------------------------------------------------------------------
    def _show_preview(self, records: list[dict], plan: dict) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        addition_ids = {r["id"] for r in plan["additions"]}
        duplicate_ids = {r["id"] for r in plan["duplicates"]}
        for r in records:
            if r["id"] in addition_ids:
                status = "新規"
            elif r["id"] in duplicate_ids:
                status = "登録済み"
            else:
                status = "要確認"
            self.tree.insert(
                "",
                "end",
                values=(
                    status,
                    r["grade"],
                    r["class"],
                    "" if r["number"] is None else r["number"],
                    r["name"],
                    r["class_code"] + "-" + r["external_id"],
                ),
            )
        new_count = len(plan["additions"])
        duplicate_count = len(plan["duplicates"])
        conflict_count = len(plan["conflicts"])
        parts = [f"新規 {new_count} 人"]
        if duplicate_count:
            parts.append(f"登録済み {duplicate_count} 人")
        if conflict_count:
            parts.append(f"要確認 {conflict_count} 人")
        message = "、".join(parts) + "です。"
        if conflict_count:
            message += " 同じ学年・組・番号に別の氏名があるため登録できません。"
        elif not new_count:
            message += " 新しく登録する人はいません。"
        else:
            message += " 内容を確認して登録してください。"
        self.info.configure(text=message)
        self.register_btn.configure(
            state="normal" if new_count and not conflict_count else "disabled"
        )
        self.drop.set_message("別の名簿を読み込む場合は、もう一度ドロップしてください。")

    # ------------------------------------------------------------------
    def _register(self) -> None:
        if not self._pending:
            return
        headers, body, mapping, records, plan = self._pending
        new_count = len(plan["additions"])
        existing = len(self.state.master.get("students", []))
        if existing:
            ok = messagebox.askyesno(
                "確認",
                f"今の名簿（{existing}人）に、{new_count}人を追加します。よろしいですか？",
            )
        else:
            ok = messagebox.askyesno(
                "確認", f"{new_count}人を新しく登録します。よろしいですか？"
            )
        if not ok:
            return

        before = copy.deepcopy(self.state.master)
        try:
            added = roster.add_to_master(self.state.master, headers, body, mapping)
            self.state.save()
        except Exception as exc:  # noqa: BLE001
            self.state.master = before
            messagebox.showerror("保存できません", f"登録を保存できませんでした。（{exc}）")
            return

        self._pending = None
        self.register_btn.configure(state="disabled")
        self.refresh_summary()
        self.info.configure(text=f"{len(added)}人を登録しました。")
        messagebox.showinfo("登録しました", f"{len(added)}人を登録しました。")

    # ------------------------------------------------------------------
    def _ask_columns(self, headers, guess) -> dict | None:
        """列を選んでもらう小さな画面を出す。キャンセルで None。"""
        dialog = tk.Toplevel(self)
        dialog.configure(background="#F4F5F7")
        dialog.title("列を選んでください")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        ttk.Label(
            dialog,
            text="見出しを自動で判別できませんでした。\nそれぞれがどの列かを選んでください。",
            padding=10,
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        options = [f"{i+1}列目: {h or '(空)'}" for i, h in enumerate(headers)]
        none_option = "（なし）"
        combos: dict[str, ttk.Combobox] = {}
        row = 1
        for field, label in _FIELD_LABELS.items():
            ttk.Label(dialog, text=label, padding=(10, 4)).grid(
                row=row, column=0, sticky="e"
            )
            cb = ttk.Combobox(
                dialog, values=[none_option] + options, state="readonly", width=28
            )
            g = guess.get(field)
            cb.current(0 if g is None else g + 1)
            cb.grid(row=row, column=1, padx=(0, 10), pady=2, sticky="w")
            combos[field] = cb
            row += 1

        result: dict = {}

        def on_ok():
            mapping: dict[str, int | None] = {}
            for field, cb in combos.items():
                idx = cb.current()
                mapping[field] = None if idx == 0 else idx - 1
            if any(
                mapping.get(k) is None
                for k in ("grade", "class", "number", "name")
            ):
                messagebox.showwarning(
                    "選び直してください",
                    "「学年」「組」「番号」「氏名」は必ず選んでください。",
                    parent=dialog,
                )
                return
            result.update(mapping)
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btns = ttk.Frame(dialog, padding=10)
        btns.grid(row=row, column=0, columnspan=2, sticky="e")
        ttk.Button(btns, text="決定", command=on_ok).pack(side="right", padx=4)
        ttk.Button(btns, text="やめる", command=on_cancel).pack(side="right")

        dialog.wait_window()
        return result or None

    def _save_template(self) -> None:
        """登録用のCSVテンプレート（Shift_JIS）を保存する。"""
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="テンプレートCSVの保存",
            filetypes=[("CSVファイル", "*.csv")],
            defaultextension=".csv",
            initialfile="名簿登録用テンプレート.csv",
            parent=self.winfo_toplevel()
        )
        if not path:
            return

        try:
            with open(path, mode="w", encoding="cp932", newline="") as f:
                import csv
                writer = csv.writer(f)
                writer.writerow(["学年", "組", "出席番号", "氏名"])
                writer.writerow(["3", "2", "1", "山田　太郎"])
                writer.writerow(["3", "2", "2", "佐藤　花子"])
            messagebox.showinfo("保存しました", f"テンプレートファイルを保存しました。\n{path}", parent=self.winfo_toplevel())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "保存できませんでした",
                f"ファイルの書き込みに失敗しました。\n（{exc}）",
                parent=self.winfo_toplevel()
            )


class RegisteredRosterViewer(tk.Toplevel):
    """登録済み名簿の絞り込み・複数選択・削除画面。"""

    _ALL = "すべて"

    def __init__(self, parent: tk.Misc, state, on_change):
        super().__init__(parent)
        self.state = state
        self.on_change = on_change
        self.title("登録済み名簿を見る・削除する")
        self.geometry("880x570")
        self.minsize(700, 420)
        self.transient(parent)
        self.configure(background="#F4F5F7")

        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="登録済み名簿", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text="学年・組・番号で絞り込めます。削除する行は複数選べます。",
            style="Info.TLabel",
        ).pack(anchor="w", pady=(2, 12))

        filters = ttk.LabelFrame(body, text="絞り込み", padding=10)
        filters.pack(fill="x", pady=(0, 10))
        self.grade_filter = self._make_filter(filters, "学年", 0)
        self.class_filter = self._make_filter(filters, "組", 2)
        self.number_filter = self._make_filter(filters, "番号", 4)
        ttk.Button(
            filters,
            text="絞り込みを解除",
            command=self._clear_filters,
            style="Secondary.TButton",
        ).grid(row=0, column=6, padx=(14, 0))

        table_frame = ttk.Frame(body)
        table_frame.pack(fill="both", expand=True)
        columns = ("grade", "class", "number", "name", "code")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        for column, title, width in (
            ("grade", "学年", 60),
            ("class", "組", 60),
            ("number", "番号", 60),
            ("name", "氏名", 190),
            ("code", "外部コード", 230),
        ):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="center")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        self.result_label = ttk.Label(body, text="")
        self.result_label.pack(anchor="w", pady=(8, 6))

        actions = ttk.Frame(body)
        actions.pack(fill="x")
        ttk.Button(
            actions,
            text="表示中をすべて選択",
            command=self._select_all_visible,
            style="Secondary.TButton",
        ).pack(side="left")
        ttk.Button(
            actions,
            text="選択を解除",
            command=lambda: self.tree.selection_remove(self.tree.selection()),
            style="Secondary.TButton",
        ).pack(side="left", padx=6)
        self.delete_btn = ttk.Button(
            actions,
            text="選択した人を削除",
            command=self._delete_selected,
            style="Danger.TButton",
        )
        self.delete_btn.pack(side="right")
        ttk.Button(actions, text="閉じる", command=self.destroy).pack(
            side="right", padx=6
        )

        self._populate_filters()
        self._refresh_table()

    def _make_filter(self, parent: ttk.Frame, label: str, column: int) -> ttk.Combobox:
        ttk.Label(parent, text=label).grid(row=0, column=column, padx=(0, 4))
        combo = ttk.Combobox(parent, state="readonly", width=8)
        combo.grid(row=0, column=column + 1, padx=(0, 12))
        combo.bind("<<ComboboxSelected>>", lambda _event: self._refresh_table())
        return combo

    def _populate_filters(self) -> None:
        students = self.state.master.get("students", [])
        for combo, field in (
            (self.grade_filter, "grade"),
            (self.class_filter, "class"),
            (self.number_filter, "number"),
        ):
            values = sorted({int(s[field]) for s in students})
            combo.configure(values=[self._ALL] + [str(v) for v in values])
            combo.set(self._ALL)

    def _selected_number(self, combo: ttk.Combobox) -> int | None:
        value = combo.get()
        return None if not value or value == self._ALL else int(value)

    def _refresh_table(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        students = roster.filter_students(
            self.state.master,
            grade=self._selected_number(self.grade_filter),
            class_no=self._selected_number(self.class_filter),
            number=self._selected_number(self.number_filter),
        )
        for student in students:
            self.tree.insert(
                "",
                "end",
                iid=student["id"],
                values=(
                    student["grade"],
                    student["class"],
                    student["number"],
                    student["name"],
                    f"{student['class_code']}-{student['external_id']}",
                ),
            )
        total = len(self.state.master.get("students", []))
        self.result_label.configure(text=f"{total} 人中 {len(students)} 人を表示しています。")
        self.delete_btn.configure(state="normal" if students else "disabled")

    def _clear_filters(self) -> None:
        for combo in (self.grade_filter, self.class_filter, self.number_filter):
            combo.set(self._ALL)
        self._refresh_table()

    def _select_all_visible(self) -> None:
        self.tree.selection_set(self.tree.get_children())

    def _delete_selected(self) -> None:
        selected = set(self.tree.selection())
        if not selected:
            messagebox.showwarning(
                "行を選んでください",
                "削除する人を一覧から選んでください。",
                parent=self,
            )
            return
        ok = messagebox.askyesno(
            "削除の確認",
            f"選択した {len(selected)} 人を登録済み名簿から削除します。\n"
            "必要になった場合は、同じ名簿を登録し直せば同じコードで戻せます。\n\n"
            "削除してよろしいですか？",
            icon="warning",
            parent=self,
        )
        if not ok:
            return

        before = copy.deepcopy(self.state.master)
        try:
            removed = roster.delete_students(self.state.master, selected)
            self.state.save()
        except Exception as exc:  # noqa: BLE001
            self.state.master = before
            messagebox.showerror(
                "削除できません",
                f"名簿を保存できなかったため、削除を取り消しました。（{exc}）",
                parent=self,
            )
            return

        self.on_change()
        self._populate_filters()
        self._refresh_table()
        messagebox.showinfo(
            "削除しました", f"{len(removed)} 人を削除しました。", parent=self
        )
