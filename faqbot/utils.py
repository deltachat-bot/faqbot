from simplebot_aio import AttrDict
from sqlalchemy.future import select

from .orm import FAQ, async_session


async def get_faq(chat_id: int) -> str:
    text = ""
    async with async_session() as session:
        stmt = select(FAQ).filter(FAQ.chat_id == chat_id)
        for faq in (await session.execute(stmt)).scalars().all():
            text += f"* {faq.question}\n"
    return text


async def get_answer_text(faq: FAQ, msg: AttrDict) -> str:
    if not faq.answer_text:
        return ""
    kwargs = {}
    if msg.quote:
        kwargs["name"] = msg.quote.override_sender_name or msg.quote.author_display_name
    else:
        sender = await msg.sender.get_snapshot()
        kwargs["name"] = msg.override_sender_name or sender.display_name
    kwargs["faq"] = await get_faq(msg.chat_id)
    return faq.answer_text.format(**kwargs)
