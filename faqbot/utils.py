import random
from datetime import datetime
from typing import Callable

from simplebot_aio import AttrDict
from sqlalchemy.future import select

from .orm import FAQ, async_session


class RandStr:
    def __init__(self, func: Callable) -> None:
        self.func = func

    def __str__(self) -> str:
        return str(self.func())


async def get_faq(chat_id: int) -> str:
    text = ""
    async with async_session() as session:
        stmt = select(FAQ).filter(FAQ.chat_id == chat_id)
        for faq in (await session.execute(stmt)).scalars().all():
            text += f"* {faq.question}\n"
    return text


async def get_answer_text(faq: FAQ, event: AttrDict) -> str:
    if not faq.answer_text:
        return ""
    kwargs = {}
    if event.quote:
        kwargs["name"] = (
            event.quote.override_sender_name or event.quote.author_display_name
        )
        quote = await (
            await event.message.account.get_message_by_id(event.quote.message_id)
        ).get_snapshot()
        sender = await quote.sender.get_snapshot()
    else:
        sender = await event.sender.get_snapshot()
        kwargs["name"] = event.override_sender_name or sender.display_name
    if sender.last_seen:
        last_seen = datetime.fromtimestamp(sender.last_seen)
        kwargs["last_seen"] = str(last_seen.replace(microsecond=0))
    else:
        kwargs["last_seen"] = "never"
    kwargs["faq"] = await get_faq(event.chat_id)
    kwargs["percent"] = RandStr(lambda: random.randint(0, 100))
    kwargs["yes_no"] = RandStr(lambda: random.choice(["yes", "no"]))
    kwargs["dice"] = RandStr(lambda: random.choice(["⚀", "⚁", "⚂", "⚃", "⚄", "⚅"]))
    kwargs["date"] = datetime.utcnow().date().strftime("%d/%m/%Y")

    return faq.answer_text.format(**kwargs)
