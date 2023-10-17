# FAQ Bot

[![Latest Release](https://img.shields.io/pypi/v/deltachat-faqbot.svg)](https://pypi.org/project/deltachat-faqbot)
[![CI](https://github.com/deltachat-bot/faqbot/actions/workflows/python-ci.yml/badge.svg)](https://github.com/deltachat-bot/faqbot/actions/workflows/python-ci.yml)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A simple FAQ Bot for Delta Chat groups

## Install

```sh
pip install deltachat-faqbot
```

### Installing deltachat-rpc-server

This package depends on a standalone Delta Chat RPC server `deltachat-rpc-server` program.
To install it check:
https://github.com/deltachat/deltachat-core-rust/tree/master/deltachat-rpc-server

## Usage

Configure the bot:

```sh
faqbot init bot@example.com PASSWORD
```

Start the bot:

```sh
faqbot serve
```

Run `faqbot --help` to see all available options.
