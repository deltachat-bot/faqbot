"""Utilities"""
import random
from datetime import datetime
from typing import Callable

from simplebot_aio import AttrDict
from sqlalchemy.future import select

from .orm import FAQ, async_session


class RandStr:
    """Class producing dynamic values each time it is converted to string."""

    def __init__(self, func: Callable) -> None:
        self.func = func

    def __str__(self) -> str:
        return str(self.func())


async def get_faq(chat_id: int) -> str:
    """Get the FAQ list as a markdown list."""
    text = ""
    async with async_session() as session:
        stmt = select(FAQ).filter(FAQ.chat_id == chat_id)
        for faq in (await session.execute(stmt)).scalars().all():
            text += f"* {faq.question}\n"
    return text


async def get_answer_text(faq: FAQ, msg: AttrDict) -> str:
    """Generate the answer from the given FAQ entry's template answer."""
    if not faq.answer_text:
        return ""
    kwargs = {}
    if msg.quote:
        kwargs["name"] = msg.quote.override_sender_name or msg.quote.author_display_name
        quote = await (
            msg.message.account.get_message_by_id(msg.quote.message_id)
        ).get_snapshot()
        sender = await quote.sender.get_snapshot()
    else:
        sender = await msg.sender.get_snapshot()
        kwargs["name"] = msg.override_sender_name or sender.display_name
    if sender.last_seen:
        last_seen = datetime.fromtimestamp(sender.last_seen)
        kwargs["last_seen"] = str(last_seen.replace(microsecond=0))
    else:
        kwargs["last_seen"] = "never"
    kwargs["faq"] = await get_faq(msg.chat_id)
    kwargs["percent"] = RandStr(lambda: random.randint(0, 100))
    kwargs["yes_no"] = RandStr(lambda: random.choice(["yes", "no"]))
    kwargs["dice"] = RandStr(lambda: random.choice(["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]))
    kwargs["date"] = datetime.utcnow().date().strftime("%d/%m/%Y")

    return faq.answer_text.format(**kwargs)
