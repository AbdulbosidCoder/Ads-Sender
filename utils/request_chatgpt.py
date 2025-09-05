# gpt_router.py — full rewrite (multi-ad, route by ORIGIN; null ids if topic not found)
from __future__ import annotations
import os, json, re, hashlib, asyncio
from typing import Any, Dict, Optional, List, Tuple
from dotenv import load_dotenv
from openai import OpenAI
from loader import db

load_dotenv()
_openai_key = os.getenv("OPENAI_API_KEY")
_openai_client = OpenAI(api_key=_openai_key) if _openai_key else None

# ---------------------------
# Utils
# ---------------------------
def _ns(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def text_hash(s: str) -> str:
    return hashlib.sha256(_ns(s).lower().encode("utf-8")).hexdigest()

def _only_digits_plus_list(nums: List[str]) -> List[str]:
    out: List[str] = []
    for x in nums or []:
        x = re.sub(r"[^\d\+\s]", "", x or "").strip()
        x = re.sub(r"\s+", "", x)
        if x:
            out.append(x)
    seen = set(); uniq = []
    for x in out:
        if x not in seen:
            uniq.append(x); seen.add(x)
    return uniq

def _flat(s: Optional[str]) -> str:
    s = (s or "")
    s = (s.replace("’","'")
           .replace("ʻ","'")
           .replace("ʼ","'")
           .replace("‘","'")
           .replace("`","'")
           .lower())
    s = re.sub(r"[\s_\-']", "", s)
    return s

# ---------------------------
# REGION aliases (city/district -> canonical region)
# ---------------------------
_REGION_ALIASES: Dict[str, List[str]] = {
    "TOSHKENT_SHAHRI": ["Toshkent shahar","Toshkent shahri","Tashkent city","Тошкент шахар","Тошкент шаҳри","Ташкент сити"],
    "TOSHKENT": [
        "Toshkent","Tashkent","Тошкент","Ташкент","Chirchiq","Angren","Olmaliq","Nurafshon","Bekobod",
        "Yangiyo‘l","Piskent","Ohangaron","Qibray","Zangiota","Oqqo‘rg‘on","Parkent","Bo‘stonliq",
        "Yuqori Chirchiq","Quyi Chirchiq","Quyichirchiq","Чирчиқ","Ангрен","Олмалиқ","Нурафшон","Бекобод",
        "Янгийўл","Пискент","Оҳангарон","Қибрай","Зангиота","Оққўрғон","Паркент","Бўстонлиқ","Юқори Чирчиқ","Қуйи Чирчиқ"
    ],
    "ANDIJON": ["Andijon","Андижон","Андижан","Asaka","Xo‘jaobod","Jalaquduq","Marhamat","Paxtaobod","Shahrixon"],
    "FARGONA": [
        "Farg‘ona","Fargona","Fergana","Фарғона","Фергана","Qo‘qon","Qoqon","Қўқон","Marg‘ilon","Margilon","Марғилон",
        "Oltiariq","Buvayda","Bag‘dod","Dang‘ara","Rishton","Uchko‘prik","Uchkoprik","Олтийарик","Бувайда","Боғдод","Данғара","Риштон","Учкўприк"
    ],
    "NAMANGAN": ["Namangan","Наманган","Chust","Kosonsoy","Pop","To‘raqo‘rg‘on","Torako‘rgon","Uychi","Чуст","Косонсой","Поп","Тўрақўрғон","Уйчи"],
    "SAMARQAND": ["Samarqand","Samarkand","Самарқанд","Самарканд","Kattaqo‘rg‘on","Urgut","Pastdarg‘om","Nurobod"],
    "BUXORO": ["Buxoro","Bukhara","Бухоро","Бухара","G‘ijduvon","Gijduvon","Kogon","Vobkent","Ғиждувон","Гиждуван","Когон","Вобкент"],
    "NAVOIY": ["Navoiy","Навоий","Zarafshon","Qiziltepa","Konimex","Kanimex","Зарафшон","Қизилтепа","Конимех","Канимех","Навои"],
    "JIZZAX": ["Jizzax","Жиззах","Zomin","G‘allaorol","Gallaorol","Arnasoy","Зомин","Ғаллаорол","Арнасой","Джизак"],
    "SIRDARYO": ["Sirdaryo","Сирдарё","Guliston","Yangiyer","Boyovut","Sardoba","Shirin","Гулистон","Янгиер","Бўёвут","Сардоба","Ширин","Сырдарья"],
    "QASHQADARYO": ["Qashqadaryo","Қашқадарё","Qarshi","Shahrisabz","Yakkabog‘","Yakkabog","Kasbi","Қарши","Шаҳрисабз","Яккабоғ","Яккабог","Касби","Кашкадарья"],
    "SURXONDARYO": ["Surxondaryo","Сурхондарё","Termiz","Denov","Sherobod","Boysun","Термиз","Денов","Шеробод","Бойсун","Сурхандарья"],
    "XORAZM": ["Xorazm","Хоразм","Xiva","Urganch","Xonqa","Gurlan","Хива","Урганч","Хонқа","Гурлан","Хорезм","Ургенч"],
    "QORAQALPOGISTON": ["Qoraqalpog‘iston","Qoraqalpogiston","Қорақалпоғистон","Karakalpakstan","Nukus","Xo‘jayli","Mo‘ynoq","Muynak","Taxtako‘pir","Taxtakopir","Каракалпакстан","Нукус","Хўжайли","Мўйноқ","Муйнак","Тахтакўпир"],
}
_ALIAS2CANON: Dict[str, str] = {}
for canon, aliases in _REGION_ALIASES.items():
    for a in aliases + [canon]:
        _ALIAS2CANON[_flat(a)] = canon

def _infer_region_from_place(place_text: str) -> Optional[str]:
    """Map any city/district text to a canonical region (case/space/apostrophe insensitive)."""
    s = _flat(place_text)
    if not s:
        return None
    if s in _ALIAS2CANON:
        return _ALIAS2CANON[s]
    for alias_flat, canon in _ALIAS2CANON.items():
        if alias_flat and alias_flat in s:
            return canon
    return None

# ---------------------------
# SYSTEM prompt (multi-ad, strict same-group topic lookup, route by ORIGIN)
# ---------------------------
SYSTEM = """
You are a logistics ads EXTRACTOR & FORMATTER. Return ONLY valid JSON (no code fences, no prose).

GOAL
- Split a single incoming message into 0..N ad items.
- For each item: extract fields, build formatted texts, and choose a topic_id ONLY from the given catalog for the SAME group.
- Never invent IDs. Never switch to another group.
- IMPORTANT: Route by ORIGIN (pickup place). Derive `region` from ORIGIN first; if ORIGIN is missing, you MAY fallback to DESTINATION.
- If no suitable topic for the region exists in the provided catalog: mark the item as not ok with reason="no_region_topic" AND leave BOTH group_id and topic_id null.

INPUT LANGUAGE
- Uzbek (Latin/Cyrillic), Russian, or mixed. Treat all apostrophes equally: ’ ʻ ʼ ‘ ` '
- Messages may be multiline and contain multiple ads.

SPLITTING RULES (multi-ad)
- HEADER mode: If the first paragraph contains multiple pairs like "A - B", "A — B", "A -> B", "A → B" (separated by commas/semicolons/newlines), create one item per pair. The rest of the message is the shared BODY and applies to all items.
- Otherwise: Split by phone-line boundaries (a line that looks like "+998...") or by 2+ consecutive blank lines. Each block is an item.
- Discard empty/noise-only blocks.

DEDUP RULE
- Items are duplicates when this canonical key is identical: lower(normalize(origin)) | lower(normalize(destination)) | lower(normalize(product_or_extra)) | lower(normalize(vehicle)) | sorted(phones).
- Keep the first, drop later duplicates.

FIELDS TO EXTRACT (never hallucinate)
- origin (str|null)
- destination (str|null)
- vehicle (str|null)
- product_or_extra (str|null)
- price (str|null)
- phones (list[str]) — keep only digits and '+'
- username (str|null) — Telegram handle WITHOUT leading '@' (a fallback is provided in payload)
- contact_used: "phones" | "username" | null (apply CONTACT RULE)
- region (str|null) — canonical region derived from ORIGIN (fallback: DESTINATION). Used ONLY for topic matching; do not normalize origin/destination strings themselves.

DESTINATION/ORIGIN HINTS
- Recognize: "A - B" / "A — B" / "A -> B" / "A → B"; "A dan B ga|gacha|tomon|sari"; "from A to B"; hashtags like "#ANDIJON".
- Multiline: one line with "...dan" and another with "...ga..." → first is origin, second is destination.
- If multiple place names appear, take the FIRST as origin and the LAST as destination.
- If only one confident place appears, treat it as destination (origin=null).

REGION MAP (ORIGIN → region)
Canonical region keys (UPPERCASE): TOSHKENT_SHAHRI, TOSHKENT, ANDIJON, FARGONA, NAMANGAN, SAMARQAND, BUXORO, NAVOIY, JIZZAX, SIRDARYO, QASHQADARYO, SURXONDARYO, XORAZM, QORAQALPOGISTON.

TOPIC SELECTION (catalog)
- Select topic_id ONLY from the provided catalog. Never invent IDs.
- Match topic name to the canonical region (case/spacing/apostrophes ignored). Prefer exact match; else substring.
- If a matching topic is found, set group_id to src_group_id and topic_id to that topic.
- If NO matching topic exists → item.ok=false, reason="no_region_topic", and set BOTH group_id AND topic_id to null.

CONTACT RULE
- If at least one phone exists → use all phones (comma-separated) in ☎️ line; contact_used="phones".
- Else if NO phone but a fallback username is provided in the payload → use that username for the ☎️ line; contact_used="username".
- Else → item.ok=false, reason="no_contact".

FORMATTING (for each item)
- Title: "{ORIGIN_UPPER} - {DEST_UPPER}". If origin missing, use "NOMA'LUM".
- Then, in order (omit empty):
  1) "🚛 {vehicle}"
  2) "💬 {product_or_extra}"
  3) "💰 {price}"
  4) "☎️ {contact}"
  5) "👤 Aloqaga_chiqish {username}" (only if username exists)
  6) "#{DEST_HASHTAG}" (destination uppercased, spaces removed)
  7) 14 dashes: "──────────────"
  8) "Boshqa yuklar: @{group_username}" (prepend '@' if missing)

OUTPUT (only JSON)
{
  "ok": <true|false>,        // true if at least one item ok=true
  "items": [
    {
      "ok": <true|false>,
      "reason": "<string|null>",    // e.g., "missing_destination" | "no_region_topic" | "no_contact"
      "group_id": <int|null>,        // set ONLY if topic was found; otherwise null
      "topic_id": <int|null>,        // from catalog or null
      "data": {
        "origin": "<str|null>",
        "destination": "<str|null>",
        "vehicle": "<str|null>",
        "product_or_extra": "<str|null>",
        "price": "<str|null>",
        "phones": ["<str>", ...],
        "username": "<str|null>",   // WITHOUT '@'
        "contact_used": "<phones|username|null>",
        "region": "<REGION|null>"
      },
      "short_text": "<str>",
      "full_text": "<str>"
    }
  ]
}
- Return ONLY JSON. No explanations.
"""

# ---------------------------
# Formatting helper (server-side safety)
# ---------------------------
def _format_final(
    *,
    origin: Optional[str],
    destination: str,
    vehicle: Optional[str],
    product_or_extra: Optional[str],
    price: Optional[str],
    phones: Optional[List[str]],
    username: Optional[str],  # WITH leading @
    group_username: Optional[str],
) -> str:
    origin_disp = (origin or "").strip() or "NOMA'LUM"
    title = f"{origin_disp.upper()} - {destination.upper()}".strip(" -")
    lines: List[str] = [title, ""]

    if vehicle:
        lines.append(f"🚛 {vehicle}")
    if product_or_extra:
        lines.append(f"💬 {product_or_extra}")
    if price:
        lines.append(f"💰 {price}")

    clean_phones = _only_digits_plus_list(phones or [])
    if clean_phones:
        lines.append(f"☎️ {', '.join(clean_phones)}")
    elif username:
        lines.append(f"☎️ {username}")
        lines.append(f"👤 Aloqaga_chiqish {username}")
    else:
        return ""  # reject: no contact

    tag = re.sub(r"[^A-Za-z0-9\u0400-\u04FFʼʻ’ ]+", "", destination or "").replace(" ", "").upper()
    if tag:
        lines.append(f"\n#{tag}")

    gu = (group_username or "lorry_yuk_markazi").strip()
    if not gu.startswith("@"):
        gu = "@" + gu
    lines.append("➖" * 14)
    lines.append(f"Boshqa yuklar: {gu}")
    return "\n".join(lines)

# ---------------------------
# Topic selection safety (server-side)
# ---------------------------
def _pick_topic_by_region(topics: List[Dict[str, Any]], region_canon: Optional[str]) -> Optional[Dict[str, Any]]:
    if not region_canon:
        return None
    rflat = _flat(region_canon)
    exact = None; contains = None
    for t in topics or []:
        nflat = _flat(t.get("name") or "")
        if nflat == rflat:
            exact = t; break
        if rflat in nflat or nflat in rflat:
            contains = contains or t
    return exact or contains

# ---------------------------
# LLM call + robust post-processing
# ---------------------------
async def gpt_format_and_route(
    *,
    src_group_db_id: int,
    message_text: str,
    fallback_username: Optional[str] = None,  # may have leading @
    group_username: Optional[str] = None,     # may have leading @
) -> Dict[str, Any]:
    """
    Multi-ad capable router (route by ORIGIN).
    - LLM splits/extracts/formats and chooses topic within the SAME group when region exists.
    - Server-side validates: never switch group; if no topic for region, both ids stay null.
    - Returns { ok, items: [...] }.
    """
    topics = db.list_topics_by_group(src_group_db_id) or []
    catalog = [{"group_id": src_group_db_id, "topic_id": t["id"], "name": t.get("name") or ""} for t in topics]

    payload = {
        "message": _ns(message_text),
        "src_group_id": src_group_db_id,
        "catalog": catalog,
        "fallback_username": (fallback_username or "").lstrip("@"),
        "group_username": (group_username or "lorry_yuk_markazi").lstrip("@"),
    }

    items: List[Dict[str, Any]] = []

    # -------- LLM path --------
    if _openai_client:
        try:
            resp = await asyncio.to_thread(
                lambda: _openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    temperature=0,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                )
            )
            raw = resp.choices[0].message.content
            parsed = json.loads(raw) if raw else {}
            llm_items = parsed.get("items") if isinstance(parsed, dict) else None
            if isinstance(llm_items, list):
                items = llm_items
        except Exception:
            items = []

    # -------- Deterministic fallback (simple single-block heuristic) --------
    if not items:
        def _find_hits(txt: str) -> List[str]:
            mflat = _flat(txt)
            hits: List[str] = []
            for alias_flat in _ALIAS2CANON.keys():
                if alias_flat and alias_flat in mflat:
                    hits.append(alias_flat)
            seen=set(); out=[]
            for h in hits:
                if h not in seen:
                    out.append(h); seen.add(h)
            return out

        msg = _ns(message_text)
        # Try A - B pattern
        m = re.search(r"([A-Za-z\u0400-\u04FFʼʻ’`' ]+?)\s*(?:-+|—+|->|→)\s*([A-Za-z\u0400-\u04FFʼʻ’`' ]+)", msg)
        if m:
            origin = _ns(m.group(1)); destination = _ns(m.group(2))
        else:
            # hits heuristic: first -> origin, last -> destination
            hits = _find_hits(msg)
            origin = hits[0] if hits else None
            destination = hits[-1] if len(hits) >= 2 else None

        phones = _only_digits_plus_list(re.findall(r"\+?\d[\d\-\s]{6,}\d", msg))
        username_at = (fallback_username or "").lstrip("@")
        username_at = f"@{username_at}" if username_at else None

        # Region by ORIGIN (fallback: destination)
        region = _infer_region_from_place(origin or "") if origin else _infer_region_from_place(destination or "")
        topic = _pick_topic_by_region(topics, region)

        # If topic exists → set ids, else ids must be null
        if (origin or destination) and (phones or username_at) and topic:
            full = _format_final(
                origin=origin,
                destination=destination or (origin or "NOMA'LUM"),
                vehicle=None,
                product_or_extra=msg,
                price=None,
                phones=phones,
                username=username_at,
                group_username=group_username,
            )
            items = [{
                "ok": True,
                "reason": None,
                "group_id": int(src_group_db_id),
                "topic_id": int(topic["id"]),
                "data": {
                    "origin": origin,
                    "destination": destination,
                    "vehicle": None,
                    "product_or_extra": msg,
                    "price": None,
                    "phones": phones,
                    "username": (fallback_username or "").lstrip("@") if fallback_username else None,
                    "contact_used": "phones" if phones else "username",
                    "region": region,
                },
                "short_text": full,
                "full_text": full,
            }]
        else:
            # topic yo'q yoki boshqa talab bajarilmagan
            reason = "no_region_topic" if (region and not topic) else ("missing_destination" if not (origin or destination) else ("no_contact" if not (phones or username_at) else "no_region_topic"))
            items = [{
                "ok": False,
                "reason": reason,
                "group_id": None,
                "topic_id": None,
                "data": {
                    "origin": origin,
                    "destination": destination,
                    "vehicle": None,
                    "product_or_extra": msg,
                    "price": None,
                    "phones": phones,
                    "username": (fallback_username or "").lstrip("@") if fallback_username else None,
                    "contact_used": "phones" if phones else ("username" if username_at else None),
                    "region": region,
                },
                "short_text": "",
                "full_text": "",
            }]

    # -------- Server-side safety & normalization over returned items --------
    out_items: List[Dict[str, Any]] = []
    valid_topic_ids = {int(t["id"]) for t in topics}

    for it in items:
        it = it or {}
        data = it.get("data") or {}

        origin = _ns(data.get("origin")) or None
        destination = _ns(data.get("destination")) or None
        vehicle = data.get("vehicle")
        product_or_extra = data.get("product_or_extra")
        price = data.get("price")
        phones = _only_digits_plus_list(data.get("phones") or [])

        # username in payload is WITHOUT '@'
        username_raw = data.get("username")
        if username_raw:
            username_raw = username_raw.lstrip("@")
        username_at = f"@{username_raw}" if username_raw else (f"@{(fallback_username or '').lstrip('@')}" if fallback_username else None)
        has_contact = bool(phones) or bool(username_at)

        group_id = it.get("group_id")
        topic_id = it.get("topic_id")

        # Recompute/ensure region from ORIGIN (fallback DEST)
        region = data.get("region") or _infer_region_from_place(origin or "") or _infer_region_from_place(destination or "")

        # If topic_id invalid/missing -> try to pick by region
        if not topic_id or (isinstance(topic_id, int) and topic_id not in valid_topic_ids):
            t = _pick_topic_by_region(topics, region)
            topic_id = int(t["id"]) if t else None

        # If topic exists → enforce same-group id; else BOTH ids must be null
        if topic_id is not None:
            group_id = int(src_group_db_id)
        else:
            group_id = None

        # No destination is allowed? We still need a DEST string for formatting hashtag & title.
        # If destination missing but origin present — use origin as fallback for title hashtag.
        dest_for_format = destination or origin or "NOMA'LUM"

        # Validate minimal requirements
        if topic_id is None:
            out_items.append({
                "ok": False,
                "reason": "no_region_topic",
                "group_id": None,
                "topic_id": None,
                "data": {
                    **data,
                    "origin": origin,
                    "destination": destination,
                    "phones": phones,
                    "username": username_raw,
                    "contact_used": "phones" if phones else ("username" if username_at else None),
                    "region": region,
                },
                "short_text": "",
                "full_text": "",
            })
            continue

        if not has_contact:
            out_items.append({
                "ok": False,
                "reason": "no_contact",
                "group_id": group_id,
                "topic_id": topic_id,
                "data": {
                    **data,
                    "origin": origin,
                    "destination": destination,
                    "phones": phones,
                    "username": username_raw,
                    "contact_used": None,
                    "region": region,
                },
                "short_text": "",
                "full_text": "",
            })
            continue

        # Build/repair formatted texts
        short_text = (it.get("short_text") or "").strip()
        full_text  = (it.get("full_text") or "").strip()

        def needs_rebuild(s: str) -> bool:
            return (not s) or ("Boshqa yuklar:" not in s) or ("#" not in s) or ("☎️" not in s)

        if needs_rebuild(short_text):
            short_text = _format_final(
                origin=origin,
                destination=dest_for_format,
                vehicle=vehicle,
                product_or_extra=product_or_extra,
                price=price,
                phones=phones,
                username=username_at,
                group_username=group_username,
            )
        if needs_rebuild(full_text):
            full_text = _format_final(
                origin=origin,
                destination=dest_for_format,
                vehicle=vehicle,
                product_or_extra=product_or_extra,
                price=price,
                phones=phones,
                username=username_at,
                group_username=group_username,
            )

        if not short_text or not full_text:
            out_items.append({
                "ok": False,
                "reason": "no_contact",
                "group_id": group_id,
                "topic_id": topic_id,
                "data": {
                    **data,
                    "origin": origin,
                    "destination": destination,
                    "phones": phones,
                    "username": username_raw,
                    "contact_used": "phones" if phones else "username",
                    "region": region,
                },
                "short_text": "",
                "full_text": "",
            })
            continue

        out_items.append({
            "ok": True,
            "reason": None,
            "group_id": group_id,
            "topic_id": topic_id,
            "data": {
                **data,
                "origin": origin,
                "destination": destination,
                "vehicle": vehicle,
                "product_or_extra": product_or_extra,
                "price": price,
                "phones": phones,
                "username": username_at.lstrip("@") if username_at else None,
                "contact_used": "phones" if phones else "username",
                "region": region,
            },
            "short_text": short_text,
            "full_text": full_text,
        })

    return {"ok": any(it.get("ok") for it in out_items), "items": out_items}

# Back-compat helper (returns single item if exactly one ok item)
async def gpt_format_and_route_single(
    *,
    src_group_db_id: int,
    message_text: str,
    fallback_username: Optional[str] = None,
    group_username: Optional[str] = None,
) -> Dict[str, Any]:
    res = await gpt_format_and_route(
        src_group_db_id=src_group_db_id,
        message_text=message_text,
        fallback_username=fallback_username,
        group_username=group_username,
    )
    items = res.get("items") or []
    if len(items) == 1:
        return items[0]
    return res
