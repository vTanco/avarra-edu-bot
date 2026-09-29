#!/usr/bin/env python3
"""Script to wait for a user to send /start to the Telegram bot and auto-save the chat_id."""

import os
import sys
import time
from pathlib import Path
import httpx

from navarra_edu_bot.config.keychain import read_secret


def get_token() -> str:
    try:
        return read_secret("telegram-token")
    except Exception:
        token = os.environ.get("TELEGRAM_TOKEN")
        if not token:
            print("Error: TELEGRAM_TOKEN not found in .env or environment.")
            sys.exit(1)
        return token


def update_env_files(chat_id: int) -> None:
    for target in (Path(".env"), Path(".env.jasier")):
        if target.exists():
            content = target.read_text()
            lines = content.splitlines()
            new_lines = []
            found = False
            for line in lines:
                if line.startswith("TELEGRAM_CHAT_ID="):
                    new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
                    found = True
                else:
                    new_lines.append(line)
            if not found:
                new_lines.append(f"TELEGRAM_CHAT_ID={chat_id}")
            target.write_text("\n".join(new_lines) + "\n")
            print(f"Updated {target} with TELEGRAM_CHAT_ID={chat_id}")


def main() -> None:
    token = get_token()
    print(f"Connecting to bot with token {token[:10]}...")
    url = f"https://api.telegram.org/bot{token}/getUpdates"

    # Verify bot
    me_resp = httpx.get(f"https://api.telegram.org/bot{token}/getMe").json()
    if not me_resp.get("ok"):
        print("Error connecting to bot:", me_resp)
        sys.exit(1)

    bot_info = me_resp["result"]
    print(f"Bot active: @{bot_info.get('username')} ({bot_info.get('first_name')})")
    print("\nWaiting for Hasier (or you) to send /start or any message in Telegram...")
    print(f"Open link: https://t.me/{bot_info.get('username')}\n")

    offset = None
    while True:
        try:
            params = {"timeout": 20}
            if offset:
                params["offset"] = offset
            resp = httpx.get(url, params=params, timeout=25.0)
            data = resp.json()
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    offset = update["update_id"] + 1
                    msg = update.get("message") or update.get("channel_post")
                    if msg:
                        sender = msg.get("from", {})
                        chat = msg.get("chat", {})
                        chat_id = chat.get("id")
                        name = f"{sender.get('first_name', '')} {sender.get('last_name', '')}".strip()
                        username = sender.get("username", "N/A")
                        text = msg.get("text", "")
                        print(f"\nMessage received!")
                        print(f"  From: {name} (@{username})")
                        print(f"  Chat ID: {chat_id}")
                        print(f"  Text: {text}")
                        update_env_files(chat_id)
                        print("\nSetup complete! You can now run the bot.")
                        return
            time.sleep(1)
        except KeyboardInterrupt:
            print("\nAborted.")
            sys.exit(0)
        except Exception as exc:
            print(f"Polling error: {exc}")
            time.sleep(2)


if __name__ == "__main__":
    main()
