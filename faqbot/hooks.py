import os

import aiofiles
from deltachat_rpc_client import AttrDict, EventType, events
from sqlalchemy.future import select

from .orm import FAQ, async_session

hooks = events.HookCollection()


@hooks.on(events.RawEvent((EventType.INFO, EventType.WARNING, EventType.ERROR)))
async def log_event(event: AttrDict) -> None:
    print(f"{event.type.upper()}: {event.msg}")


async def _get_faq(chat_id: int) -> str:
    text = ""
    async with async_session() as session:
        stmt = select(FAQ).filter(FAQ.chat_id == chat_id)
        for faq in (await session.execute(stmt)).scalars().all():
            text += f"* {faq.question}\n"
    return text


async def _get_answer_text(faq: FAQ, msg: AttrDict) -> str:
    if not faq.answer_text:
        return ""
    kwargs = {}
    if msg.quote:
        kwargs["name"] = msg.quote.override_sender_name or msg.quote.author_display_name
    else:
        sender = await msg.sender.get_snapshot()
        kwargs["name"] = msg.override_sender_name or sender.display_name
    kwargs["faq"] = await _get_faq(msg.chat_id)
    return faq.answer_text.format(**kwargs)


@hooks.on(events.NewMessage(r"^/help$"))
async def help_cmd(event: AttrDict) -> None:
    text = """
           **Available commands**

           /faq - sends available topics.

           /save TAG - save the quoted message as answer to the given tag/question. The answer can contain special keywords like:
           {faq} - gets replaced by the FAQ/topics list.
           {name} - gets replaced by the name of the sender of the tag/question or the quoted message.

           /remove TAG - remove the saved tag/question and its reply


           """
    await event.chat.send_text(text)


@hooks.on(events.NewMessage(r"^/faq$"))
async def faq_cmd(event: AttrDict) -> None:
    text = await _get_faq(event.chat_id)
    await event.chat.send_text(f"**FAQ**\n\n{text}")


@hooks.on(events.NewMessage(r"^/remove .+"))
async def remove_cmd(event: AttrDict) -> None:
    question = event.text.split(maxsplit=1)[1]
    stmt = select(FAQ).filter(FAQ.chat_id == event.chat_id, FAQ.question == question)
    async with async_session() as session:
        async with session.begin():
            faq = (await session.execute(stmt)).scalars().first()
            if faq:
                await session.delete(faq)
                await event.chat.send_message(
                    text="✅ Note removed", quoted_msg=event.id
                )


@hooks.on(events.NewMessage(r"^/save .+"))
async def save_cmd(event: AttrDict) -> None:
    question = event.text.split(maxsplit=1)[1]
    if question.startswith("/"):
        await event.chat.send_message(
            text="Invalid text, can not start with /", quoted_msg=event.id
        )
        return
    quote = event.quote
    assert quote
    quote = await (
        await event.message.account.get_message_by_id(quote.message_id)
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
                    chat_id=event.chat_id,
                    question=question,
                    answer_text=quote.text,
                    answer_filename=quote.file_name,
                    answer_file=file_bytes,
                    answer_viewtype=quote.view_type,
                )
            )
    await event.chat.send_message(text="✅ Saved", quoted_msg=event.id)


@hooks.on(events.NewMessage(r"^(?!/).+"))
async def answer_msg(event: AttrDict) -> None:
    async with async_session() as session:
        stmt = select(FAQ).filter(
            FAQ.chat_id == event.chat_id, FAQ.question == event.text
        )
        faq = (await session.execute(stmt)).scalars().first()
        if faq:
            quoted_msg_id = event.quote.message_id if event.quote else event.id
            kwargs = dict(
                text=await _get_answer_text(faq, event), quoted_msg=quoted_msg_id
            )
            if faq.answer_file:
                async with aiofiles.tempfile.TemporaryDirectory() as tmp_dir:
                    filename = os.path.join(tmp_dir, faq.answer_filename)
                    async with aiofiles.open(filename, mode="wb") as attachment:
                        await attachment.write(faq.answer_file)
                    await event.chat.send_message(file=filename, **kwargs)
            else:
                await event.chat.send_message(**kwargs)
