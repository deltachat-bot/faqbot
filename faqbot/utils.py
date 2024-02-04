"""Utilities"""

from deltabot_cli import AttrDict, Bot
from sqlalchemy.future import select

from .orm import FAQ


def get_faq(chat_id: int, session) -> str:
    """Get the FAQ list as a markdown list."""
    text = ""
    stmt = select(FAQ).filter(FAQ.chat_id == chat_id)
    for faq in session.execute(stmt).scalars().all():
        text += f"* {faq.question}\n"
    return text


def get_answer_text(bot: Bot, accid: int, faq: FAQ, msg: AttrDict, session) -> str:
    """Generate the answer from the given FAQ entry's template answer."""
    if not faq.answer_text:
        return ""
    kwargs = {}
    if msg.quote:
        kwargs["name"] = msg.quote.override_sender_name or msg.quote.author_display_name
    else:
        kwargs["name"] = (
            msg.override_sender_name
            or bot.rpc.get_contact(accid, msg.sender.id).display_name
        )
    kwargs["faq"] = get_faq(msg.chat_id, session)

    return faq.answer_text.format(**kwargs)
