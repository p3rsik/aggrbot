import json
import argparse
import os
import openai
import logging
from datetime import datetime, timedelta, UTC
from telethon import TelegramClient

logging.basicConfig(
    format="[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


async def fetch_messages(client, channel, since_time):
    logger.info(f"Fetching messages from: {channel}")
    messages = []
    async for message in client.iter_messages(
        channel, reverse=True, offset_date=since_time
    ):
        messages.append({"date": message.date.isoformat(), "text": message.text})
    return messages


async def fetch_summary_message(client):
    logger.info("Fetching summary message")
    async for message in client.iter_messages("kpszsu", limit=200):
        if (
            message.text
            and message.photo
            and ("збито" in message.text.lower())
            and ("➖" in message.text)
        ):
            return {"date": message.date.isoformat(), "text": message.text}
    return None


async def main(client, all_channels, save_dir="./reports", openai_step=False):
    # Time window to fetch messages from
    now = datetime.now(UTC)
    # TODO tune the time window
    since_time = now - timedelta(hours=12)

    summary_message = await fetch_summary_message(client)

    # Fetch messages from additional channels
    channels_data = {}
    for channel in all_channels:
        messages = await fetch_messages(client, channel, since_time)
        channels_data[channel] = messages

    # Compile the data
    data = {"summary": summary_message, "channels": channels_data}

    # Write the collected data to a JSON file
    with open(f"{save_dir}/messages-{now.date()}.json", "w", encoding="utf8") as f:
        print(f"Summary:\n{summary_message['text']}")
        json.dump(data, f, indent=4, ensure_ascii=False)

    # Skip openai step if not True
    if not openai_step:
        return

    # Send data to ChatGPT API for filtering and compiling
    chatgpt_response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {
                "role": "user",
                "content": f"{args.prompt}\n\n{json.dumps(data, indent=4)}",
            },
        ],
    )

    # Extract the response from ChatGPT
    compiled_result = chatgpt_response["choices"][0]["message"]["content"]

    # Save the ChatGPT response in Markdown format
    with open("output.md", "w") as f:
        f.write(compiled_result)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Fetch Telegram messages for the last 24 hours"
    )

    # Optional CLI arguments for API keys
    parser.add_argument("--api-id", type=str, help="Telegram API ID")
    parser.add_argument("--api-hash", type=str, help="Telegram API Hash")
    parser.add_argument("--openai-key", type=str, help="OpenAI API Key")

    # Optional CLI argument to change the directory where report is saved
    parser.add_argument(
        "-d",
        "--save-dir",
        default="./reports",
        help="Directory where to save the reports"
    )

    # Optional CLI argument to include openai processing step
    parser.add_argument(
        "--openai-processing",
        default=False,
        help="If True, takes additional step to process collected info through OpenAI API",
    )

    # Optional CLI argument for additional channels
    parser.add_argument(
        "-a",
        "--add-channels",
        nargs="+",
        default=[],
        help="List of additional channels to fetch messages from",
    )

    # Optional CLI argument for ChatGPT prompt
    parser.add_argument(
        "-p",
        "--prompt",
        type=str,
        default="Filter and summarize the following data:",
        help="Prompt to guide ChatGPT in processing the collected data",
    )

    return parser.parse_args()


if __name__ == "__main__":
    # Parse CLI arguments
    args = parse_args()

    # Get API credentials: CLI args > Environment Variables
    api_id = args.api_id or os.getenv("TELEGRAM_API_ID")
    api_hash = args.api_hash or os.getenv("TELEGRAM_API_HASH")
    openai_key = args.openai_key or os.getenv("OPENAI_API_KEY")

    # Ensure required keys are available
    if not api_id or not api_hash or not openai_key:
        raise ValueError(
            "API credentials (Telegram API ID, API Hash, OpenAI API Key) must be provided either via CLI args or environment variables"
        )

    # Set OpenAI API key
    openai.api_key = openai_key

    # Combine default channels with any additional ones from --add-channels
    default_channels = []  # Default additional channels to fetch info from
    all_channels = default_channels + args.add_channels

    # Start the Telegram client and run the script
    with TelegramClient("aggrbot", api_id, api_hash) as client:
        client.loop.run_until_complete(main(client, all_channels, save_dir=args.save_dir, openai_step=args.openai_processing))
