"""
handlers/shop.py — MathBot MVP v2.0
Virtual Shop & Inventory

Items (from config.SHOP_ITEMS):
  shield      — Blocks one incoming R3 challenge (auto-activates)
  trap        — Next challenger who attacks you loses 10 XP (auto-activates)
  double_down — Double XP on next R2 session
  spy         — Reveal another student's current XP total (one-time use)
  hint        — Skip one R2 question without penalty

Commands/callbacks registered in main.py:
  /shop                           → show_shop()
  /inventory                      → show_inventory()
  CB_SHOP_BUY + "{item_key}"      → handle_buy_confirm()
  CB_SHOP_CONFIRM + "{item_key}"  → handle_buy_execute()
  CB_SHOP_USE + "{item_key}"      → handle_use_item()
  CB_SPY_TARGET + "{target_id}"   → handle_spy_target()
"""
import logging
from typing import Dict, Any, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

import config
import database as db
from utils import messages as msg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _shop_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, item in config.SHOP_ITEMS.items():
        label = f"{item['icon']} {item['name_zh']}  🪙{item['price']}"
        rows.append([InlineKeyboardButton(label, callback_data=f"{config.CB_SHOP_BUY}{key}")])
    return InlineKeyboardMarkup(rows)


def _confirm_keyboard(item_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ 確認購買", callback_data=f"{config.CB_SHOP_CONFIRM}{item_key}"),
        InlineKeyboardButton("❌ 取消", callback_data=f"{config.CB_SHOP_BUY}cancel"),
    ]])


def _inventory_keyboard(owned_items: List[Dict]) -> Optional[InlineKeyboardMarkup]:
    usable = [i for i in owned_items if i["uses_remaining"] > 0 and i["item_key"] in config.SHOP_ITEMS]
    if not usable:
        return None
    rows = []
    for item in usable:
        meta = config.SHOP_ITEMS[item["item_key"]]
        label = f"{meta['icon']} 使用 {meta['name_zh']}"
        rows.append([InlineKeyboardButton(label, callback_data=f"{config.CB_SHOP_USE}{item['item_key']}")])
    return InlineKeyboardMarkup(rows) if rows else None


def _spy_target_keyboard(pool_ignored, targets: List[Dict]) -> InlineKeyboardMarkup:
    rows = []
    for t in targets[:8]:
        rows.append([InlineKeyboardButton(
            t["display_name"],
            callback_data=f"{config.CB_SPY_TARGET}{t['id']}"
        )])
    return InlineKeyboardMarkup(rows)


def _format_shop_text() -> str:
    lines = ["🛒 *道具商店*\n"]
    for key, item in config.SHOP_ITEMS.items():
        lines.append(
            f"{item['icon']} *{item['name_zh']}*  🪙 {item['price']} 硬幣\n"
            f"  _{item['description_zh']}_\n"
        )
    return "\n".join(lines)


def _format_inventory_text(owned_items: List[Dict]) -> str:
    if not owned_items:
        return "🎒 *背包空空如也*\n\n去商店買道具吧！"
    lines = ["🎒 *我的背包*\n"]
    for item in owned_items:
        meta = config.SHOP_ITEMS.get(item["item_key"])
        if not meta:
            continue
        uses = item["uses_remaining"]
        status = "（已用完）" if uses == 0 else f"（剩餘 {uses} 次）"
        lines.append(f"{meta['icon']} *{meta['name_zh']}* {status}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# /shop command
# ---------------------------------------------------------------------------

async def show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pool = context.application.bot_data.get("db")
    if not pool:
        await update.message.reply_text(msg.MSG_DATABASE_ERROR)
        return

    student = await db.get_student_by_telegram_id(pool, update.effective_user.id)
    if not student or student["status"] != "active":
        await update.message.reply_text(msg.MSG_NOT_REGISTERED)
        return

    shop_text = _format_shop_text()
    shop_text += f"\n\n💰 你的硬幣：*{student['coins']}*"

    await update.message.reply_text(
        shop_text,
        reply_markup=_shop_keyboard(),
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# /inventory command
# ---------------------------------------------------------------------------

async def show_inventory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pool = context.application.bot_data.get("db")
    if not pool:
        await update.message.reply_text(msg.MSG_DATABASE_ERROR)
        return

    student = await db.get_student_by_telegram_id(pool, update.effective_user.id)
    if not student or student["status"] != "active":
        await update.message.reply_text(msg.MSG_NOT_REGISTERED)
        return

    owned = await db.get_student_inventory(pool, student["id"])
    text = _format_inventory_text(owned)
    keyboard = _inventory_keyboard(owned)

    await update.message.reply_text(
        text,
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# CB_SHOP_BUY — show item detail + confirm button
# ---------------------------------------------------------------------------

async def handle_buy_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    pool = context.application.bot_data.get("db")
    if not pool:
        await query.edit_message_text(msg.MSG_DATABASE_ERROR)
        return

    item_key = query.data.replace(config.CB_SHOP_BUY, "", 1)

    if item_key == "cancel":
        await query.edit_message_text("❌ 已取消。")
        return

    item = config.SHOP_ITEMS.get(item_key)
    if not item:
        await query.edit_message_text("❌ 找不到此道具。")
        return

    student = await db.get_student_by_telegram_id(pool, update.effective_user.id)
    if not student:
        await query.edit_message_text(msg.MSG_NOT_REGISTERED)
        return

    text = (
        f"{item['icon']} *{item['name_zh']}*\n\n"
        f"{item['description_zh']}\n\n"
        f"價格：🪙 {item['price']} 硬幣\n"
        f"你的硬幣：🪙 {student['coins']}\n\n"
        f"確認購買？"
    )

    await query.edit_message_text(
        text,
        reply_markup=_confirm_keyboard(item_key),
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# CB_SHOP_CONFIRM — execute purchase
# ---------------------------------------------------------------------------

async def handle_buy_execute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    pool = context.application.bot_data.get("db")
    if not pool:
        await query.edit_message_text(msg.MSG_DATABASE_ERROR)
        return

    item_key = query.data.replace(config.CB_SHOP_CONFIRM, "", 1)
    item = config.SHOP_ITEMS.get(item_key)
    if not item:
        await query.edit_message_text("❌ 找不到此道具。")
        return

    student = await db.get_student_by_telegram_id(pool, update.effective_user.id)
    if not student:
        await query.edit_message_text(msg.MSG_NOT_REGISTERED)
        return

    if student["coins"] < item["price"]:
        await query.edit_message_text(
            f"❌ 硬幣不足！\n\n需要 🪙 {item['price']}，你只有 🪙 {student['coins']}。"
        )
        return

    # Deduct coins and add to inventory
    success = await db.purchase_item(pool, student_id=student["id"], item_key=item_key, price=item["price"])
    if not success:
        await query.edit_message_text("❌ 購買失敗，請重試。")
        return

    new_coins = student["coins"] - item["price"]
    await query.edit_message_text(
        f"✅ *購買成功！*\n\n"
        f"{item['icon']} {item['name_zh']} 已加入背包。\n"
        f"剩餘硬幣：🪙 {new_coins}",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# CB_SHOP_USE — use an item from inventory
# ---------------------------------------------------------------------------

async def handle_use_item(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    pool = context.application.bot_data.get("db")
    if not pool:
        await query.edit_message_text(msg.MSG_DATABASE_ERROR)
        return

    item_key = query.data.replace(config.CB_SHOP_USE, "", 1)
    item = config.SHOP_ITEMS.get(item_key)
    if not item:
        await query.edit_message_text("❌ 找不到此道具。")
        return

    student = await db.get_student_by_telegram_id(pool, update.effective_user.id)
    if not student:
        await query.edit_message_text(msg.MSG_NOT_REGISTERED)
        return

    # Verify student owns it with uses remaining
    inv_item = await db.get_inventory_item(pool, student_id=student["id"], item_key=item_key)
    if not inv_item or inv_item["uses_remaining"] <= 0:
        await query.edit_message_text("❌ 你沒有這個道具或已用完。")
        return

    # Spy requires target selection — handle separately
    if item_key == "spy":
        classmates = await db.get_active_classmates(pool, student_id=student["id"], class_id=student["class_id"])
        if not classmates:
            await query.edit_message_text("❌ 找不到同班同學。")
            return
        keyboard = _spy_target_keyboard(None, classmates)
        await query.edit_message_text(
            "🔍 *選擇你要偵查的同學：*",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        return

    # All other items: activate flag on student row
    flag_map = {
        "shield": "shield_active",
        "trap": "trap_active",
        "double_down": "double_down_active",
        "hint": "hint_active",
    }
    flag = flag_map.get(item_key)
    if not flag:
        await query.edit_message_text("❌ 這個道具暫時無法使用。")
        return

    await db.activate_item_flag(pool, student_id=student["id"], flag=flag)
    await db.consume_inventory_item(pool, student_id=student["id"], item_key=item_key)

    await query.edit_message_text(
        f"✅ *{item['icon']} {item['name_zh']} 已啟動！*\n\n{item['activated_text_zh']}",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# CB_SPY_TARGET — reveal target's XP
# ---------------------------------------------------------------------------

async def handle_spy_target(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    pool = context.application.bot_data.get("db")
    if not pool:
        await query.edit_message_text(msg.MSG_DATABASE_ERROR)
        return

    try:
        target_id = int(query.data.replace(config.CB_SPY_TARGET, "", 1))
    except ValueError:
        await query.edit_message_text("❌ 無效操作。")
        return

    student = await db.get_student_by_telegram_id(pool, update.effective_user.id)
    if not student:
        await query.edit_message_text(msg.MSG_NOT_REGISTERED)
        return

    # Consume the spy item
    inv_item = await db.get_inventory_item(pool, student_id=student["id"], item_key="spy")
    if not inv_item or inv_item["uses_remaining"] <= 0:
        await query.edit_message_text("❌ 偵查道具已用完。")
        return

    target = await db.get_student_by_id(pool, target_id)
    if not target:
        await query.edit_message_text("❌ 找不到同學。")
        return

    await db.consume_inventory_item(pool, student_id=student["id"], item_key="spy")

    await query.edit_message_text(
        f"🔍 *偵查結果*\n\n"
        f"{target['display_name']} 目前有 *{target['xp']} XP*。",
        parse_mode="Markdown",
    )
