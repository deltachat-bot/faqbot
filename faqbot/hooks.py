"""Event Hooks"""
import logging
import os
from argparse import Namespace
from tempfile import TemporaryDirectory

from deltabot_cli import AttrDict, Bot, BotCli, EventType, const, events
from sqlalchemy.exc import IntegrityError
from sqlalchemy.future import select

from .orm import FAQ, init, session_scope
from .utils import get_answer_text, get_faq

cli = BotCli("faqbot")


@cli.on_init
def on_init(bot: Bot, _args: Namespace) -> None:
    if not bot.account.get_config("displayname"):
        bot.account.set_config("displayname", "FAQ Bot")
        status = "I am a Delta Chat bot, send me /help for more info"
        bot.account.set_config("selfstatus", status)


@cli.on_start
def _on_start(_bot: Bot, args: Namespace) -> None:
    path = os.path.join(args.config_dir, "sqlite.db")
    init(f"sqlite:///{path}")


@cli.on(events.RawEvent)
def log_event(event: AttrDict) -> None:
    if event.type == EventType.INFO:
        logging.info(event.msg)
    elif event.type == EventType.WARNING:
        logging.warning(event.msg)
    elif event.type == EventType.ERROR:
        logging.error(event.msg)


@cli.on(events.NewMessage(command="/help"))
def _help(event: AttrDict) -> None:
    text = """**Available commands**

/faq - sends available topics.

/save TAG - save the quoted message as answer to the given tag/question. The answer can contain special keywords like:
{faq} - gets replaced by the FAQ/topics list.
{name} - gets replaced by the name of the sender of the tag/question or the quoted message.

/remove TAG - remove the saved tag/question and its reply


**How to use me?**

Add me to a group then you can use the /save and /faq commands there"""
    event.message_snapshot.chat.send_text(text)


@cli.on(events.NewMessage(command="/faq"))
def _faq(event: AttrDict) -> None:
    msg = event.message_snapshot
    chat = msg.chat.get_basic_snapshot()
    if chat.chat_type == const.ChatType.SINGLE:
        msg.chat.send_message(
            text="Can't save notes in private, add me to a group and use the command there",
            quoted_msg=msg.id,
        )
        return

    with session_scope() as session:
        text = get_faq(msg.chat_id, session)
    msg.chat.send_text(f"**FAQ**\n\n{text}")


@cli.on(events.NewMessage(command="/remove"))
def _remove(event: AttrDict) -> None:
    msg = event.message_snapshot
    chat = msg.chat.get_basic_snapshot()
    if chat.chat_type == const.ChatType.SINGLE:
        msg.chat.send_message(
            text="Can't save notes in private, add me to a group and use the command there",
            quoted_msg=msg.id,
        )
        return

    question = event.payload
    stmt = select(FAQ).filter(FAQ.chat_id == msg.chat_id, FAQ.question == question)
    with session_scope() as session:
        with session.begin():
            faq = (session.execute(stmt)).scalars().first()
            if faq:
                session.delete(faq)
                msg.chat.send_message(text="✅ Note removed", quoted_msg=msg.id)


@cli.on(events.NewMessage(command="/save"))
def _save(event: AttrDict) -> None:
    msg = event.message_snapshot
    chat = msg.chat.get_basic_snapshot()
    if chat.chat_type == const.ChatType.SINGLE:
        msg.chat.send_message(
            text="Can't save notes in private, add me to a group and use the command there",
            quoted_msg=msg.id,
        )
        return

    question = event.payload
    if question.startswith(const.COMMAND_PREFIX):
        msg.chat.send_message(
            text=f"Invalid text, can not start with {const.COMMAND_PREFIX}",
            quoted_msg=msg.id,
        )
        return
    quote = msg.quote
    assert quote
    quote = msg.message.account.get_message_by_id(quote.message_id).get_snapshot()
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
        msg.chat.send_message(text="✅ Saved", quoted_msg=msg.id)
    except IntegrityError:
        msg.chat.send_message(
            text="❌ Error: there is already a saved reply for that tag/question,"
            " use /remove first to remove the old reply",
            quoted_msg=msg.id,
        )


@cli.on(events.NewMessage(is_info=False, func=cli.is_not_known_command))
def _answer(event: AttrDict) -> None:
    msg = event.message_snapshot
    chat = msg.chat.get_basic_snapshot()
    if chat.chat_type == const.ChatType.SINGLE:
        _help(event)
        return
    if event.command or not msg.text:
        return

    with session_scope() as session:
        stmt = select(FAQ).filter(FAQ.chat_id == msg.chat_id, FAQ.question == msg.text)
        faq = (session.execute(stmt)).scalars().first()
        if faq:
            quoted_msg_id = msg.quote.message_id if msg.quote else msg.id
            kwargs = {
                "text": get_answer_text(faq, msg, session),
                "quoted_msg": quoted_msg_id,
            }
            if faq.answer_file:
                with TemporaryDirectory() as tmp_dir:
                    filename = os.path.join(tmp_dir, faq.answer_filename)
                    with open(filename, mode="wb") as attachment:
                        attachment.write(faq.answer_file)
                    msg.chat.send_message(file=filename, **kwargs)
            else:
                msg.chat.send_message(**kwargs)
