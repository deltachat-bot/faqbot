"""Event Hooks"""
import logging
import os

import aiofiles
from simplebot_aio import AttrDict, BotCli, EventType, events
from sqlalchemy.future import select

from .orm import FAQ, async_session, init
from .utils import get_answer_text, get_faq

cli = BotCli("faqbot")


@cli.on(events.RawEvent((EventType.INFO, EventType.WARNING, EventType.ERROR)))
async def _log_event(event: AttrDict) -> None:
    getattr(logging, event.type.lower())(event.msg)


@cli.on(events.NewMessage(command="/help"))
async def _help(event: AttrDict) -> None:
    text = """
           **Available commands**

           /faq - sends available topics.

           /save TAG - save the quoted message as answer to the given tag/question. The answer can contain special keywords like:
           {faq} - gets replaced by the FAQ/topics list.
           {name} - gets replaced by the name of the sender of the tag/question or the quoted message.
           {last_seen} - gets replaced by the last time the sender of the quoted message was seen.
           {date} - gets replaced by the current date.
           {percent} - gets replaced by a random number in 0-100 range.
           {dice} - gets replaced by a random dice.
           {yes_no} - gets replaced randomly by "yes" or "no".

           /remove TAG - remove the saved tag/question and its reply


           """
    await event.message_snapshot.chat.send_text(text)


@cli.on(events.NewMessage(command="/faq"))
async def _faq(event: AttrDict) -> None:
    msg = event.message_snapshot
    text = await get_faq(msg.chat_id)
    await msg.chat.send_text(f"**FAQ**\n\n{text}")


@cli.on(events.NewMessage(command="/remove"))
async def _remove(event: AttrDict) -> None:
    msg = event.message_snapshot
    question = event.payload
    stmt = select(FAQ).filter(FAQ.chat_id == msg.chat_id, FAQ.question == question)
    async with async_session() as session:
        async with session.begin():
            faq = (await session.execute(stmt)).scalars().first()
            if faq:
                await session.delete(faq)
                await msg.chat.send_message(text="✅ Note removed", quoted_msg=msg.id)


@cli.on(events.NewMessage(command="/save"))
async def _save(event: AttrDict) -> None:
    msg = event.message_snapshot
    question = event.payload
    if question.startswith("/"):
        await msg.chat.send_message(
            text="Invalid text, can not start with /", quoted_msg=msg.id
        )
        return
    quote = msg.quote
    assert quote
    quote = await (
        msg.message.account.get_message_by_id(quote.message_id)
    ).get_snapshot()
    if quote.file:
        async with aiofiles.open(quote.file, mode="rb") as attachment:
            file_bytes = await attachment.read()
    else:
        file_bytes = None
    async with async_session() as session:
        async with session.begin():
            session.add(
                FAQ(
                    chat_id=msg.chat_id,
                    question=question,
                    answer_text=quote.text,
                    answer_filename=quote.file_name,
                    answer_file=file_bytes,
                    answer_viewtype=quote.view_type,
                )
            )
    await msg.chat.send_message(text="✅ Saved", quoted_msg=msg.id)


@cli.on(events.NewMessage(r".+", func=lambda ev: not ev.command))
async def _answer(event: AttrDict) -> None:
    msg = event.message_snapshot
    async with async_session() as session:
        stmt = select(FAQ).filter(FAQ.chat_id == msg.chat_id, FAQ.question == msg.text)
        faq = (await session.execute(stmt)).scalars().first()
        if faq:
            quoted_msg_id = msg.quote.message_id if msg.quote else msg.id
            kwargs = dict(
                text=await get_answer_text(faq, msg), quoted_msg=quoted_msg_id
            )
            if faq.answer_file:
                async with aiofiles.tempfile.TemporaryDirectory() as tmp_dir:
                    filename = os.path.join(tmp_dir, faq.answer_filename)
                    async with aiofiles.open(filename, mode="wb") as attachment:
                        await attachment.write(faq.answer_file)
                    await msg.chat.send_message(file=filename, **kwargs)
            else:
                await msg.chat.send_message(**kwargs)


@cli.on_start
async def _on_start(_bot, args) -> None:
    path = os.path.join(args.config_dir, "sqlite.db")
    await init(f"sqlite+aiosqlite:///{path}")
