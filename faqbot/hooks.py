"""Event Hooks"""
import logging
import os
from argparse import Namespace

import aiofiles
from deltabot_cli import AttrDict, Bot, BotCli, EventType, const, events
from sqlalchemy.future import select

from .orm import FAQ, async_session, init
from .utils import get_answer_text, get_faq

cli = BotCli("faqbot")


@cli.on_init
async def on_init(bot: Bot, _args: Namespace) -> None:
    if not await bot.account.get_config("displayname"):
        await bot.account.set_config("displayname", "FAQ Bot")
        status = "📸 I am a Delta Chat bot, send me /help for more info"
        await bot.account.set_config("selfstatus", status)


@cli.on_start
async def _on_start(_bot: Bot, args: Namespace) -> None:
    path = os.path.join(args.config_dir, "sqlite.db")
    await init(f"sqlite+aiosqlite:///{path}")


@cli.on(events.RawEvent)
async def log_event(event: AttrDict) -> None:
    if event.type == EventType.INFO:
        logging.info(event.msg)
    elif event.type == EventType.WARNING:
        logging.warning(event.msg)
    elif event.type == EventType.ERROR:
        logging.error(event.msg)


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


           **How to use me?**

           Add me to a group then you can use the /save and /faq commands there
           """
    await event.message_snapshot.chat.send_text(text)


@cli.on(events.NewMessage(command="/faq"))
async def _faq(event: AttrDict) -> None:
    msg = event.message_snapshot
    chat = await msg.chat.get_basic_snapshot()
    if chat.chat_type == const.ChatType.SINGLE:
        await msg.chat.send_message(
            text="Can't save notes in private, add me to a group and use the command there",
            quoted_msg=msg.id,
        )
        return

    text = await get_faq(msg.chat_id)
    await msg.chat.send_text(f"**FAQ**\n\n{text}")


@cli.on(events.NewMessage(command="/remove"))
async def _remove(event: AttrDict) -> None:
    msg = event.message_snapshot
    chat = await msg.chat.get_basic_snapshot()
    if chat.chat_type == const.ChatType.SINGLE:
        await msg.chat.send_message(
            text="Can't save notes in private, add me to a group and use the command there",
            quoted_msg=msg.id,
        )
        return

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
    chat = await msg.chat.get_basic_snapshot()
    if chat.chat_type == const.ChatType.SINGLE:
        await msg.chat.send_message(
            text="Can't save notes in private, add me to a group and use the command there",
            quoted_msg=msg.id,
        )
        return

    question = event.payload
    if question.startswith(const.COMMAND_PREFIX):
        await msg.chat.send_message(
            text=f"Invalid text, can not start with {const.COMMAND_PREFIX}",
            quoted_msg=msg.id,
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


@cli.on(events.NewMessage(is_info=False, func=cli.is_not_known_command))
async def _answer(event: AttrDict) -> None:
    msg = event.message_snapshot
    chat = await msg.chat.get_basic_snapshot()
    if chat.chat_type == const.ChatType.SINGLE:
        await _help(event)
        return
    if event.command or not msg.text:
        return

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
