"""초등학생을 위한 장보기 미션 앱 (Streamlit)."""

import csv
import io
import os
import tempfile
from pathlib import Path

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont, ImageOps


st.set_page_config(page_title="장보기 미션", page_icon="🛒", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
CSV_PATH = BASE_DIR / "products.csv"
MISSIONS = {
    "카레 만들기": {"budget": 25_000, "emoji": "🍛", "goal": "맛있는 카레를 만들 재료를 예산 안에서 골라 보세요."},
    "여름캠핑 준비하기": {"budget": 100_000, "emoji": "🏕️", "goal": "여름 캠핑에 필요한 물건을 생각하며 골라 보세요."},
    "친구 생일파티 준비하기": {"budget": 60_000, "emoji": "🎂", "goal": "친구를 위한 생일파티 물건을 알뜰하게 골라 보세요."},
}
FONT_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/"
    "nanumgothic/NanumGothic-Regular.ttf"
)

st.markdown(
    """
    <style>
    .block-container {max-width: 1200px; padding-top: 1.6rem;}
    [data-testid="stMetricValue"] {font-size: 1.7rem;}
    div.stButton > button {font-weight: 650;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False)
def load_products(path: str, modified_time: float):
    """UTF-8 CSV 로드. 가격에 쉼표나 '원'이 있어도 허용."""
    del modified_time  # 파일 수정 시 캐시를 갱신하기 위한 인수
    products = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = set(reader.fieldnames or [])
        image_field = next((s for s in ("이미지 url", "이미지 URL", "이미지_url") if s in fields), None)
        if not {"품명", "가격"}.issubset(fields) or not image_field:
            raise ValueError("CSV 첫 줄은 '품명,가격,이미지 url'이어야 합니다.")
        for row_number, row in enumerate(reader, start=2):
            name = (row.get("품명") or "").strip()
            price_text = (row.get("가격") or "").strip().replace(",", "").replace("원", "")
            if not name and not price_text:
                continue
            try:
                price = int(price_text)
                if not name or price <= 0:
                    raise ValueError
            except ValueError as exc:
                raise ValueError(f"products.csv {row_number}행의 품명/가격을 확인하세요.") from exc
            products.append({"name": name, "price": price, "url": (row.get(image_field) or "").strip()})
    if not products:
        raise ValueError("products.csv에 상품을 한 개 이상 입력하세요.")
    return products


@st.cache_data(show_spinner=False, ttl=3600, max_entries=128)
def fetch_image(image_url: str):
    """결과 PNG에서 사용할 이미지 로드. 실패한 URL은 빈 결과로 처리."""
    if not image_url.startswith(("https://", "http://")):
        return None
    try:
        with requests.get(image_url, timeout=(4, 8), stream=True, headers={"User-Agent": "Mozilla/5.0"}) as response:
            response.raise_for_status()
            payload = bytearray()
            for chunk in response.iter_content(32768):
                payload.extend(chunk)
                if len(payload) > 6_000_000:
                    return None
        with Image.open(io.BytesIO(payload)) as im:
            return ImageOps.exif_transpose(im).convert("RGB")
    except (requests.RequestException, OSError, ValueError):
        return None


def find_korean_font():
    """한글이 실제로 있는 폰트만 사용하며, 없으면 공개 한글 폰트 다운로드."""
    candidates = [
        BASE_DIR / "fonts" / "NanumGothic-Regular.ttf",
        BASE_DIR / "NanumGothic-Regular.ttf",
        Path(tempfile.gettempdir()) / "grocery_mission_NanumGothic.ttf",
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/truetype/nanum/NanumGothicCoding.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
    ]
    for path in candidates:
        if path.exists():
            try:
                font = ImageFont.truetype(str(path), 26)
                if font.getmask("가나다").getbbox() is not None:
                    return str(path)
            except OSError:
                pass

    destination = Path(tempfile.gettempdir()) / "grocery_mission_NanumGothic.ttf"
    temporary = None
    try:
        response = requests.get(FONT_URL, timeout=(5, 20))
        response.raise_for_status()
        if not 100_000 < len(response.content) < 8_000_000:
            raise ValueError("글꼴 크기가 올바르지 않습니다.")
        with tempfile.NamedTemporaryFile(suffix=".ttf", delete=False) as f:
            temporary = Path(f.name)
            f.write(response.content)
        ImageFont.truetype(str(temporary), 26)  # 파일 검증
        os.replace(temporary, destination)
        return str(destination)
    except (requests.RequestException, OSError, ValueError):
        return None
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def wrap_lines(draw, text, font, max_width):
    """한글 문장도 글자 단위로 안전하게 줄바꿈."""
    result = []
    for paragraph in text.splitlines() or [""]:
        current = ""
        for char in paragraph:
            trial = current + char
            if current and draw.textlength(trial, font=font) > max_width:
                result.append(current)
                current = char
            else:
                current = trial
        result.append(current)
    return result


def price_won(amount):
    return f"{amount:,}원"


@st.cache_data(show_spinner=False, ttl=3600, max_entries=64)
def make_result_png(mission, budget, purchased_items, reason):
    """한글 글꼴 + 상품 사진을 PIL로 직접 합성하므로 스크린샷이 필요 없음."""
    font_path = find_korean_font()
    if font_path is None:
        raise RuntimeError("한글 글꼴을 찾을 수 없습니다. 인터넷을 확인하거나 fonts/NanumGothic-Regular.ttf를 추가하세요.")

    title_font = ImageFont.truetype(font_path, 45)
    heading_font = ImageFont.truetype(font_path, 30)
    regular_font = ImageFont.truetype(font_path, 26)
    small_font = ImageFont.truetype(font_path, 23)
    row_font = ImageFont.truetype(font_path, 28)

    width, margin = 1100, 65
    draft = ImageDraw.Draw(Image.new("RGB", (width, 100), "white"))
    reason_lines = wrap_lines(draft, reason, regular_font, width - 2 * margin - 44)
    row_height = 148
    total = sum(price * count for _, price, _, count in purchased_items)
    reason_start = 240 + 51 + row_height * len(purchased_items) + 9 + 200 + 53
    reason_box_bottom = reason_start + 34 + max(1, len(reason_lines)) * 41
    height = reason_box_bottom + 120
    image = Image.new("RGB", (width, height), "#f7fafc")
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((34, 30, width - 34, 205), radius=26, fill="#dceefb")
    draw.text((margin, 54), f"미션: {mission}", font=title_font, fill="#123c56")
    draw.text((margin, 129), "나의 장보기 결과", font=heading_font, fill="#285e7d")

    y = 240
    draw.text((margin, y), "구매한 물건", font=heading_font, fill="#243447")
    y += 51
    for name, price, url, count in purchased_items:
        draw.rounded_rectangle((margin - 15, y - 5, width - margin + 15, y + 133), radius=17, fill="white")
        src = fetch_image(url)
        if src:
            thumb = ImageOps.contain(src, (155, 116), method=Image.Resampling.LANCZOS)
            px = margin + (155 - thumb.width) // 2
            py = y + 5 + (116 - thumb.height) // 2
            image.paste(thumb, (px, py))
        else:
            draw.rounded_rectangle((margin, y + 5, margin + 155, y + 121), radius=12, fill="#e8eef4")
            draw.text((margin + 15, y + 48), "사진 없음", font=small_font, fill="#52687c")
        text_x = margin + 185
        name_display = name
        while draw.textlength(name_display, font=row_font) > 440 and len(name_display) > 1:
            name_display = name_display[:-2] + "…"
        draw.text((text_x, y + 10), name_display, font=row_font, fill="#1f2937")
        draw.text((text_x, y + 67), f"{price_won(price)} × {count}개", font=small_font, fill="#586574")
        draw.text((width - margin, y + 67), price_won(price * count), anchor="ra", font=row_font, fill="#164e63")
        y += row_height

    y += 9
    draw.rounded_rectangle((margin - 15, y, width - margin + 15, y + 160), radius=20, fill="#ecf8f2")
    draw.text((margin + 14, y + 23), f"예산  {price_won(budget)}", font=regular_font, fill="#254a3d")
    draw.text((width - margin - 14, y + 23), f"사용  {price_won(total)}", anchor="ra", font=regular_font, fill="#254a3d")
    draw.text((margin + 14, y + 90), f"남은 돈  {price_won(budget - total)}", font=heading_font, fill="#0f6b55")
    y += 200

    draw.text((margin, y), "내가 이 물건을 고른 이유", font=heading_font, fill="#243447")
    y += 53
    reason_bottom = y + 34 + len(reason_lines) * 41
    draw.rounded_rectangle((margin - 15, y - 10, width - margin + 15, reason_bottom), radius=18, fill="white")
    for line in reason_lines:
        draw.text((margin + 14, y + 6), line, font=regular_font, fill="#344054")
        y += 41
    draw.text((margin, height - 53), "알뜰한 장보기 미션 완료!", font=small_font, fill="#52687c")

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def start_mission(mission):
    st.session_state.mission = mission
    st.session_state.stage = "shopping"
    st.session_state.cart = {}
    st.session_state.reason = ""
    for key in list(st.session_state):
        if str(key).startswith("qty_"):
            del st.session_state[key]


# ---------------------------------- 앱 상태 ----------------------------------
for state_key, default_value in {
    "stage": "start", "mission": None, "cart": {}, "reason": ""
}.items():
    if state_key not in st.session_state:
        st.session_state[state_key] = default_value

if not CSV_PATH.exists():
    st.error("products.csv 파일을 app.py와 같은 폴더에 넣어 주세요.")
    st.stop()
try:
    products = load_products(str(CSV_PATH), CSV_PATH.stat().st_mtime)
except (OSError, ValueError) as error:
    st.error(str(error))
    st.stop()


# ---------------------------------- 시작화면 ----------------------------------
if st.session_state.stage == "start":
    st.title("🛒 알뜰살뜰 장보기 미션")
    st.write("미션을 선택하고, 예산에 맞게 물건을 골라 보세요!")
    st.info("가격을 비교하고, 필요한 물건을 고민하는 경제 활동 연습이에요.")
    columns = st.columns(3)
    for column, (mission, info) in zip(columns, MISSIONS.items()):
        with column:
            with st.container(border=True):
                st.header(f"{info['emoji']} {mission}")
                st.metric("사용할 수 있는 돈", price_won(info["budget"]))
                st.write(info["goal"])
                st.button("이 미션 시작하기", key=f"start_{mission}", type="primary",
                          use_container_width=True, on_click=start_mission, args=(mission,))


# ---------------------------------- 쇼핑화면 ----------------------------------
elif st.session_state.stage == "shopping":
    mission = st.session_state.mission
    info = MISSIONS[mission]
    budget = info["budget"]
    st.title(f"{info['emoji']} {mission}")
    st.write(info["goal"])
    if st.button("← 미션 선택으로 돌아가기"):
        st.session_state.stage = "start"
        st.rerun()

    cart = st.session_state.cart
    st.subheader("🏬 우리 반 장보기 마트")
    for offset in range(0, len(products), 3):
        columns = st.columns(3)
        for col, idx in zip(columns, range(offset, min(offset + 3, len(products)))):
            item = products[idx]
            key = f"qty_{idx}"
            if key not in st.session_state:
                st.session_state[key] = 1
            with col:
                with st.container(border=True):
                    if item["url"]:
                        try:
                            st.image(item["url"], use_container_width=True)
                        except Exception:
                            st.info("🖼️ 상품 이미지 준비 중")
                    else:
                        st.info("🖼️ 상품 이미지 준비 중")
                    st.markdown(f"**{item['name']}**")
                    st.write(f"가격: **{price_won(item['price'])}**")
                    minus, qty, plus = st.columns([1, 1, 1])
                    with minus:
                        if st.button("−", key=f"minus_{idx}", disabled=st.session_state[key] <= 1,
                                     use_container_width=True):
                            st.session_state[key] -= 1
                            st.rerun()
                    with qty:
                        st.markdown(f"<p style='text-align:center;padding-top:8px'><b>{st.session_state[key]}</b></p>",
                                    unsafe_allow_html=True)
                    with plus:
                        if st.button("+", key=f"plus_{idx}", disabled=st.session_state[key] >= 30,
                                     use_container_width=True):
                            st.session_state[key] += 1
                            st.rerun()
                    if st.button("🛒 장바구니 담기", key=f"add_{idx}", use_container_width=True):
                        cart[idx] = cart.get(idx, 0) + st.session_state[key]
                        st.session_state[key] = 1
                        st.rerun()

    st.divider()
    st.subheader("🧺 나의 장바구니")
    total = sum(products[idx]["price"] * count for idx, count in cart.items())
    remaining = budget - total
    top1, top2, top3 = st.columns(3)
    top1.metric("미션 예산", price_won(budget))
    top2.metric("사용한 금액", price_won(total))
    top3.metric("남은 돈", price_won(remaining))
    st.progress(min(total / budget, 1.0))

    if not cart:
        st.info("아직 담은 물건이 없어요. 위에서 물건을 담아 보세요!")
    else:
        for idx, count in list(cart.items()):
            product = products[idx]
            title_col, amount_col, delete_col = st.columns([5, 3, 1])
            title_col.write(f"**{product['name']}** × {count}개")
            amount_col.write(price_won(product["price"] * count))
            if delete_col.button("삭제", key=f"remove_{idx}"):
                del cart[idx]
                st.rerun()
    over_budget = total > budget
    if over_budget:
        st.error(f"🚨 예산을 {price_won(total - budget)} 초과했어요. 물건을 삭제하거나 수량을 줄여 주세요.")
    elif cart:
        st.success("✅ 예산 안에 들어왔어요. 준비가 되었으면 제출해 보세요!")
    if st.button("📮 제출하기", type="primary", use_container_width=True,
                 disabled=over_budget or not cart):
        # 결과 화면 진입은 이 버튼에서만 허용합니다.
        st.session_state.submitted_cart = dict(cart)
        st.session_state.stage = "result"
        st.rerun()


# ---------------------------------- 결과화면 ----------------------------------
elif st.session_state.stage == "result":
    mission = st.session_state.mission
    budget = MISSIONS[mission]["budget"]
    submitted_cart = st.session_state.get("submitted_cart", {})
    if not submitted_cart:
        st.session_state.stage = "shopping"
        st.rerun()
    items = tuple(
        (products[idx]["name"], products[idx]["price"], products[idx]["url"], count)
        for idx, count in submitted_cart.items()
    )
    spent = sum(price * count for _, price, _, count in items)
    st.title(f"🎉 미션 완료: {mission}")
    st.subheader("내가 구매한 물건")
    for name, price, url, count in items:
        with st.container(border=True):
            preview_col, details_col = st.columns([1, 4])
            with preview_col:
                if url:
                    try:
                        st.image(url, use_container_width=True)
                    except Exception:
                        st.write("🖼️ 이미지 없음")
            with details_col:
                st.markdown(f"**{name}**")
                st.write(f"단가 {price_won(price)} × {count}개 = **{price_won(price * count)}**")
    col1, col2, col3 = st.columns(3)
    col1.metric("예산", price_won(budget))
    col2.metric("사용한 금액", price_won(spent))
    col3.metric("남은 돈", price_won(budget - spent))
    st.divider()
    reason = st.text_area(
        "✏️ 이 물건들을 구매한 이유를 적어 보세요.",
        key="reason", max_chars=400, height=135,
        placeholder="예: 카레를 만들 때 필요한 재료라서 골랐어요. 예산도 고려했어요.",
    )
    if reason.strip():
        try:
            with st.spinner("결과 그림을 만드는 중이에요..."):
                image_data = make_result_png(mission, budget, items, reason.strip())
            st.download_button("🖼️ 그림으로 저장 (PNG)", data=image_data,
                               file_name=f"장보기미션_{mission}.png", mime="image/png",
                               type="primary", use_container_width=True, on_click="ignore")
            st.caption("물건 사진을 불러올 수 없는 경우 그림에는 '사진 없음'으로 표시됩니다.")
        except RuntimeError as error:
            st.error(str(error))
    else:
        st.info("구매 이유를 작성하면 '그림으로 저장' 버튼이 나타납니다.")
    if st.button("← 장바구니 수정하기"):
        st.session_state.stage = "shopping"
        st.rerun()
