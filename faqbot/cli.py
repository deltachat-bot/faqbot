import argparse
import asyncio
import os

from appdirs import user_config_dir
from deltachat_rpc_client import Bot, DeltaChat, Rpc
from deltachat_rpc_client.rpc import JsonRpcError

from .hooks import hooks
from .orm import init

config_dir = user_config_dir("faqbot")
if not os.path.exists(config_dir):
    os.makedirs(config_dir)
def_accounts_dir = os.path.join(config_dir, "accounts")


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser("faqbot")
    parser.add_argument(
        "--accounts",
        "-a",
        help="accounts folder (default: %(default)s)",
        metavar="PATH",
        default=def_accounts_dir,
    )
    subparsers = parser.add_subparsers(title="subcommands")

    init_parser = subparsers.add_parser("init", help="initialize the account")
    init_parser.add_argument("addr", help="the e-mail address to use")
    init_parser.add_argument("password", help="account password")
    init_parser.set_defaults(cmd=init_cmd)

    config_parser = subparsers.add_parser(
        "config", help="set/get account configuration values"
    )
    config_parser.add_argument("option", help="option name", nargs="?")
    config_parser.add_argument("value", help="option value to set", nargs="?")
    config_parser.set_defaults(cmd=config_cmd)

    avatar_parser = subparsers.add_parser("set_avatar", help="set account avatar")
    avatar_parser.add_argument("path", help="path to avatar image", nargs="?")
    avatar_parser.set_defaults(cmd=set_avatar_cmd)

    return parser


async def init_cmd(bot: Bot, args: argparse.Namespace) -> None:
    print("Configuring...")
    asyncio.create_task(bot.configure(email=args.email, password=args.password))
    await bot.run_forever()


async def config_cmd(bot: Bot, args: argparse.Namespace) -> None:
    if args.value:
        await bot.account.set_config(args.option, args.value)

    if args.option:
        try:
            value = await bot.account.get_config(args.option)
            print(f"{args.option}={value!r}")
        except JsonRpcError:
            print(f"Unknown configuration option: {args.option}")
    else:
        keys = (await bot.account.get_config("sys.config_keys")) or ""
        for key in keys.split():
            value = await bot.account.get_config(key)
            print(f"{key}={value!r}")


async def set_avatar_cmd(bot: Bot, args: argparse.Namespace) -> None:
    await bot.account.set_avatar(args.path)
    if args.path:
        print("Avatar updated.")
    else:
        print("Avatar removed.")


async def _main():
    args = get_parser().parse_args()

    path = os.path.join(config_dir, "sqlite.db")
    await init(f"sqlite+aiosqlite:///{path}")
    async with Rpc(accounts_dir=args.accounts) as rpc:
        deltachat = DeltaChat(rpc)
        core_version = (await deltachat.get_system_info()).deltachat_core_version
        accounts = await deltachat.get_all_accounts()
        account = accounts[0] if accounts else await deltachat.add_account()

        bot = Bot(account, hooks)
        bot.logger.debug("Running deltachat core %s", core_version)
        if "cmd" in args:
            await args.cmd(bot, args)
        else:
            if await bot.is_configured():
                await bot.run_forever()
            else:
                print("Account is not configured")


def main():
    asyncio.run(_main())
