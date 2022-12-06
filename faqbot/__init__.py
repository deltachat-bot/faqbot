import logging
import os

from appdirs import user_config_dir
from deltachat_rpc_client import Message, MessageSnapshot, events, run_bot_cli
from sqlalchemy.future import select

from .orm import FAQ, async_session, init

hooks = events.HookCollection()
config_dir = user_config_dir("faqbot")
if not os.path.exists(config_dir):
    os.makedirs(config_dir)


@hooks.on(events.RawEvent)
async def log_event(event):
    print(event)


@hooks.on(events.NewMessage(r"^/faq$"))
async def faq_cmd(msg: MessageSnapshot) -> None:
    text = ""
    async with async_session() as session:
        stmt = select(FAQ).filter(FAQ.chat_id == msg.chat.chat_id)
        for faq in (await session.execute(stmt)).scalars().all():
            text += f"* {faq.question}\n"
    await msg.chat.send_msg(f"**FAQ**\n\n{text}")


@hooks.on(events.NewMessage(r"^/remove .+"))
async def remove_cmd(msg: MessageSnapshot) -> None:
    question = msg.text.split(maxsplit=1)[1]
    stmt = select(FAQ).filter(FAQ.chat_id == msg.chat.chat_id, FAQ.question == question)
    async with async_session() as session:
        async with session.begin():
            faq = (await session.execute(stmt)).scalars().first()
            if faq:
                await session.delete(faq)
                await msg.chat.send_msg(
                    text="✅ Note removed", quoted_msg=msg.message.msg_id
                )


@hooks.on(events.NewMessage(r"^/save .+"))
async def save_cmd(msg: MessageSnapshot) -> None:
    m = msg.message
    snapshot = await m._rpc.get_message(m.account_id, m.msg_id)
    question = msg.text.split(maxsplit=1)[1]
    assert not question.startswith("/")
    quote = snapshot["quote"] or {}
    answer = quote["text"]
    assert answer
    chat_id = msg.chat.chat_id
    async with async_session() as session:
        async with session.begin():
            session.add(FAQ(chat_id=chat_id, question=question, answer=answer))
    await msg.chat.send_msg(text="✅ Note saved", quoted_msg=m.msg_id)


@hooks.on(events.NewMessage(r"^(?!/).+"))
async def answer_msg(msg: MessageSnapshot) -> None:
    chat_id = msg.chat.chat_id
    async with async_session() as session:
        stmt = select(FAQ).filter(FAQ.chat_id == chat_id, FAQ.question == msg.text)
        faq = (await session.execute(stmt)).scalars().first()
        if faq:
            m = msg.message
            snapshot = await m._rpc.get_message(m.account_id, m.msg_id)
            quote = snapshot["quote"] or {}
            quoted_msg_id = quote.get("messageId") or m.msg_id
            await msg.chat.send_msg(text=faq.answer, quoted_msg=quoted_msg_id)


async def main():
    logging.basicConfig(level=logging.INFO)
    path = os.path.join(config_dir, "sqlite.db")
    await init(f"sqlite+aiosqlite:///{path}")
    await run_bot_cli(hooks)
