"""置換ロジック（コード化 / 復元）。

コード化の対象と優先順位（長いものから置換する）:
  1. 氏名の完全一致（「姓 名」「姓　名」「姓名」＝スペース有無・全角半角）
  2. 姓のみ一致（同姓が複数いる場合は自動で置換せず「要確認」に回す）
  3. 年組表記（「3年2組」「３年２組」は自動、「3-2」などは確認後）
  4. 学年・組・番号の単独表記

置換先:
  - 生徒名 → K526-KUE5V（4文字の年組コード + 5文字の生徒コード）
  - 年組・単独表記 → 4文字コード

「長いものから」「重ならない一回走査」で置換するため、
「田中」を置換して「田中村」を壊すような部分一致の誤りが起きにくい。
姓のみ一致には前後が漢字なら置換しない、という安全策も入れている。

このモジュールは複数の文字列（segments）をまとめて扱える。
  - txt / md … segments = [本文全体]
  - csv / xlsx … segments = 全セルの文字列

プレビュー（何を何箇所置換するか）と、確定実行を別々の関数にしている。
"""

from __future__ import annotations

from app.core import roster

# 全角数字 ↔ 半角数字
_ZEN2HAN_DIGIT = str.maketrans("０１２３４５６７８９", "0123456789")
_HAN2ZEN_DIGIT = str.maketrans("0123456789", "０１２３４５６７８９")

# 曖昧な単独表記を、確認画面で「置き換える」と決めたことを表す値。
ATTRIBUTE_APPROVAL = "__attribute_replace__"


def _student_code(student: dict) -> str:
    """文書に出すクラスコード＋生徒コードを返す。"""
    return f"{student['class_code']}-{student['external_id']}"


# ---------------------------------------------------------------------------
# 小さな判定ヘルパー
# ---------------------------------------------------------------------------
def _is_kanji(ch: str) -> bool:
    """漢字（CJK統合漢字など）かどうか。空文字は False。"""
    if not ch:
        return False
    o = ord(ch)
    return (
        0x3400 <= o <= 0x9FFF  # CJK統合漢字（拡張A含む）
        or 0xF900 <= o <= 0xFAFF  # 互換漢字
        or o == 0x3005  # 々（繰り返し記号）
    )


def _is_digit(ch: str) -> bool:
    """数字（全角半角どちらも）かどうか。空文字は False。"""
    return bool(ch) and ch.isdigit()


def _is_ascii_alnum(ch: str) -> bool:
    """半角英数字かどうか（コードの部分一致防止に使う）。"""
    return bool(ch) and ch.isascii() and ch.isalnum()


# ---------------------------------------------------------------------------
# コード化用のパターン作り
# ---------------------------------------------------------------------------
def _student_name_variants(student: dict) -> set[str]:
    """1人の氏名について、探すべき表記のゆれ一覧を作る。"""
    variants: set[str] = set()
    name = (student.get("name") or "").strip()
    sei = (student.get("sei") or "").strip()
    mei = (student.get("mei") or "").strip()
    if name:
        variants.add(name)
    if sei and mei:
        variants.add(sei + mei)          # 田中太郎
        variants.add(sei + " " + mei)    # 田中 太郎（半角スペース）
        variants.add(sei + "　" + mei)  # 田中　太郎（全角スペース）
    return {v for v in variants if v}


def _class_notations(grade, class_no) -> list[tuple[str, bool]]:
    """年組表記を (文字列, 確認が必要か) で返す。"""
    g = str(grade)
    c = str(class_no)
    half = f"{g}年{c}組"
    dash = f"{g}-{c}"
    return [
        (half, False),
        (half.translate(_HAN2ZEN_DIGIT), False),  # ３年２組
        (dash, True),  # 日付・得点・資料番号とも読めるため確認する
        (dash.translate(_HAN2ZEN_DIGIT).replace("-", "－"), True),
    ]


def _fullwidth_variant(text: str) -> str:
    return text.translate(_HAN2ZEN_DIGIT)


def _standalone_notations(kind: str, value: int) -> list[tuple[str, bool]]:
    """単独表記を (文字列, 確認が必要か) で返す。"""
    value_s = str(value)
    if kind == "grade":
        automatic = (f"{value_s}年生", f"{value_s}学年", f"第{value_s}学年")
        ambiguous = (f"{value_s}年",)
    elif kind == "group":
        automatic = (f"第{value_s}組",)
        ambiguous = (f"{value_s}組",)
    elif kind == "number":
        automatic = (f"出席番号{value_s}番",)
        ambiguous = (f"{value_s}番",)
    else:
        raise ValueError(f"未対応の単独表記です: {kind}")

    notations: list[tuple[str, bool]] = []
    for text in automatic:
        notations.extend(((text, False), (_fullwidth_variant(text), False)))
    for text in ambiguous:
        notations.extend(((text, True), (_fullwidth_variant(text), True)))
    return list(dict.fromkeys(notations))


def build_index(master: dict) -> dict:
    """コード化のための内部インデックスを作る（走査を速くするため）。"""
    students = master.get("students", [])
    id_index = {s["id"]: s for s in students}

    # 氏名・姓のパターン: text -> {"ids": 該当生徒ID集合, "complete": 完全な氏名か}
    pat_map: dict[str, dict] = {}
    for s in students:
        for v in _student_name_variants(s):
            e = pat_map.setdefault(v, {"ids": set(), "complete": False})
            e["ids"].add(s["id"])
            e["complete"] = True  # 完全な氏名の表記
        sei = (s.get("sei") or "").strip()
        mei = (s.get("mei") or "").strip()
        if sei and mei:  # 姓が名と分かれているときだけ「姓のみ」を対象にする
            e = pat_map.setdefault(sei, {"ids": set(), "complete": False})
            e["ids"].add(s["id"])

    # 年組パターン: text -> class_code。後日そのクラスを登録しても結果が
    # 変わらないよう、現在の名簿ではなく対応範囲全体から作る。
    class_map: dict[str, dict] = {}
    for grade in range(roster.MIN_GRADE, roster.MAX_GRADE + 1):
        for class_no in range(roster.MIN_GROUP, roster.MAX_GROUP + 1):
            for notation, needs_review in _class_notations(grade, class_no):
                class_map.setdefault(
                    notation,
                    {
                        "code": roster.make_class_code(grade, class_no),
                        "needs_review": needs_review,
                    },
                )

    # 学年・組・番号の単独表記。同じ値は名簿に何人いても1回だけ登録する。
    attribute_map: dict[str, dict] = {}
    attribute_values = (
        (
            "grade",
            "学年",
            range(roster.MIN_GRADE, roster.MAX_GRADE + 1),
            roster.make_grade_code,
        ),
        (
            "group",
            "組",
            range(roster.MIN_GROUP, roster.MAX_GROUP + 1),
            roster.make_group_code,
        ),
        (
            "number",
            "出席番号",
            range(roster.MIN_NUMBER, roster.MAX_NUMBER + 1),
            roster.make_number_code,
        ),
    )
    for attribute, label, values, make_code in attribute_values:
        for value in values:
            code = make_code(value)
            for text, needs_review in _standalone_notations(attribute, value):
                attribute_map.setdefault(
                    text,
                    {
                        "attribute": attribute,
                        "label": label,
                        "code": code,
                        "needs_review": needs_review,
                    },
                )

    patterns: list[dict] = []
    for text, e in pat_map.items():
        patterns.append(
            {
                "text": text,
                "len": len(text),
                "kind": "student",
                "complete": e["complete"],
                "ids": sorted(e["ids"]),
            }
        )
    for text, entry in class_map.items():
        if text in pat_map:
            continue  # 氏名パターンと重なるものは氏名を優先
        patterns.append(
            {
                "text": text,
                "len": len(text),
                "kind": (
                    "attribute_review" if entry["needs_review"] else "class"
                ),
                "attribute": "class",
                "label": "年組",
                "code": entry["code"],
            }
        )
    for text, entry in attribute_map.items():
        if text in pat_map or text in class_map:
            continue
        patterns.append(
            {
                "text": text,
                "len": len(text),
                "kind": (
                    "attribute_review" if entry["needs_review"] else "attribute"
                ),
                "attribute": entry["attribute"],
                "label": entry["label"],
                "code": entry["code"],
            }
        )

    # 先頭文字ごとにまとめ、各グループを「長い順」に並べる
    by_first: dict[str, list[dict]] = {}
    for p in patterns:
        by_first.setdefault(p["text"][0], []).append(p)
    priority = {"student": 0, "class": 1, "attribute": 2, "attribute_review": 3}
    for group in by_first.values():
        group.sort(key=lambda p: (-p["len"], priority[p["kind"]]))

    return {"by_first": by_first, "id_index": id_index}


# ---------------------------------------------------------------------------
# 走査（1つの文字列を、重ならないように置換候補へ分解する）
# ---------------------------------------------------------------------------
def _scan(text: str, index: dict) -> tuple[list[dict], set[str]]:
    """text を左から走査し、置換対象の一覧と、出現した生徒ID集合を返す。"""
    by_first = index["by_first"]
    id_index = index["id_index"]
    matches: list[dict] = []
    appeared: set[str] = set()
    n = len(text)
    i = 0
    while i < n:
        chosen = None
        for p in by_first.get(text[i], ()):  # 長い順に試す
            L = p["len"]
            if i + L > n or text[i : i + L] != p["text"]:
                continue
            before = text[i - 1] if i > 0 else ""
            after = text[i + L] if i + L < n else ""
            if p["kind"] == "student" and not p["complete"]:
                # 姓のみ一致: 前後が漢字なら別の名前の一部の恐れ → 置換しない
                if _is_kanji(before) or _is_kanji(after):
                    continue
            if p["kind"] in ("class", "attribute", "attribute_review"):
                # 年組・単独項目: 前後が数字なら別の数字の一部の恐れ → 置換しない
                if _is_digit(before) or _is_digit(after):
                    continue
            chosen = p
            break

        if chosen is None:
            i += 1
            continue

        L = chosen["len"]
        if chosen["kind"] in ("class", "attribute"):
            matches.append(
                {
                    "start": i,
                    "end": i + L,
                    "kind": chosen["kind"],
                    "text": chosen["text"],
                    "code": chosen["code"],
                    "attribute": chosen.get("attribute"),
                }
            )
        elif chosen["kind"] == "attribute_review":
            matches.append(
                {
                    "start": i,
                    "end": i + L,
                    "kind": "attribute_review",
                    "text": chosen["text"],
                    "code": chosen["code"],
                    "attribute": chosen["attribute"],
                    "label": chosen["label"],
                }
            )
        else:
            ids = chosen["ids"]
            if len(ids) == 1:
                sid = ids[0]
                s = id_index[sid]
                appeared.add(sid)
                matches.append(
                    {
                        "start": i,
                        "end": i + L,
                        "kind": "name" if chosen["complete"] else "surname",
                        "text": chosen["text"],
                        "code": _student_code(s),
                        "student": sid,
                    }
                )
            else:  # 同姓が複数 → 自動置換せず「要確認」
                for sid in ids:
                    appeared.add(sid)
                matches.append(
                    {
                        "start": i,
                        "end": i + L,
                        "kind": "review",
                        "text": chosen["text"],
                        "candidates": ids,
                    }
                )
        i += L
    return matches, appeared


# ---------------------------------------------------------------------------
# プレビュー / 実行（コード化）
# ---------------------------------------------------------------------------
def preview(segments: list[str], master: dict, index: dict | None = None) -> dict:
    """コード化のプレビューを作る（実際には置換しない）。

    返す内容:
      replacements … 自動で置換する一覧（表記・コード・箇所数）
      reviews       … 同姓が複数で要確認の一覧（位置・前後の文脈・候補）
      not_found     … 名簿にあるのに本文に出てこなかった氏名
    """
    if index is None:
        index = build_index(master)
    id_index = index["id_index"]

    agg: dict[tuple, dict] = {}  # (kind, code) -> {display, code, kind, count}
    reviews: list[dict] = []
    appeared_all: set[str] = set()

    for seg_no, text in enumerate(segments):
        matches, appeared = _scan(text, index)
        appeared_all |= appeared
        for m in matches:
            if m["kind"] == "review":
                reviews.append(
                    {
                        "review_kind": "surname",
                        "seg": seg_no,
                        "position": m["start"],
                        "surname": m["text"],
                        "context": _context(text, m["start"], m["end"]),
                        "candidates": [
                            {
                                "id": sid,
                                "name": id_index[sid]["name"],
                                "code": _student_code(id_index[sid]),
                            }
                            for sid in m["candidates"]
                        ],
                    }
                )
            elif m["kind"] == "attribute_review":
                reviews.append(
                    {
                        "review_kind": "attribute",
                        "seg": seg_no,
                        "position": m["start"],
                        "text": m["text"],
                        "context": _context(text, m["start"], m["end"]),
                        "label": m["label"],
                        "code": m["code"],
                    }
                )
            else:
                key = (m["kind"], m["code"])
                entry = agg.get(key)
                if entry is None:
                    agg[key] = {
                        "kind": m["kind"],
                        "code": m["code"],
                        "display": _display_for(m, id_index),
                        "count": 1,
                    }
                else:
                    entry["count"] += 1

    replacements = sorted(
        agg.values(), key=lambda e: (e["kind"] != "name", e["code"])
    )
    not_found = [
        s["name"]
        for s in master.get("students", [])
        if s["id"] not in appeared_all
    ]
    return {
        "replacements": replacements,
        "reviews": reviews,
        "not_found": not_found,
    }


def apply(
    segments: list[str],
    master: dict,
    selections: dict | None = None,
    index: dict | None = None,
) -> tuple[list[str], dict]:
    """コード化を実行して、置換後の segments とレポートを返す。

    selections: 要確認への回答。 (seg番号, 位置) -> 生徒ID。
                指定が無い / 候補外のものは置換せず元のまま残す。
    """
    if index is None:
        index = build_index(master)
    id_index = index["id_index"]
    selections = selections or {}

    new_segments: list[str] = []
    replaced = 0
    review_total = 0
    review_resolved = 0
    appeared_all: set[str] = set()

    for seg_no, text in enumerate(segments):
        matches, appeared = _scan(text, index)
        appeared_all |= appeared
        out: list[str] = []
        last = 0
        for m in matches:
            out.append(text[last : m["start"]])
            if m["kind"] == "review":
                review_total += 1
                sid = selections.get((seg_no, m["start"]))
                if sid in m["candidates"]:
                    s = id_index[sid]
                    out.append(_student_code(s))
                    replaced += 1
                    review_resolved += 1
                else:
                    out.append(m["text"])  # 未回答は元のまま
            elif m["kind"] == "attribute_review":
                review_total += 1
                if selections.get((seg_no, m["start"])) == ATTRIBUTE_APPROVAL:
                    out.append(m["code"])
                    replaced += 1
                    review_resolved += 1
                else:
                    out.append(m["text"])
            else:
                out.append(m["code"])
                replaced += 1
            last = m["end"]
        out.append(text[last:])
        new_segments.append("".join(out))

    not_found = [
        s["name"]
        for s in master.get("students", [])
        if s["id"] not in appeared_all
    ]
    report = {
        "replaced": replaced,
        "review_total": review_total,
        "review_resolved": review_resolved,
        "not_found": not_found,
    }
    return new_segments, report


# ---------------------------------------------------------------------------
# 復元（コード → 氏名・年組）
# ---------------------------------------------------------------------------
def build_decode_index(master: dict) -> dict:
    """復元用の逆引きインデックスを作る。"""
    rev: dict[str, str] = {}
    for s in master.get("students", []):
        rev[_student_code(s)] = s["name"]

    # 短い項目コードは名簿登録の有無にかかわらず同じ規則で復元する。
    for grade in range(roster.MIN_GRADE, roster.MAX_GRADE + 1):
        rev.setdefault(roster.make_grade_code(grade), f"{grade}年")
    for class_no in range(roster.MIN_GROUP, roster.MAX_GROUP + 1):
        rev.setdefault(roster.make_group_code(class_no), f"{class_no}組")
    for number in range(roster.MIN_NUMBER, roster.MAX_NUMBER + 1):
        rev.setdefault(roster.make_number_code(number), f"{number}番")
    for grade in range(roster.MIN_GRADE, roster.MAX_GRADE + 1):
        for class_no in range(roster.MIN_GROUP, roster.MAX_GROUP + 1):
            rev.setdefault(
                roster.make_class_code(grade, class_no), f"{grade}年{class_no}組"
            )

    by_first: dict[str, list[dict]] = {}
    for text, repl in rev.items():
        by_first.setdefault(text[0], []).append(
            {"text": text, "len": len(text), "repl": repl}
        )
    for group in by_first.values():
        # 長い生徒コードを、短いクラスコードより先に照合する。
        group.sort(key=lambda p: -p["len"])
    return {"by_first": by_first}


def decode(
    segments: list[str], master: dict, index: dict | None = None
) -> tuple[list[str], dict]:
    """復元を実行して、置換後の segments とレポートを返す。"""
    if index is None:
        index = build_decode_index(master)
    by_first = index["by_first"]

    new_segments: list[str] = []
    replaced = 0
    for text in segments:
        out: list[str] = []
        n = len(text)
        i = 0
        while i < n:
            chosen = None
            for p in by_first.get(text[i], ()):
                L = p["len"]
                if i + L > n or text[i : i + L] != p["text"]:
                    continue
                before = text[i - 1] if i > 0 else ""
                after = text[i + L] if i + L < n else ""
                # コードの前後に英数字があれば別コードの一部の恐れ → 置換しない
                if _is_ascii_alnum(before) or _is_ascii_alnum(after):
                    continue
                chosen = p
                break
            if chosen is None:
                out.append(text[i])
                i += 1
            else:
                out.append(chosen["repl"])
                replaced += 1
                i += chosen["len"]
        new_segments.append("".join(out))
    return new_segments, {"replaced": replaced}


# ---------------------------------------------------------------------------
# 表示用の小物
# ---------------------------------------------------------------------------
def _display_for(match: dict, id_index: dict) -> str:
    if match["kind"] in ("name", "surname"):
        return id_index[match["student"]]["name"]
    return match["text"]  # 年組・単独項目は元の表記を表示


def _context(text: str, start: int, end: int, width: int = 8) -> str:
    """前後の文脈を短く切り出す（要確認リスト表示用）。"""
    left = text[max(0, start - width) : start]
    hit = text[start:end]
    right = text[end : end + width]
    return f"…{left}[{hit}]{right}…"
