import sqlite3
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import database
from emojis import (
    BALANCE, CHECK, SUCCESS, ERROR, STARS, PERSONAL, PUBLIC,
    BACK, CANCEL, CONFIRM, REJECT, WAIT, LINK, PROFILE,
    BAN, UNBAN, EDIT, ADMIN, REQUESTS, STATS, USERS,
    PLUS, MINUS, PAID, WALLET,
)

router = Router()
ADMIN_IDS = [8959461245]


class AdminStates(StatesGroup):
    wait_for_amount = State()


# ---------------------------------------------------------------------------
# Клавиатура профиля (в кнопках — обычные эмодзи, премиум там не работает)
# ---------------------------------------------------------------------------

def get_check_kb(target_id: str, is_banned: bool, has_vip: bool) -> InlineKeyboardMarkup:
    target_id = str(target_id).replace("@", "")

    ban_btn = (
        InlineKeyboardButton(text="🔓 Разбанить", callback_data=f"check_unban_{target_id}", style="success")
        if is_banned
        else InlineKeyboardButton(text="🚫 Забанить", callback_data=f"check_ban_{target_id}", style="danger")
    )

    vip_btn = (
        InlineKeyboardButton(text="❌ Снять VIP", callback_data=f"check_revip_{target_id}", style="danger")
        if has_vip
        else InlineKeyboardButton(text="👑 Выдать VIP", callback_data=f"check_givip_{target_id}", style="success")
    )

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💰 +dC",    callback_data=f"check_add_balance_{target_id}", style="success"),
            InlineKeyboardButton(text="💸 −dC",    callback_data=f"check_rem_balance_{target_id}", style="danger"),
        ],
        [
            InlineKeyboardButton(text="⭐️ +Звёзды", callback_data=f"check_add_stars_{target_id}", style="success"),
            InlineKeyboardButton(text="✂️ −Звёзды",  callback_data=f"check_rem_stars_{target_id}", style="danger"),
        ],
        [vip_btn, ban_btn],
        [
            InlineKeyboardButton(text="🔄 Обновить",          callback_data=f"check_refresh_{target_id}", style="primary"),
            InlineKeyboardButton(text="🗑 Обнулить ⭐️ ВСЕМ",  callback_data="check_resetallstars", style="danger"),
        ],
    ])


# ---------------------------------------------------------------------------
# Текст карточки пользователя (премиум-эмодзи)
# ---------------------------------------------------------------------------

def build_profile_text(target_id: str, name: str, balance: int, stars: int,
                        is_banned: bool, has_vip: bool) -> str:
    unit_icon  = database.get_setting("plugs_icon", BALANCE)
    stars_icon = database.get_setting("stars_icon", STARS)

    fmt_balance = f"{balance:,}".replace(",", " ")
    fmt_stars   = f"{stars:,}".replace(",", " ")
    status_line = f"{BAN} Заблокирован" if is_banned else f"{SUCCESS} Активен"
    vip_line    = "💎 Есть" if has_vip else "❌ Нет"

    return (
        f"┌─ {PROFILE} <b>{name}</b>\n"
        f"├─ 🆔 <code>@{target_id}</code>\n"
        f"├─ {unit_icon} dC: <b>{fmt_balance}</b>\n"
        f"├─ {stars_icon} Звёзды: <b>{fmt_stars}</b>\n"
        f"├─ {STATS} Статус: {status_line}\n"
        f"└─ 👑 VIP: {vip_line}"
    )


# ---------------------------------------------------------------------------
# Работа со звёздочками (колонка pl_gold — именно там хранит cmd_b.py)
# ---------------------------------------------------------------------------

def _get_stars(user_id_fmt: str) -> int:
    try:
        conn = sqlite3.connect(database.DB_PATH, timeout=15)
        c = conn.cursor()
        c.execute("SELECT pl_gold FROM users WHERE user_id = ?", (user_id_fmt,))
        row = c.fetchone()
        conn.close()
        return row[0] if row and row[0] is not None else 0
    except Exception:
        return 0


def _update_stars(user_id_fmt: str, delta: int):
    try:
        conn = sqlite3.connect(database.DB_PATH, timeout=15)
        c = conn.cursor()
        c.execute(
            "UPDATE users SET pl_gold = MAX(0, COALESCE(pl_gold, 0) + ?) WHERE user_id = ?",
            (delta, user_id_fmt),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _reset_all_stars():
    try:
        conn = sqlite3.connect(database.DB_PATH, timeout=15)
        c = conn.cursor()
        c.execute("UPDATE users SET pl_gold = 0")
        conn.commit()
        conn.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# /чек — просмотр профиля пользователя
# ---------------------------------------------------------------------------

@router.message(Command("чек", "Чек"), F.from_user.id.in_(ADMIN_IDS))
async def cmd_check(message: Message, command: CommandObject):
    if not command.args:
        return await message.answer(
            f"{HELP} Введите ID или @username:\n"
            "<code>/чек 1234567</code>  или  <code>/чек @username</code>",
            parse_mode="HTML",
        )

    target_arg = command.args.strip().replace("@", "")

    if target_arg.isdigit():
        search_id  = f"@{target_arg}"
        display_id = target_arg
    else:
        row = database.get_user_by_username(target_arg)
        if not row:
            return await message.answer(
                f"{ERROR} Юзернейм <code>@{target_arg}</code> не найден в базе.",
                parse_mode="HTML",
            )
        search_id  = row[0]
        display_id = search_id.replace("@", "")

    user_data = database.get_user_info(search_id)
    if not user_data:
        return await message.answer(
            f"{ERROR} Пользователь <code>{search_id}</code> не найден.",
            parse_mode="HTML",
        )

    name, balance, _, _ = user_data
    stars     = _get_stars(search_id)
    is_banned = database.is_user_banned(display_id)
    has_vip   = database.get_vip_status(display_id)

    await message.answer(
        build_profile_text(display_id, name, balance, stars, is_banned, has_vip),
        reply_markup=get_check_kb(display_id, is_banned, has_vip),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Обработка всех кнопок карточки
# ---------------------------------------------------------------------------

@router.callback_query(F.data.startswith("check_"), F.from_user.id.in_(ADMIN_IDS))
async def handle_check_buttons(call: CallbackQuery, state: FSMContext):
    data = call.data

    if data == "check_resetallstars":
        _reset_all_stars()
        await call.answer("✅ Звёзды обнулены у всех пользователей!", show_alert=True)
        return

    raw    = data[len("check_"):]
    parts  = raw.split("_")
    action = parts[0]

    if action in ("add", "rem"):
        currency = parts[1]
        target   = parts[2]
        await state.update_data(t_id=target, action=action, curr=currency)
        await state.set_state(AdminStates.wait_for_amount)

        verb  = "начисления" if action == "add" else "списания"
        label = "dC" if currency == "balance" else "звёздочек"
        icon  = BALANCE if currency == "balance" else STARS
        return await call.message.answer(
            f"{icon} Введите сумму {verb} <b>{label}</b> для <code>@{target}</code>:",
            parse_mode="HTML",
        )

    if action == "refresh":
        target    = parts[1]
        search_id = f"@{target}"
        user_data = database.get_user_info(search_id)
        if not user_data:
            return await call.answer("❌ Пользователь не найден.")
        name, balance, _, _ = user_data
        stars     = _get_stars(search_id)
        is_banned = database.is_user_banned(target)
        has_vip   = database.get_vip_status(target)
        await call.message.edit_text(
            build_profile_text(target, name, balance, stars, is_banned, has_vip),
            reply_markup=get_check_kb(target, is_banned, has_vip),
            parse_mode="HTML",
        )
        await call.answer("🔄 Обновлено")
        return

    target = parts[1]
    if action == "ban":
        database.set_ban_status(f"@{target}", 1)
    elif action == "unban":
        database.set_ban_status(f"@{target}", 0)
    elif action == "givip":
        database.give_vip_month(target)
    elif action == "revip":
        database.remove_vip(target)
    else:
        return await call.answer("⚠️ Неизвестное действие.")

    await call.answer("✅ Выполнено!")

    search_id = f"@{target}"
    user_data = database.get_user_info(search_id)
    name, balance, _, _ = user_data
    stars     = _get_stars(search_id)
    is_banned = database.is_user_banned(target)
    has_vip   = database.get_vip_status(target)

    await call.message.edit_text(
        build_profile_text(target, name, balance, stars, is_banned, has_vip),
        reply_markup=get_check_kb(target, is_banned, has_vip),
        parse_mode="HTML",
    )


# ---------------------------------------------------------------------------
# Обработка ввода суммы
# ---------------------------------------------------------------------------

@router.message(AdminStates.wait_for_amount)
async def proc_admin_amount(message: Message, state: FSMContext):
    if not message.text or not message.text.strip().isdigit():
        return await message.answer(f"{ERROR} Введите целое положительное число!", parse_mode="HTML")

    data      = await state.get_data()
    target_id = data["t_id"]
    action    = data["action"]
    currency  = data["curr"]
    amount    = int(message.text.strip())
    fmt_id    = f"@{target_id}"

    if currency == "balance":
        delta = amount if action == "add" else -amount
        database.update_balance(fmt_id, delta)
        icon  = BALANCE
        label = f"dC {icon}"
    else:
        delta = amount if action == "add" else -amount
        _update_stars(fmt_id, delta)
        icon  = STARS
        label = f"звёздочек {icon}"

    verb       = f"{SUCCESS} Начислено" if action == "add" else f"{MINUS} Снято"
    fmt_amount = f"{amount:,}".replace(",", " ")

    await message.answer(
        f"{verb} <b>{fmt_amount} {label}</b> пользователю <code>@{target_id}</code>",
        parse_mode="HTML",
    )
    await state.clear()
