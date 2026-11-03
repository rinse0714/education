"""쇼핑 리스트 앱 (Streamlit)."""

import json
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

DATA_FILE = Path(__file__).parent / "shopping_list.json"


# ---------- 저장소 ----------

def _backup_corrupt_file() -> Path | None:
    """손상된 데이터 파일을 덮어쓰지 않도록 별도 이름으로 보관한다."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DATA_FILE.with_name(f"{DATA_FILE.stem}.corrupt-{stamp}.json")
    try:
        DATA_FILE.replace(backup)
    except OSError:
        return None
    return backup


def _normalize(raw) -> dict | None:
    """저장된 아이템 하나를 검증·보정한다. 쓸 수 없는 항목이면 None."""
    if not isinstance(raw, dict):
        return None
    if not isinstance(raw.get("id"), str) or not isinstance(raw.get("name"), str):
        return None
    if not raw["name"].strip():
        return None
    quantity = raw.get("quantity", 1)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        quantity = 1
    return {
        "id": raw["id"],
        "name": raw["name"].strip(),
        "quantity": quantity,
        "checked": bool(raw.get("checked", False)),
        "created_at": str(raw.get("created_at", "")),
    }


def read_items() -> tuple[list[dict], str | None]:
    """데이터 파일을 읽어 (아이템 목록, 경고 메시지)를 반환한다.

    파일이 손상되었거나 일부 항목을 읽을 수 없으면, 원본을 백업 파일로 옮겨
    다음 저장 때 덮어써서 데이터가 사라지지 않게 하고 경고 메시지를 돌려준다.
    """
    if not DATA_FILE.exists():
        return [], None
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        data = None

    if not isinstance(data, list):
        backup = _backup_corrupt_file()
        where = f" 원본은 `{backup.name}`에 보관했어요." if backup else ""
        return [], f"저장된 쇼핑 리스트 파일이 손상되어 빈 리스트로 시작합니다.{where}"

    items = [n for n in (_normalize(i) for i in data) if n is not None]
    if len(items) < len(data):
        backup = _backup_corrupt_file()
        if backup:
            save_items(items)
        where = f" 원본은 `{backup.name}`에 보관했어요." if backup else ""
        skipped = len(data) - len(items)
        return items, f"읽을 수 없는 항목 {skipped}개를 제외하고 불러왔어요.{where}"
    return items, None


def load_items() -> list[dict]:
    """JSON 파일에서 아이템 목록을 읽는다. 없거나 손상되면 빈 리스트."""
    return read_items()[0]


def save_items(items: list[dict]) -> None:
    """아이템 목록을 JSON 파일에 저장한다."""
    DATA_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------- 상태 ----------
# 주의: st.session_state.items 는 dict.items() 메서드와 충돌하므로 shopping_items 사용

def init_state() -> None:
    """세션 상태를 최초 1회 초기화한다."""
    if "shopping_items" not in st.session_state:
        items, warning = read_items()
        st.session_state.shopping_items = items
        st.session_state.load_warning = warning
    if "editing_id" not in st.session_state:
        st.session_state.editing_id = None
    if "edit_error" not in st.session_state:
        st.session_state.edit_error = None


def get_items() -> list[dict]:
    """현재 세션의 아이템 목록."""
    return st.session_state.shopping_items


def find_item(item_id: str) -> dict | None:
    """id로 아이템을 찾는다."""
    return next((i for i in get_items() if i["id"] == item_id), None)


def validate(name: str, quantity) -> str | None:
    """입력값을 검증하고 오류 메시지를 반환한다. 문제가 없으면 None."""
    if not name or not name.strip():
        return "아이템 이름을 입력해 주세요."
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        return "수량은 1 이상의 정수여야 합니다."
    return None


# ---------- CRUD ----------

def add_item(name: str, quantity: int) -> None:
    """새 아이템을 추가한다."""
    get_items().append({
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "quantity": int(quantity),
        "checked": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    })
    save_items(get_items())


def update_item(item_id: str, name: str, quantity: int) -> None:
    """아이템의 이름과 수량을 수정한다."""
    item = find_item(item_id)
    if item is None:
        return
    item["name"] = name.strip()
    item["quantity"] = int(quantity)
    save_items(get_items())


def delete_item(item_id: str) -> None:
    """아이템을 삭제한다."""
    st.session_state.shopping_items = [i for i in get_items() if i["id"] != item_id]
    if st.session_state.editing_id == item_id:
        st.session_state.editing_id = None
        st.session_state.edit_error = None
    save_items(get_items())


def toggle_item(item_id: str) -> None:
    """아이템의 체크 상태를 토글한다."""
    item = find_item(item_id)
    if item is None:
        return
    item["checked"] = not item["checked"]
    save_items(get_items())


def delete_checked() -> None:
    """체크된 아이템을 모두 삭제한다."""
    checked_ids = {i["id"] for i in get_items() if i["checked"]}
    st.session_state.shopping_items = [i for i in get_items() if not i["checked"]]
    if st.session_state.editing_id in checked_ids:
        st.session_state.editing_id = None
        st.session_state.edit_error = None
    save_items(get_items())


# ---------- 편집 모드 콜백 ----------

def start_edit(item_id: str) -> None:
    """해당 아이템을 편집 모드로 전환한다 (한 번에 하나만)."""
    st.session_state.pop(f"edit_name_{item_id}", None)
    st.session_state.pop(f"edit_qty_{item_id}", None)
    st.session_state.editing_id = item_id
    st.session_state.edit_error = None


def cancel_edit() -> None:
    """편집을 취소한다."""
    st.session_state.editing_id = None
    st.session_state.edit_error = None


def save_edit(item_id: str) -> None:
    """편집 내용을 검증 후 저장한다."""
    name = st.session_state.get(f"edit_name_{item_id}", "")
    quantity = st.session_state.get(f"edit_qty_{item_id}", 1)
    error = validate(name, quantity)
    if error:
        st.session_state.edit_error = error
        return
    update_item(item_id, name, quantity)
    st.session_state.editing_id = None
    st.session_state.edit_error = None


# ---------- 화면 ----------

CSS = """
<style>
.item-name { font-size: 1.05rem; line-height: 1.5; word-break: break-all; }
.item-name.done { text-decoration: line-through; opacity: 0.45; }
/* 이름 칸의 Markdown 기본 아래 여백 제거 → 체크박스·버튼과 세로 중앙 정렬 */
div[data-testid="stColumn"] div[data-testid="stMarkdownContainer"]:has(.item-name) { margin-bottom: 0; }
div[data-testid="stColumn"] div[data-testid="stMarkdown"]:has(.item-name) { margin-bottom: 0; }
div[data-testid="stColumn"] .stMarkdown:has(.item-name) p { margin: 0; }
.qty-badge {
    display: inline-block; margin-left: 0.5rem; padding: 0 0.5rem;
    font-size: 0.8rem; line-height: 1.4rem; border-radius: 999px;
    background: rgba(128, 128, 128, 0.18); vertical-align: middle;
}
/* 좁은 화면에서도 행의 열이 세로로 쌓이지 않게 */
@media (max-width: 640px) {
    div[data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 0.4rem !important; }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] { min-width: 0 !important; }
    /* 버튼이 들어 있는 열은 아이콘/글자가 잘리지 않을 최소 폭 확보 */
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:has(button) {
        min-width: 2.75rem !important; flex-shrink: 0 !important;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:has(button) button {
        padding-left: 0.35rem; padding-right: 0.35rem; min-width: 2.75rem;
    }
    div[data-testid="stForm"] div[data-testid="stColumn"]:has(button) { min-width: 3.5rem !important; }
    /* 체크박스 열이 줄어들어 이름과 겹치지 않게 */
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:has([data-testid="stCheckbox"]) {
        min-width: 1.75rem !important; flex-shrink: 0 !important;
    }
}
</style>
"""

# Markdown/LaTeX로 해석될 수 있는 문자까지 HTML 엔티티로 바꾼다
_ESCAPE = {c: f"&#{ord(c)};" for c in "&<>\"'*_~`[]()#|$\\!+-=.{}"}


def escape_text(text: str) -> str:
    """사용자 입력을 HTML/Markdown에 안전하게 넣을 수 있도록 이스케이프한다."""
    return "".join(_ESCAPE.get(c, c) for c in text)


def on_add_submit() -> None:
    """추가 폼 제출 콜백.

    스크립트 본문이 아니라 콜백에서 처리해야, 빠른 연속 클릭으로 실행이 중단돼도
    제출한 아이템이 사라지지 않는다.
    """
    name = st.session_state.get("new_name", "")
    quantity = st.session_state.get("new_qty", 1)
    error = validate(name, quantity)
    st.session_state.add_error = error
    if error is None:
        add_item(name, quantity)
        st.toast(f"'{escape_text(name.strip())}'을(를) 추가했어요", icon="✅")


def render_add_form() -> None:
    """아이템 추가 폼."""
    with st.form("add_form", clear_on_submit=True, border=False):
        col_name, col_qty, col_btn = st.columns([5, 1.6, 1.2], vertical_alignment="bottom")
        col_name.text_input("아이템 이름", placeholder="예: 우유", key="new_name")
        # min_value를 두지 않고 validate()로 검사해 PRD의 한국어 경고를 보여준다
        col_qty.number_input("수량", step=1, value=1, key="new_qty")
        col_btn.form_submit_button("추가", type="primary", use_container_width=True,
                                   on_click=on_add_submit)
    # 경고는 제출 직후 한 번만 보여준다
    error = st.session_state.pop("add_error", None)
    if error:
        st.warning(error, icon="⚠️")


def render_item(item: dict) -> None:
    """아이템 한 행 (카드)."""
    item_id = item["id"]
    with st.container(border=True):
        if st.session_state.editing_id == item_id:
            col_name, col_qty, col_save, col_cancel = st.columns(
                [5, 1.6, 1, 1], vertical_alignment="bottom"
            )
            col_name.text_input("이름", value=item["name"], key=f"edit_name_{item_id}")
            col_qty.number_input(
                "수량", step=1, value=item["quantity"], key=f"edit_qty_{item_id}"
            )
            col_save.button("💾", key=f"save_{item_id}", help="저장", type="primary",
                            on_click=save_edit, args=(item_id,), use_container_width=True)
            col_cancel.button("✖️", key=f"cancel_{item_id}", help="취소",
                              on_click=cancel_edit, use_container_width=True)
            if st.session_state.edit_error:
                st.warning(st.session_state.edit_error, icon="⚠️")
            return

        col_chk, col_name, col_edit, col_del = st.columns(
            [0.5, 6, 0.9, 0.9], vertical_alignment="center"
        )
        col_chk.checkbox(
            "구매 완료",
            value=item["checked"],
            key=f"chk_{item_id}",
            on_change=toggle_item,
            args=(item_id,),
            label_visibility="collapsed",
        )
        done_cls = " done" if item["checked"] else ""
        col_name.markdown(
            f'<div class="item-name{done_cls}">{escape_text(item["name"])}'
            f'<span class="qty-badge">× {item["quantity"]}</span></div>',
            unsafe_allow_html=True,
        )
        col_edit.button("✏️", key=f"edit_{item_id}", help="수정",
                        on_click=start_edit, args=(item_id,), use_container_width=True)
        col_del.button("🗑️", key=f"del_{item_id}", help="삭제",
                       on_click=on_delete, args=(item_id, item["name"]), use_container_width=True)


def on_delete(item_id: str, name: str) -> None:
    """삭제 버튼 콜백 (삭제 + 알림)."""
    delete_item(item_id)
    st.toast(f"'{escape_text(name)}'을(를) 삭제했어요", icon="🗑️")


def on_delete_checked() -> None:
    """체크된 항목 모두 삭제 버튼 콜백."""
    count = sum(1 for i in get_items() if i["checked"])
    delete_checked()
    st.toast(f"구매 완료한 {count}개 항목을 삭제했어요", icon="🧹")


def main() -> None:
    """앱 진입점."""
    st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒", layout="centered")
    init_state()
    st.markdown(CSS, unsafe_allow_html=True)

    st.title("🛒 쇼핑 리스트")
    st.caption("장보기 전에 적고, 장보면서 체크하세요")

    if st.session_state.get("load_warning"):
        st.warning(st.session_state.load_warning, icon="⚠️")
        st.button("확인", key="dismiss_load_warning",
                  on_click=lambda: st.session_state.update(load_warning=None))

    items = list(get_items())  # 렌더링용 복사본 (모든 변경은 콜백에서 이미 반영됨)
    total = len(items)
    done = sum(1 for i in items if i["checked"])

    # PRD 6장: 진행 상황 요약 → 입력 폼 → 리스트 순서
    st.progress(
        done / total if total else 0.0,
        text=f"구매 완료 **{done}** / 전체 **{total}**",
    )

    render_add_form()

    if not items:
        st.info("쇼핑 리스트가 비어 있습니다. 위에서 사야 할 물건을 추가해 보세요.", icon="🧺")
    elif done == total:
        st.success("장보기 완료! 🎉")

    # 미완료 항목을 위로 (저장 순서는 그대로, 화면 표시만 정렬)
    for item in sorted(items, key=lambda i: i["checked"]):
        render_item(item)

    if items:
        st.button("🧹 체크된 항목 모두 삭제", on_click=on_delete_checked, disabled=done == 0)


if __name__ == "__main__":
    main()
