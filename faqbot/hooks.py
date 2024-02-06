"""Event Hooks"""

import os
from argparse import Namespace
from tempfile import TemporaryDirectory

from deltabot_cli import (
    AttrDict,
    Bot,
    BotCli,
    EventType,
    const,
    events,
    is_not_known_command,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from .orm import FAQ, init, session_scope
from .utils import get_answer_text, get_faq

cli = BotCli("faqbot")


@cli.on_init
def on_init(bot: Bot, _args: Namespace) -> None:
    for accid in bot.rpc.get_all_account_ids():
        if not bot.rpc.get_config(accid, "displayname"):
            bot.rpc.set_config(accid, "displayname", "FAQ Bot")
            status = "I am a Delta Chat bot, send me /help for more info"
            bot.rpc.set_config(accid, "selfstatus", status)
            bot.rpc.set_config(accid, "delete_server_after", "1")


@cli.on_start
def _on_start(_bot: Bot, args: Namespace) -> None:
    path = os.path.join(args.config_dir, "sqlite.db")
    init(f"sqlite:///{path}")


@cli.on(events.RawEvent)
def log_event(bot: Bot, accid: int, event: AttrDict) -> None:
    if event.kind == EventType.INFO:
        bot.logger.info(event.msg)
    elif event.kind == EventType.WARNING:
        bot.logger.warning(event.msg)
    elif event.kind == EventType.ERROR:
        bot.logger.error(event.msg)
    elif event.kind == EventType.SECUREJOIN_INVITER_PROGRESS:
        if event.progress == 1000:
            bot.logger.debug("QR scanned by contact id=%s", event.contact_id)
            chatid = bot.rpc.create_chat_by_contact_id(accid, event.contact_id)
            send_help(bot, accid, chatid)


@cli.on(events.NewMessage(command="/help"))
def _help(bot: Bot, accid: int, event: AttrDict) -> None:
    send_help(bot, accid, event.msg.chat_id)


def send_help(bot: Bot, accid: int, chat_id: int) -> None:
    text = """**Available commands**

/faq - sends available topics.

/save TAG - save the quoted message as answer to the given tag/question. The answer can contain special keywords like:
{faq} - gets replaced by the FAQ/topics list.
{name} - gets replaced by the name of the sender of the tag/question or the quoted message.

/remove TAG - remove the saved tag/question and its reply


**How to use me?**

Add me to a group then you can use the /save and /faq commands there"""
    bot.rpc.send_msg(accid, chat_id, {"text": text})


@cli.on(events.NewMessage(command="/faq"))
def _faq(bot: Bot, accid: int, event: AttrDict) -> None:
    msg = event.msg
    if reply_to_command_in_dm(bot, accid, msg):
        return

    with session_scope() as session:
        text = get_faq(msg.chat_id, session)
    bot.rpc.send_msg(accid, msg.chat_id, {"text": f"**FAQ**\n\n{text}"})


@cli.on(events.NewMessage(command="/remove"))
def _remove(bot: Bot, accid: int, event: AttrDict) -> None:
    msg = event.msg
    if reply_to_command_in_dm(bot, accid, msg):
        return

    question = event.payload
    stmt = select(FAQ).filter(FAQ.chat_id == msg.chat_id, FAQ.question == question)
    with session_scope() as session:
        with session.begin():
            faq = (session.execute(stmt)).scalars().first()
            if faq:
                session.delete(faq)
                reply = {"text": "✅ Note removed", "quotedMessageId": msg.id}
                bot.rpc.send_msg(accid, msg.chat_id, reply)


@cli.on(events.NewMessage(command="/save"))
def _save(bot: Bot, accid: int, event: AttrDict) -> None:
    msg = event.msg
    if reply_to_command_in_dm(bot, accid, msg):
        return

    question = event.payload
    if question.startswith(const.COMMAND_PREFIX):
        reply = {
            "text": f"Invalid text, can not start with {const.COMMAND_PREFIX}",
            "quotedMessageId": msg.id,
        }
        bot.rpc.send_msg(accid, msg.chat_id, reply)
        return
    quote = msg.quote
    assert quote
    quote = bot.rpc.get_message(accid, quote.message_id)
    if quote.file:
        with open(quote.file, mode="rb") as attachment:
            file_bytes = attachment.read()
    else:
        file_bytes = None
    try:
        with session_scope() as session:
            with session.begin():
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
        reply = {"text": "✅ Saved", "quotedMessageId": msg.id}
    except IntegrityError:
        reply = {
            "text": "❌ Error: there is already a saved reply for that tag/question,"
            " use /remove first to remove the old reply",
            "quotedMessageId": msg.id,
        }
    bot.rpc.send_msg(accid, msg.chat_id, reply)


@cli.on(events.NewMessage(is_info=False))
def markseen_commands(bot: Bot, accid: int, event: AttrDict) -> None:
    if not is_not_known_command(bot, event):
        bot.rpc.markseen_msgs(accid, [event.msg.id])


@cli.on(events.NewMessage(is_info=False, func=is_not_known_command))
def _answer(bot: Bot, accid: int, event: AttrDict) -> None:
    msg = event.msg
    chat = bot.rpc.get_basic_chat_info(accid, msg.chat_id)
    if chat.chat_type == const.ChatType.SINGLE:
        bot.rpc.markseen_msgs(accid, [msg.id])
        _help(bot, accid, event)
        return
    if event.command or not msg.text:
        return

    with session_scope() as session:
        stmt = select(FAQ).filter(FAQ.chat_id == msg.chat_id, FAQ.question == msg.text)
        faq = (session.execute(stmt)).scalars().first()
        if faq:
            quoted_msg_id = msg.quote.message_id if msg.quote else msg.id
            reply = {
                "text": get_answer_text(bot, accid, faq, msg, session),
                "quotedMessageId": quoted_msg_id,
            }
            if faq.answer_file:
                with TemporaryDirectory() as tmp_dir:
                    filename = os.path.join(tmp_dir, faq.answer_filename)
                    with open(filename, mode="wb") as attachment:
                        attachment.write(faq.answer_file)
                    bot.rpc.send_msg(accid, msg.chat_id, {"file": filename, **reply})
            else:
                bot.rpc.send_msg(accid, msg.chat_id, reply)


def reply_to_command_in_dm(bot: Bot, accid: int, msg: AttrDict) -> bool:
    chat = bot.rpc.get_basic_chat_info(accid, msg.chat_id)
    if chat.chat_type == const.ChatType.SINGLE:
        reply = {
            "text": "Can't save notes in private, add me to a group and use the command there",
            "quotedMessageId": msg.id,
        }
        bot.rpc.send_msg(accid, msg.chat_id, reply)
        return True
    return False
