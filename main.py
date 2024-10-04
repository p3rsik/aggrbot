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
        if message.text:
            messages.append(
                {
                    "id": message.id,
                    "date": message.date.strftime("%d.%m.%y %H:%M:%S"),
                    "text": message.text,
                }
            )
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
            return {
                "id": message.id,
                "date": message.date.strftime("%d.%m.%y %H:%M:%S"),
                "text": message.text,
            }
    return None


def process_data(data, save_dir):
    logger.info("Summarizing data using OpenAI API")
    client = openai.OpenAI()

    now = datetime.now()

    _prompt = """ Filter and summarize data given to you. \
        Include only data pertaining to used weaponry, its sightning locations, \
        its movements at any time and if it was destroyed/disarmed/tracking lost. \
        Response should contain summary of when \
        the alarm started/stopped(give time periods if there were more than one), \
        amount and types of weaponry used in each one and it's trajectories. \
        Try to give time periods for regions(oblast) if possible, \
        if not, just specify the general time period of the alarms. \
        Include the sources(channel names and message date) for the given information. \
        Give the answer in markdown, in Ukrainian language."""

    filtering_prompt = """\
        Filter out any information that does not relate to the air alerts \
        or weaponry location/trajectory/type/etc from the given data, \
        return back the same json file in the same format excluding \
        the messages you've filtered out."""

    if not os.path.exists(f"{save_dir}/{now.date()}/openai-filtered.json"):
        # Send data to ChatGPT API for filtering and compiling
        chatgpt_response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format=openai.types.ResponseFormatJSONObject,
            messages=[
                {
                    "role": "system",
                    "content": "You are a data analyzer.",
                },
                {
                    "role": "user",
                    "content": filtering_prompt,
                },
                {
                    "role": "user",
                    "content": f"The data:\n{json.dumps(data)}",
                },
            ],
        )
        # Extract the response from ChatGPT
        filtered_result = chatgpt_response.choices[0].message.content

        # Save the ChatGPT response in Markdown format
        with open(f"{save_dir}/{now.date()}/openai-filtered.json", "w") as f:
            json.dump(filtered_result, f)


async def main(
    client, all_channels, prompt, save_dir, refresh=False, openai_step=False
):
    # Time window to fetch messages from
    now = datetime.now()
    # TODO tune the time window
    since_time = now - timedelta(hours=24)

    if not os.path.exists(f"{save_dir}/{now.date()}"):
        os.mkdir(f"{save_dir}/{now.date()}")

    # Skip if report for this day already exists and user didn't specify refresh=True
    if (not os.path.exists(f"{save_dir}/{now.date()}/messages.json")) or refresh:
        async with client:
            summary_message = await fetch_summary_message(client)

            # Fetch messages from additional channels
            channels_data = {}
            for channel in all_channels:
                messages = await fetch_messages(client, channel, since_time)
                channels_data[channel] = messages

            # Compile the data
            data = {"summary": summary_message, "channels": channels_data}

            # Write the collected data to a JSON file
            with open(
                f"{save_dir}/{now.date()}/messages.json", "w", encoding="utf8"
            ) as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
    else:
        with open(f"{save_dir}/{now.date()}/messages.json", "r", encoding="utf8") as f:
            data = json.load(f)

    # Skip openai step if not True
    if openai_step:
        client.loop.run_in_executor(None, process_data, data)


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
        help="Directory where to save the reports",
    )

    # Optional CLI argument to include openai processing step
    parser.add_argument(
        "--openai-processing",
        action=argparse.BooleanOptionalAction,
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

    parser.add_argument(
        "-r",
        "--refresh",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="If True, collects the data for today anew and overwrites existing one",
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
    default_channels = [
        "vanek_nikolaev",
        "monitor_ukr",
        "war_monitor",
        "monitorwarr",
        "dsns_telegram",
        "dsns_kyiv_region",
        "gu_dsns_zp",
        "dsns_sumy",
        "dsns_mykolaiv",
        "dsns_lviv",
        "dsns_kherson",
    ]  # Default additional channels to fetch info from
    all_channels = default_channels + args.add_channels

    # Start the Telegram client and run the script
    client = TelegramClient("aggrbot", api_id, api_hash)
    client.loop.run_until_complete(
        main(
            client,
            all_channels,
            args.prompt,
            refresh=args.refresh,
            save_dir=args.save_dir,
            openai_step=args.openai_processing,
        )
    )
