"""초등학생 장보기 미션 앱

GitHub 저장소에 app.py, products.csv, requirements.txt를 같은 폴더에 둡니다.
PNG의 한글을 확실하게 표시하려면 NanumHumanRegular.ttf도 같은 폴더에 추가하세요.
"""

import csv
import html
import io
from pathlib import Path
from urllib.parse import urlparse

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError


st.set_page_config(page_title="초등학생 장보기 미션", page_icon="🛒", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
PRODUCTS_CSV = BASE_DIR / "products.csv"
MISSIONS = {
    "카레 만들기": {
        "emoji": "🍛",
        "budget": 25_000,
        "guide": "카레를 만드는 데 꼭 필요한 재료를 골라 보세요!",
    },
    "여름캠핑 준비하기": {
        "emoji": "🏕️",
        "budget": 100_000,
        "guide": "더운 여름, 신나는 캠핑에 필요한 물건을 준비해 보세요!",
    },
    "친구 생일파티 준비하기": {
        "emoji": "🎂",
        "budget": 60_000,
        "guide": "친구와 즐겁게 생일파티를 열기 위한 물건을 골라 보세요!",
    },
}

# 상품 이미지 크기는 CSS로 고정합니다. 쇼핑 화면에서는 서버의 st.image()를 사용하지 않습니다.
st.markdown(
    """
<style>
.block-container {max-width: 1260px; padding-top: 1.5rem; padding-bottom: 3rem;}
[data-testid="stMetricValue"] {font-size: 1.7rem;}
div.stButton > button {font-weight: 700;}
.mission-banner {text-align: center; padding: 12px 4px 20px;}
.mission-banner .emoji {font-size: 50px; line-height: 1.25;}
.mission-banner h3 {font-size: 20px; margin: 8px 0 0;}
.mission-banner .amount {font-size: 24px; font-weight: 800; color: #146b88; margin: 10px 0;}
.mission-banner .guide {font-size: 14px; color: #637488; min-height: 44px;}
/* 고정 높이 카드: 상품명/사진/가격이 항상 같은 위치에 배치됩니다. */
.product-tile {box-sizing: border-box; height: 270px; overflow: hidden;
    display: grid; grid-template-rows: 52px 166px 36px;
    gap: 4px; padding: 5px 2px;}
.product-title {font-size: 18px; line-height: 24px; font-weight: 750;
    color: #182a3d; display: -webkit-box; -webkit-line-clamp: 2;
    -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere;}
.product-img-wrap {height: 166px; border-radius: 12px; background: #f3f6fa;
    display: flex; align-items: center; justify-content: center; overflow: hidden;}
.product-img-wrap img {width: 100%; height: 100%; object-fit: contain;
    display: block; background: #f3f6fa;}
.product-img-fallback {font-size: 14px; color: #718096; text-align: center;}
.product-price {height: 36px; line-height: 36px; color: #087a8c;
    font-size: 21px; font-weight: 800; white-space: nowrap;}
.quantity-number {text-align: center; height: 38px; line-height: 38px;
    font-size: 18px; font-weight: 800;}
.cart-image {height: 84px; width: 100%; object-fit: contain; background: #f3f6fa;
    border-radius: 10px; display: block;}
.cart-img-placeholder {height: 84px; background: #f3f6fa; border-radius: 10px;
    display: flex; align-items: center; justify-content: center; font-size: 12px;}
.cart-details {min-height: 84px; display: flex; flex-direction: column;
    justify-content: center; gap: 4px; overflow-wrap: anywhere;}
.cart-name {font-size: 17px; font-weight: 750;}
.cart-meta {font-size: 14px; color: #637488;}
.cart-sum {font-size: 17px; color: #087a8c; font-weight: 800;}
.receipt-heading {text-align: center; margin-bottom: 12px;}
.receipt-item {display: grid; grid-template-columns: 90px minmax(110px,1fr) auto;
    column-gap: 15px; align-items: center; border: 1px solid #e4eaf1;
    border-radius: 14px; padding: 12px 15px; margin-bottom: 12px;}
.receipt-item img {width: 90px; height: 84px; object-fit: contain;
    background: #f3f6fa; border-radius: 10px;}
.receipt-name {font-weight: 800; font-size: 18px; overflow-wrap: anywhere;}
.receipt-info {color: #66788a; font-size: 14px; padding-top: 4px;}
.receipt-total {font-size: 18px; font-weight: 800; text-align: right;}
@media(max-width: 640px) {
    .product-tile {height: 248px; grid-template-rows: 46px 150px 34px;}
    .product-img-wrap {height: 150px;}
    .product-title {font-size: 16px; line-height: 22px;}
    .product-price {font-size: 18px;}
    .receipt-item {grid-template-columns: 65px minmax(75px,1fr); gap: 10px;}
    .receipt-item img {width: 65px; height: 68px;}
    .receipt-total {grid-column: 2; text-align: left;}
}
</style>
""",
    unsafe_allow_html=True,
)


def won(value: int) -> str:
    return f"{value:,}원"


def valid_image_url(url: str) -> str:
    """HTML 속성에는 정상적인 HTTP(S) 이미지 URL만 허용합니다."""
    url = (url or "").strip()
    parts = urlparse(url)
    if parts.scheme.lower() in ("http", "https") and parts.netloc:
        return url
    return ""


def image_html(url: str, css_class: str, name: str) -> str:
    src = valid_image_url(url)
    if not src:
        return '<div class="product-img-fallback">🖼️ 사진 없음</div>'
    return (
        f'<img class="{css_class}" src="{html.escape(src, quote=True)}" '
        f'alt="{html.escape(name, quote=True)}" loading="lazy" decoding="async">'
    )


@st.cache_data(show_spinner=False)
def load_products(path: str, mtime: float):
    """상품명, 가격, 이미지 URL을 CSV에서 읽습니다. 파일 수정 시 캐시를 갱신합니다."""
    del mtime
    items = []
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        headers = {x.strip(): x for x in (reader.fieldnames or [])}
        img_column = next(
            (headers[x] for x in ("이미지 url", "이미지 URL", "이미지_url") if x in headers),
            None,
        )
        if "품명" not in headers or "가격" not in headers or not img_column:
            raise ValueError("products.csv 첫 줄에는 '품명,가격,이미지 url' 열이 필요합니다.")
        for line_no, record in enumerate(reader, start=2):
            name = (record.get(headers["품명"]) or "").strip()
            raw = (record.get(headers["가격"]) or "").strip().replace(",", "").replace("원", "")
            if not name and not raw:
                continue
            try:
                price = int(raw)
                if not name or price <= 0:
                    raise ValueError
            except ValueError as error:
                raise ValueError(f"products.csv {line_no}행의 품명 또는 가격을 확인하세요.") from error
            items.append({
                "name": name,
                "price": price,
                "url": valid_image_url(record.get(img_column, "")),
            })
    if not items:
        raise ValueError("products.csv에 상품이 없습니다.")
    return items


# ------------------------ PNG 전용: 한글 폰트 및 썸네일 ------------------------
def korean_font_path() -> str | None:
    """NanumHumanRegular.ttf를 우선 사용하며, 배포 서버의 한글 글꼴도 지원합니다."""
    candidates = (
        BASE_DIR / "NanumHumanRegular.ttf",
        BASE_DIR / "fonts" / "NanumHumanRegular.ttf",
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    )
    for path in candidates:
        if path.is_file():
            try:
                ImageFont.truetype(str(path), size=24)
                return str(path)
            except OSError:
                continue
    return None


@st.cache_data(show_spinner=False, ttl=3600, max_entries=128)
def png_thumbnail(image_url: str) -> bytes | None:
    """PNG 저장 시에만 서버가 이미지를 가져옵니다. 화면 상품사진은 HTML에서 직접 표시."""
    url = valid_image_url(image_url)
    if not url:
        return None
    try:
        with requests.get(url, timeout=(3, 6), stream=True, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            resp.raise_for_status()
            if int(resp.headers.get("content-length", "0")) > 4_000_000:
                return None
            buf = io.BytesIO()
            for chunk in resp.iter_content(chunk_size=32768):
                buf.write(chunk)
                if buf.tell() > 4_000_000:
                    return None
        buf.seek(0)
        with Image.open(buf) as original:
            if original.width * original.height > 12_000_000:
                return None
            thumb = ImageOps.exif_transpose(original).convert("RGB")
            thumb.thumbnail((136, 105), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            thumb.save(output, "PNG")
            return output.getvalue()
    except (requests.RequestException, OSError, ValueError, UnidentifiedImageError):
        return None


def wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    """한글/띄어쓰기/줄바꿈을 모두 보존하며 이미지 너비에 맞춰 줄바꿈합니다."""
    lines = []
    for para in text.replace("\r\n", "\n").split("\n"):
        current = ""
        for char in para:
            if current and draw.textlength(current + char, font=font) > max_width:
                lines.append(current)
                current = char
            else:
                current += char
        lines.append(current)
    return lines


def clip_text(draw, value, font, max_width):
    if draw.textlength(value, font=font) <= max_width:
        return value
    shortened = value
    while shortened and draw.textlength(shortened + "…", font=font) > max_width:
        shortened = shortened[:-1]
    return shortened + "…"


@st.cache_data(show_spinner=False, max_entries=40)
def create_result_png(mission: str, budget: int, items: tuple, reason: str) -> bytes:
    """한글 TTF를 사용하여 구매목록/단가/합계/예산/구매이유를 PNG로 출력합니다."""
    path = korean_font_path()
    if path is None:
        raise RuntimeError(
            "한글 폰트를 찾을 수 없습니다. GitHub의 app.py 옆에 "
            "NanumHumanRegular.ttf 파일을 업로드한 뒤 다시 실행하세요."
        )

    ft_title = ImageFont.truetype(path, 47)
    ft_section = ImageFont.truetype(path, 30)
    ft_heading = ImageFont.truetype(path, 25)
    ft_normal = ImageFont.truetype(path, 26)
    ft_name = ImageFont.truetype(path, 27)
    ft_small = ImageFont.truetype(path, 22)
    ft_amount = ImageFont.truetype(path, 32)

    width, side, row_height = 1280, 66, 144
    working = ImageDraw.Draw(Image.new("RGB", (width, 10), "#ffffff"))
    reason_lines = wrap_text(working, reason, ft_normal, width - 2 * side - 44)
    reason_lines = reason_lines or [""]
    rows_top = 348
    totals_top = rows_top + row_height * len(items) + 30
    reason_heading_y = totals_top + 228
    reason_box_y = reason_heading_y + 56
    reason_box_height = max(125, len(reason_lines) * 43 + 44)
    height = reason_box_y + reason_box_height + 95
    image = Image.new("RGB", (width, height), "#f6f9fc")
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((34, 28, width - 34, 192), radius=28, fill="#dceefa")
    draw.text((width // 2, 99), f"미션: {mission}", fill="#123c56",
              font=ft_title, anchor="mm")
    draw.text((width // 2, 155), "나의 알뜰 장보기 결과", fill="#27627c",
              font=ft_heading, anchor="mm")

    draw.text((side, 224), "구매품목", font=ft_section, fill="#1d3749")
    draw.rounded_rectangle((side - 8, 275, width - side + 8, 331), radius=10, fill="#e5edf5")
    draw.text((86, 291), "이미지", font=ft_heading, fill="#41536a")
    draw.text((260, 291), "이름", font=ft_heading, fill="#41536a")
    draw.text((746, 291), "수량", font=ft_heading, fill="#41536a")
    draw.text((1030, 291), "단가", font=ft_heading, fill="#41536a", anchor="ra")
    draw.text((1194, 291), "합계", font=ft_heading, fill="#41536a", anchor="ra")

    for row_number, (name, price, url, quantity) in enumerate(items):
        y = rows_top + row_number * row_height
        draw.rounded_rectangle((side - 8, y, width - side + 8, y + 132),
                               radius=16, fill="white")
        draw.rounded_rectangle((80, y + 11, 227, y + 122), radius=10, fill="#f0f4f8")
        image_bytes = png_thumbnail(url)
        if image_bytes:
            with Image.open(io.BytesIO(image_bytes)) as thumbnail:
                thumb = thumbnail.convert("RGB")
                px = 80 + (147 - thumb.width) // 2
                py = y + 11 + (111 - thumb.height) // 2
                image.paste(thumb, (px, py))
        else:
            draw.text((154, y + 67), "사진 없음", font=ft_small, fill="#66788a", anchor="mm")

        item_lines = wrap_text(draw, name, ft_name, 430)
        if len(item_lines) > 2:
            item_lines = [item_lines[0], clip_text(draw, item_lines[1] + "…", ft_name, 430)]
        if len(item_lines) == 1:
            draw.text((260, y + 65), item_lines[0], font=ft_name, fill="#1e293b", anchor="lm")
        else:
            draw.text((260, y + 38), item_lines[0], font=ft_name, fill="#1e293b", anchor="lm")
            draw.text((260, y + 86), item_lines[1], font=ft_name, fill="#1e293b", anchor="lm")

        draw.text((770, y + 65), f"{quantity}개", font=ft_normal, fill="#263849", anchor="mm")
        draw.text((1030, y + 65), won(price), font=ft_small, fill="#384b60", anchor="rm")
        draw.text((1194, y + 65), won(price * quantity), font=ft_small,
                  fill="#075d73", anchor="rm")

    draw.rounded_rectangle((side - 8, totals_top, width - side + 8, totals_top + 175),
                           radius=20, fill="#e4f5ed")
    total = sum(price * quantity for _, price, _, quantity in items)
    metrics = (
        ("주어진 금액", won(budget)),
        ("총 사용 금액", won(total)),
        ("잔액", won(budget - total)),
    )
    for i, (label, amount) in enumerate(metrics):
        mx = 246 + i * 397
        draw.text((mx, totals_top + 54), label, font=ft_heading,
                  fill="#426655", anchor="mm")
        draw.text((mx, totals_top + 113), amount, font=ft_amount,
                  fill="#0c7055", anchor="mm")

    draw.text((side, reason_heading_y), "구매 이유", font=ft_section, fill="#1d3749")
    draw.rounded_rectangle((side - 8, reason_box_y, width - side + 8,
                            reason_box_y + reason_box_height), radius=19, fill="white")
    y = reason_box_y + 26
    for line in reason_lines:
        draw.text((side + 16, y), line, font=ft_normal, fill="#253849")
        y += 43

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


# ------------------------------- 상태 및 이동 -------------------------------
def choose_mission(name: str):
    st.session_state.mission = name
    st.session_state.page = "shopping"
    st.session_state.cart = {}
    st.session_state.submitted_cart = {}
    st.session_state.reason_draft = ""
    st.session_state.submitted_reason = ""
    for key in list(st.session_state.keys()):
        if str(key).startswith("qty_"):
            del st.session_state[key]


def change_qty(product_index: int, delta: int):
    key = f"qty_{product_index}"
    st.session_state[key] = max(1, min(99, st.session_state.get(key, 1) + delta))


def add_to_cart(product_index: int):
    amount = st.session_state.get(f"qty_{product_index}", 1)
    st.session_state.cart[product_index] = st.session_state.cart.get(product_index, 0) + amount
    st.session_state[f"qty_{product_index}"] = 1


def edit_cart(product_index: int, delta: int):
    current = st.session_state.cart.get(product_index, 0)
    updated = current + delta
    if updated <= 0:
        st.session_state.cart.pop(product_index, None)
    else:
        st.session_state.cart[product_index] = updated


def remove_item(product_index: int):
    st.session_state.cart.pop(product_index, None)


def submit_cart():
    # 이 버튼으로만 결과 페이지에 진입할 수 있습니다.
    st.session_state.submitted_cart = dict(st.session_state.cart)
    st.session_state.submitted_reason = ""
    st.session_state.reason_draft = ""
    st.session_state.page = "result"


for key, initial in (
    ("page", "start"), ("mission", None), ("cart", {}),
    ("submitted_cart", {}), ("reason_draft", ""), ("submitted_reason", ""),
):
    if key not in st.session_state:
        st.session_state[key] = initial

if not PRODUCTS_CSV.is_file():
    st.error("app.py와 같은 폴더에 products.csv 파일이 필요합니다.")
    st.stop()
try:
    products = load_products(str(PRODUCTS_CSV), PRODUCTS_CSV.stat().st_mtime)
except (OSError, ValueError) as error:
    st.error(str(error))
    st.stop()


# --------------------------------- 시작 화면 ---------------------------------
if st.session_state.page == "start":
    st.title("🛒 우리 반 장보기 미션")
    st.write("미션을 하나 선택하고, 정해진 예산 안에서 알뜰하게 쇼핑해 보세요!")
    st.info("가격을 계산하고 필요한 물건을 골라 보는 경제 공부 시간이에요.")
    for column, (name, info) in zip(st.columns(3, gap="medium"), MISSIONS.items()):
        with column:
            with st.container(border=True):
                st.markdown(
                    '<div class="mission-banner">'
                    f'<div class="emoji">{info["emoji"]}</div>'
                    f'<h3>{html.escape(name)}</h3>'
                    f'<div class="amount">예산 {won(info["budget"])}</div>'
                    f'<div class="guide">{html.escape(info["guide"])}</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                st.button("미션 시작하기 →", key=f"start_{name}",
                          on_click=choose_mission, args=(name,),
                          type="primary", use_container_width=True)

# --------------------------------- 쇼핑 화면 ---------------------------------
elif st.session_state.page == "shopping":
    mission = st.session_state.mission
    if mission not in MISSIONS:
        st.session_state.page = "start"
        st.rerun()
    info = MISSIONS[mission]
    budget = info["budget"]
    st.title(f'{info["emoji"]} {mission}')
    st.caption(info["guide"])
    if st.button("← 미션 다시 선택하기"):
        st.session_state.page = "start"
        st.rerun()

    st.subheader("🏪 장보기 마트")
    st.caption("상품마다 수량을 정한 뒤 [장바구니 담기]를 누르세요.")

    # 한 줄에 카드 3개. 정보 영역의 높이는 CSS에서 고정하여 정렬을 유지합니다.
    for start_idx in range(0, len(products), 3):
        columns = st.columns(3, gap="medium")
        for column, idx in zip(columns, range(start_idx, min(start_idx + 3, len(products)))):
            product = products[idx]
            key = f"qty_{idx}"
            if key not in st.session_state:
                st.session_state[key] = 1
            with column:
                with st.container(border=True):
                    st.markdown(
                        '<div class="product-tile">'
                        f'<div class="product-title">{html.escape(product["name"])}</div>'
                        '<div class="product-img-wrap">'
                        f'{image_html(product["url"], "product-image", product["name"])}'
                        '</div>'
                        f'<div class="product-price">{won(product["price"])}</div>'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                    col_minus, col_count, col_plus = st.columns([1, 1.15, 1], gap="small")
                    with col_minus:
                        st.button("−", key=f"decrease_{idx}", use_container_width=True,
                                  disabled=st.session_state[key] <= 1,
                                  on_click=change_qty, args=(idx, -1))
                    with col_count:
                        st.markdown(
                            f'<div class="quantity-number">{st.session_state[key]}</div>',
                            unsafe_allow_html=True,
                        )
                    with col_plus:
                        st.button("+", key=f"increase_{idx}", use_container_width=True,
                                  disabled=st.session_state[key] >= 99,
                                  on_click=change_qty, args=(idx, 1))
                    st.button("🛒 장바구니 담기", key=f"add_{idx}",
                              on_click=add_to_cart, args=(idx,),
                              use_container_width=True)

    st.divider()
    st.subheader("🧺 내 장바구니")
    cart = st.session_state.cart
    # CSV가 수정되는 경우 유효하지 않은 행 인덱스는 장바구니에서 제거합니다.
    for idx in list(cart):
        if idx >= len(products) or idx < 0:
            del cart[idx]
    total = sum(products[idx]["price"] * count for idx, count in cart.items())
    remaining = budget - total
    first, second, third = st.columns(3)
    first.metric("주어진 예산", won(budget))
    second.metric("사용한 금액", won(total))
    third.metric("남은 돈", won(remaining))
    st.progress(min(1.0, total / budget))

    if not cart:
        st.info("장바구니가 비어 있어요. 위에서 필요한 물건을 선택하세요.")
    else:
        for idx, count in sorted(cart.items()):
            product = products[idx]
            with st.container(border=True):
                pic, description, minus, plus, delete = st.columns(
                    [1.0, 4.0, 0.8, 0.8, 1.1], gap="small", vertical_alignment="center"
                )
                with pic:
                    src = valid_image_url(product["url"])
                    if src:
                        st.markdown(image_html(src, "cart-image", product["name"]),
                                    unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="cart-img-placeholder">🖼️</div>',
                                    unsafe_allow_html=True)
                with description:
                    st.markdown(
                        '<div class="cart-details">'
                        f'<div class="cart-name">{html.escape(product["name"])}</div>'
                        f'<div class="cart-meta">단가 {won(product["price"])} × {count}개</div>'
                        f'<div class="cart-sum">합계 {won(product["price"] * count)}</div>'
                        '</div>', unsafe_allow_html=True,
                    )
                with minus:
                    st.button("−", key=f"cart_minus_{idx}", help="한 개 빼기",
                              use_container_width=True, on_click=edit_cart, args=(idx, -1))
                with plus:
                    st.button("+", key=f"cart_plus_{idx}", help="한 개 더하기",
                              use_container_width=True, on_click=edit_cart, args=(idx, 1))
                with delete:
                    st.button("삭제", key=f"cart_delete_{idx}",
                              use_container_width=True, on_click=remove_item, args=(idx,))

    if total > budget:
        st.error(f"🚨 예산을 {won(total - budget)} 초과했어요. 장바구니에서 수량을 줄여 주세요!")
    elif cart:
        st.success("✅ 예산 안에서 쇼핑했어요. 구매할 물건을 확인하고 제출해 보세요!")

    st.button("📮 장바구니 제출하기", type="primary", use_container_width=True,
              disabled=not cart or total > budget,
              on_click=submit_cart)

# --------------------------------- 결과 화면 ---------------------------------
elif st.session_state.page == "result":
    mission = st.session_state.mission
    submitted_cart = st.session_state.submitted_cart
    if mission not in MISSIONS or not submitted_cart:
        # 제출 정보 없이 결과 화면에 진입할 수 없습니다.
        st.session_state.page = "start"
        st.rerun()
    budget = MISSIONS[mission]["budget"]
    items = tuple(
        (products[idx]["name"], products[idx]["price"], products[idx]["url"], count)
        for idx, count in sorted(submitted_cart.items()) if 0 <= idx < len(products)
    )
    total = sum(price * count for _, price, _, count in items)

    st.markdown(
        f'<div class="receipt-heading"><h1>🎉 미션: {html.escape(mission)}</h1>'
        '<p>나의 알뜰 장보기 결과</p></div>',
        unsafe_allow_html=True,
    )
    st.subheader("🛍️ 구매품목")
    for name, price, url, count in items:
        markup = image_html(url, "receipt-image", name)
        st.markdown(
            '<div class="receipt-item">'
            f'{markup}'
            '<div>'
            f'<div class="receipt-name">{html.escape(name)}</div>'
            f'<div class="receipt-info">수량 {count}개 · 단가 {won(price)}</div>'
            '</div>'
            f'<div class="receipt-total">합계 {won(price * count)}</div>'
            '</div>', unsafe_allow_html=True,
        )

    a, b, c = st.columns(3)
    a.metric("주어진 금액", won(budget))
    b.metric("총 사용 금액", won(total))
    c.metric("잔액", won(budget - total))

    st.divider()
    st.subheader("✏️ 구매 이유")
    st.write("왜 이 물건들을 선택했는지 자신의 생각을 적고 [구매 이유 제출하기]를 눌러 주세요.")
    with st.form("reason_form"):
        reason = st.text_area(
            "구매 이유 작성", key="reason_draft", max_chars=700, height=150,
            placeholder="예: 카레를 만들 때 필요한 재료를 선택했어요. 남은 돈도 생각했어요.",
        )
        reason_submit = st.form_submit_button("✅ 구매 이유 제출하기", type="primary",
                                              use_container_width=True)
    if reason_submit:
        if reason.strip():
            st.session_state.submitted_reason = reason.strip()
            st.rerun()
        else:
            st.warning("구매 이유를 작성한 후 제출해 주세요.")

    if st.session_state.submitted_reason:
        st.success("구매 이유를 제출했어요! 이제 결과를 PNG 그림으로 저장할 수 있어요.")
        st.markdown(f'**제출한 구매 이유:** {html.escape(st.session_state.submitted_reason)}')
        if korean_font_path() is None:
            st.error("PNG 저장을 위해 app.py와 같은 폴더에 NanumHumanRegular.ttf를 추가해 주세요.")
        else:
            try:
                with st.spinner("결과 그림을 준비하고 있어요..."):
                    result_png = create_result_png(
                        mission, budget, items, st.session_state.submitted_reason
                    )
                st.download_button(
                    "🖼️ PNG로 다운", data=result_png, mime="image/png",
                    file_name=f"장보기미션_{mission}.png", type="primary",
                    use_container_width=True, on_click="ignore",
                )
                st.caption("이미지 주소가 작동하지 않으면 PNG에 '사진 없음'으로 표시됩니다.")
            except RuntimeError as error:
                st.error(str(error))

    if st.button("← 장바구니 수정하러 가기"):
        st.session_state.page = "shopping"
        st.session_state.submitted_cart = {}
        st.session_state.submitted_reason = ""
        st.session_state.reason_draft = ""
        st.rerun()
else:
    st.session_state.page = "start"
    st.rerun()
