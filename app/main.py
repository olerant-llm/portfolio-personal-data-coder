"""個人情報コード化ツールの起動処理。

流れ:
  1. マスター（対応表）が無ければ「はじめての設定」でパスワードを2回入力。
  2. 既にあればパスワードを入力して照合。誤りは「パスワードが違います」だけ表示。
  3. 3つのタブ（名簿登録／コード化／復元）を持つメインウィンドウを開く。

すべてこのパソコンの中だけで完結し、ネットには何も送信しない。
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

# このファイル単体でも実行できるよう、プロジェクト直下を import パスに入れる
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.core import roster, storage  # noqa: E402

APP_TITLE = "個人情報コード化ツール"

COLOR_NAVY = "#10233F"
COLOR_PRIMARY = "#2563EB"
COLOR_BG = "#EEF3F8"
COLOR_TEXT = "#172033"


def _base_dir() -> Path:
    """データ保存先の基準フォルダを決める。

    - exe 化して動いているとき（PyInstaller の sys.frozen）は
      「exe のあるフォルダ」を基準にする。
      ※ onefile 実行では __file__ が一時展開フォルダを指し、終了時に
        消えてしまうため、その中に data/ を作るとマスターが失われる。
    - 通常の Python 実行時はこれまで通りプロジェクト直下を基準にする。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _PROJECT_ROOT


DATA_DIR = _base_dir() / "data"
MASTER_PATH = DATA_DIR / "master.enc"


# ---------------------------------------------------------------------------
# アプリの状態（タブ間で共有）
# ---------------------------------------------------------------------------
class AppState:
    def __init__(self, data_dir: Path, password: str, master: dict):
        self.data_dir = Path(data_dir)
        self.master_path = self.data_dir / "master.enc"
        self.password = password
        self.master = master

    def save(self) -> None:
        """今のマスターを暗号化して保存する。"""
        storage.save_master(self.master, self.password, self.master_path)


# ---------------------------------------------------------------------------
# 画面づくり
# ---------------------------------------------------------------------------
def make_root() -> tk.Tk:
    """D&D 対応のルートウィンドウを作る（未対応環境では通常の Tk）。"""
    try:
        from tkinterdnd2 import TkinterDnD

        root = TkinterDnD.Tk()
    except Exception:  # noqa: BLE001
        root = tk.Tk()
    root.title(APP_TITLE)
    root.geometry("900x700")
    root.minsize(780, 600)
    root.configure(background=COLOR_BG)
    return root


class MainWindow:
    """3タブのメインウィンドウ。root と state を受け取って組み立てる。"""

    def __init__(self, root: tk.Tk, state: AppState):
        self.root = root
        self.state = state

        header = tk.Frame(root, background=COLOR_NAVY, padx=24, pady=18)
        header.pack(fill="x")

        brand = tk.Frame(header, background=COLOR_NAVY)
        brand.pack(side="left", fill="x", expand=True)
        tk.Label(
            brand,
            text=APP_TITLE,
            font=("Yu Gothic UI", 19, "bold"),
            background=COLOR_NAVY,
            foreground="white",
        ).pack(anchor="w")
        tk.Label(
            brand,
            text="名前・学年・組・番号を、推測しにくいコードへ",
            font=("Yu Gothic UI", 10),
            background=COLOR_NAVY,
            foreground="#B9C8DE",
        ).pack(anchor="w", pady=(3, 0))

        safety = tk.Frame(
            header,
            background="#193453",
            highlightbackground="#31506F",
            highlightthickness=1,
            padx=13,
            pady=8,
        )
        safety.pack(side="right", padx=(16, 0))
        tk.Label(
            safety,
            text="●  オフライン処理",
            font=("Yu Gothic UI", 10, "bold"),
            background="#193453",
            foreground="#6EE7B7",
        ).pack()
        tk.Label(
            safety,
            text="ネット送信なし",
            font=("Yu Gothic UI", 9),
            background="#193453",
            foreground="#C8D5E5",
        ).pack(pady=(2, 0))

        notebook = ttk.Notebook(root, style="Tool.TNotebook")
        notebook.pack(fill="both", expand=True, padx=18, pady=(14, 18))

        # 遅延 import（起動時の負荷とテストしやすさのため）
        from app.ui.tab_roster import RosterTab
        from app.ui.tab_encode import EncodeTab
        from app.ui.tab_decode import DecodeTab

        self.tab_roster = RosterTab(notebook, state)
        self.tab_encode = EncodeTab(notebook, state)
        self.tab_decode = DecodeTab(notebook, state)

        notebook.add(self.tab_roster, text="1   名簿登録")
        notebook.add(self.tab_encode, text="2   コード化")
        notebook.add(self.tab_decode, text="3   元に戻す")


# ---------------------------------------------------------------------------
# 高DPIおよびUIスタイル設定
# ---------------------------------------------------------------------------
def enable_dpi_awareness() -> None:
    """Windowsの高DPI設定を有効化し、フォントがぼやけるのを防ぐ。"""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_SYSTEM_DPI_AWARE
        except Exception:
            try:
                import ctypes
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def configure_styles() -> None:
    """アプリ全体の統一したモダンなデザインスタイルを設定。"""
    style = ttk.Style()
    style.theme_use("clam")

    font_family = "Yu Gothic UI"
    bg_color = COLOR_BG
    fg_color = COLOR_TEXT
    primary_color = COLOR_PRIMARY
    hover_color = "#1D4ED8"
    accent_color = "#D5DEE9"

    # 基本設定
    style.configure(".", font=(font_family, 10), background=bg_color, foreground=fg_color)
    style.configure("TFrame", background=bg_color)
    style.configure("TLabel", background=bg_color, foreground=fg_color)

    # 特殊なラベル
    style.configure(
        "Header.TLabel", font=(font_family, 16, "bold"), foreground=COLOR_NAVY
    )
    style.configure("SubHeader.TLabel", font=(font_family, 11, "bold"), foreground=fg_color)
    style.configure("Info.TLabel", font=(font_family, 10), foreground="#666677")

    # ボタン
    style.configure(
        "TButton",
        font=(font_family, 10, "bold"),
        background=primary_color,
        foreground="white",
        borderwidth=0,
        focusthickness=0,
        padding=(18, 8),
    )
    style.map(
        "TButton",
        background=[("active", hover_color), ("pressed", "#1E40AF"), ("disabled", "#CBD5E1")],
        foreground=[("disabled", "#7C8798")],
    )

    style.configure(
        "Secondary.TButton",
        font=(font_family, 10, "bold"),
        background="#E6EDF6",
        foreground=COLOR_NAVY,
        borderwidth=0,
        padding=(15, 7),
    )
    style.map(
        "Secondary.TButton",
        background=[("active", "#D8E4F2"), ("pressed", "#C9D8E9")],
    )

    style.configure(
        "Danger.TButton",
        font=(font_family, 10, "bold"),
        background="#B42318",
        foreground="white",
        borderwidth=0,
        padding=(15, 7),
    )
    style.map(
        "Danger.TButton",
        background=[
            ("active", "#912018"),
            ("pressed", "#7A1B14"),
            ("disabled", "#D5A7A3"),
        ],
        foreground=[("disabled", "#F8E8E7")],
    )

    # タブ (Notebook)
    style.configure("Tool.TNotebook", background=bg_color, borderwidth=0)
    style.configure(
        "Tool.TNotebook.Tab",
        font=(font_family, 11, "bold"),
        padding=(24, 11),
        background="#DDE6F0",
        foreground=fg_color,
        borderwidth=0,
    )
    style.map(
        "Tool.TNotebook.Tab",
        background=[("selected", "white"), ("active", "#E7EEF6")],
        foreground=[("selected", primary_color)],
    )

    # セパレータ
    style.configure("TSeparator", background=accent_color)

    # テーブル (Treeview)
    style.configure(
        "Treeview",
        font=(font_family, 10),
        background="white",
        fieldbackground="white",
        foreground=fg_color,
        rowheight=29,
        borderwidth=1,
        relief="solid",
    )
    style.configure(
        "Treeview.Heading",
        font=(font_family, 10, "bold"),
        background="#E7EDF4",
        foreground=fg_color,
        relief="flat",
        borderwidth=1,
    )
    style.map(
        "Treeview",
        background=[("selected", "#DBEAFE")],
        foreground=[("selected", fg_color)],
    )

    # コンボボックス
    style.configure("TCombobox", arrowsize=12, padding=4)
    style.configure("TEntry", padding=7, fieldbackground="white")
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", "white")],
        selectbackground=[("readonly", primary_color)],
        selectforeground=[("readonly", "white")],
    )

    # ラベルフレーム
    style.configure("TLabelframe", background="white", borderwidth=1, relief="solid")
    style.configure(
        "TLabelframe.Label",
        font=(font_family, 10, "bold"),
        background="white",
        foreground=primary_color,
    )

    # ログインカード用のスタイル
    style.configure("Card.TFrame", background="white", bordercolor="#D6E0EA")
    style.configure("CardLabel.TLabel", background="white", foreground=fg_color)
    style.configure(
        "CardSubLabel.TLabel",
        background="white",
        foreground="#5E6C80",
        font=(font_family, 9),
    )


# ---------------------------------------------------------------------------
# ログイン・パスワード設定パネル
# ---------------------------------------------------------------------------
class LoginPanel(ttk.Frame):
    """メインウィンドウ内に埋め込み表示する、美しいログインおよび初回設定パネル。"""

    def __init__(self, master: tk.Tk, master_path: Path, on_success):
        super().__init__(master, padding=24)
        self.master_window = master
        self.master_path = master_path
        self.on_success = on_success
        self.is_new = not storage.master_exists(master_path)

        # 中央配置のためのグリッド設定
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)

        # 白いコンテナ（カード風）
        card = ttk.Frame(
            self, style="Card.TFrame", padding=38, borderwidth=1, relief="solid"
        )
        card.grid(row=1, column=1, sticky="nsew")

        # タイトルと説明
        title_label = ttk.Label(
            card,
            text=APP_TITLE,
            font=("Yu Gothic UI", 22, "bold"),
            foreground=COLOR_NAVY,
            style="CardLabel.TLabel",
        )
        title_label.pack(pady=(0, 4))

        desc_label = ttk.Label(
            card,
            text="児童生徒の名前・年組を、推測しにくいコードへ変換します。\n"
            "すべてこのパソコン内で処理し、ネットには送信しません。",
            justify="center",
            style="CardSubLabel.TLabel",
        )
        desc_label.pack(pady=(0, 24))

        # 入力フォーム部分
        form = ttk.Frame(card, style="Card.TFrame")
        form.pack(fill="x", pady=8)

        if self.is_new:
            prompt_text = "【はじめての設定】\n名簿を守るためのパスワードを決めてください。\n※このパスワードを忘れると、二度と元に戻せません。"
            prompt_color = "#E06B26"  # 注意を惹くオレンジ
        else:
            prompt_text = "名簿のパスワードを入力してください。"
            prompt_color = "#2D323F"

        prompt_label = ttk.Label(
            form,
            text=prompt_text,
            justify="center",
            foreground=prompt_color,
            style="CardLabel.TLabel",
            font=("Yu Gothic UI", 11, "bold"),
        )
        prompt_label.pack(pady=(0, 16))

        # パスワード入力欄1
        input_frame1 = ttk.Frame(form, style="Card.TFrame")
        input_frame1.pack(fill="x", pady=4)
        ttk.Label(
            input_frame1, text="パスワード:", width=10, anchor="e", style="CardLabel.TLabel"
        ).pack(side="left")
        self.entry1 = ttk.Entry(input_frame1, show="*", width=24, font=("Yu Gothic UI", 11))
        self.entry1.pack(side="left", padx=(8, 0), fill="x", expand=True)

        self.entry2 = None
        if self.is_new:
            # パスワード入力欄2
            input_frame2 = ttk.Frame(form, style="Card.TFrame")
            input_frame2.pack(fill="x", pady=4)
            ttk.Label(
                input_frame2, text="もう一度:", width=10, anchor="e", style="CardLabel.TLabel"
            ).pack(side="left")
            self.entry2 = ttk.Entry(input_frame2, show="*", width=24, font=("Yu Gothic UI", 11))
            self.entry2.pack(side="left", padx=(8, 0), fill="x", expand=True)

        # エラーメッセージ表示エリア
        self.error_label = ttk.Label(
            card,
            text="",
            foreground="#A30000",
            justify="center",
            style="CardLabel.TLabel",
            font=("Yu Gothic UI", 10, "bold"),
        )
        self.error_label.pack(pady=(8, 0))

        # アクションボタン
        btn_text = "設定して開始" if self.is_new else "ログイン"
        btn = ttk.Button(card, text=btn_text, command=self._submit, width=16)
        btn.pack(pady=(16, 0))

        # Returnキーでの送信設定
        self.entry1.bind("<Return>", lambda e: self._submit())
        if self.entry2:
            self.entry2.bind("<Return>", lambda e: self._submit())
            self.entry1.focus_set()
        else:
            self.entry1.focus_set()

    def _show_error(self, message: str) -> None:
        self.error_label.configure(text=message)

    def _submit(self) -> None:
        self._show_error("")  # エラーをクリア
        p1 = self.entry1.get()
        if not p1:
            self._show_error("パスワードを入力してください。")
            return

        if self.is_new:
            p2 = self.entry2.get()
            if p1 != p2:
                self._show_error("パスワードが一致しません。")
                return

            try:
                master = roster.new_master()
                storage.save_master(master, p1, self.master_path)
                self.on_success(p1, master)
            except Exception as exc:  # noqa: BLE001
                self._show_error(f"マスターの作成に失敗しました: {exc}")
        else:
            try:
                master = storage.load_master(p1, self.master_path)
                self.on_success(p1, master)
            except storage.WrongPasswordError:
                self._show_error("パスワードが違います。")
            except storage.StorageError as exc:
                self._show_error(f"データの復号に失敗しました:\n{exc}")
            except Exception as exc:  # noqa: BLE001
                self._show_error(f"予期しないエラーが発生しました:\n{exc}")


# ---------------------------------------------------------------------------
# エントリポイント
# ---------------------------------------------------------------------------
def main() -> None:
    # 1. 高DPI対応の実行
    enable_dpi_awareness()

    # 2. メインウィンドウの作成
    root = make_root()

    # 3. 共通デザインスタイルの適用
    configure_styles()

    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        def login_success(password: str, master: dict) -> None:
            # 旧式の更新と保存が成功してから画面を切り替える。
            state = AppState(DATA_DIR, password, master)
            if roster.ensure_current_master(master):
                state.save()
            login_panel.destroy()
            MainWindow(root, state)

        # ログイン画面を配置
        login_panel = LoginPanel(root, MASTER_PATH, on_success=login_success)
        login_panel.pack(fill="both", expand=True)

        root.mainloop()
    except Exception as exc:  # noqa: BLE001 - 最後の砦。平易に伝える
        try:
            messagebox.showerror("エラー", f"予期しない問題が起きました。（{exc}）")
        finally:
            try:
                root.destroy()
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    main()
