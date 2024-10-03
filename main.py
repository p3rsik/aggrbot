import json
import argparse
import os
from datetime import datetime, timedelta
from telethon import TelegramClient
import openai

async def fetch_messages(client, channel, since_time):
    messages = []
    async for message in client.iter_messages(channel, offset_date=since_time):
        messages.append({
            'date': message.date.isoformat(),
            'text': message.text
        })
    return messages

async def fetch_summary_message(client, since_time, filter_rule):
    async for message in client.iter_messages('hardcoded', offset_date=since_time):
        if filter_rule(message):
            return {
                'date': message.date.isoformat(),
                'text': message.text
            }
    return None

async def main(client, all_channels):
    # Time window for the last 24 hours
    now = datetime.now(datetime.UTC)
    since_time = now - timedelta(hours=24)

    # Fetch summary message with a filter rule (e.g., message contains 'Summary')
    filter_rule = lambda m: 'summary' in m.text.lower() if m.text else False
    summary_message = await fetch_summary_message(client, since_time, filter_rule)
    summary = summary_message['text'] if summary_message else "No summary message found"

    # Fetch messages from additional channels
    channels_data = {}
    for channel in all_channels:
        messages = await fetch_messages(client, channel, since_time)
        channels_data[channel] = messages

    # Compile the data
    data = {
        'summary_message': summary,
        'channels': channels_data
    }

    # Write the collected data to a JSON file
    with open('messages.json', 'w') as f:
        json.dump(data, f, indent=4)

    # Send data to ChatGPT API for filtering and compiling
    chatgpt_response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"{args.prompt}\n\n{json.dumps(data, indent=4)}"}
        ]
    )

    # Extract the response from ChatGPT
    compiled_result = chatgpt_response['choices'][0]['message']['content']

    # Save the ChatGPT response in Markdown format
    with open('output.md', 'w') as f:
        f.write(compiled_result)

def parse_args():
    parser = argparse.ArgumentParser(description="Fetch Telegram messages for the last 24 hours")
    
    # Optional CLI arguments for API keys
    parser.add_argument('--api-id', type=str, help="Telegram API ID")
    parser.add_argument('--api-hash', type=str, help="Telegram API Hash")
    parser.add_argument('--openai-key', type=str, help="OpenAI API Key")
    
    # Optional CLI argument for additional channels
    parser.add_argument('--add-channels', nargs='+', default=[], 
                        help="List of additional channels to fetch messages from")
    
    # Optional CLI argument for ChatGPT prompt
    parser.add_argument('--prompt', type=str, default="Filter and summarize the following data:",
                        help="Prompt to guide ChatGPT in processing the collected data")

    return parser.parse_args()

if __name__ == '__main__':
    # Parse CLI arguments
    args = parse_args()

    # Get API credentials: CLI args > Environment Variables
    api_id = args.api_id or os.getenv('TELEGRAM_API_ID')
    api_hash = args.api_hash or os.getenv('TELEGRAM_API_HASH')
    openai_key = args.openai_key or os.getenv('OPENAI_API_KEY')

    # Ensure required keys are available
    if not api_id or not api_hash or not openai_key:
        raise ValueError("API credentials (Telegram API ID, API Hash, OpenAI API Key) must be provided either via CLI args or environment variables")

    # Set OpenAI API key
    openai.api_key = openai_key

    # Combine default channels with any additional ones from --add-channels
    default_channels = ['channel1', 'channel2']  # Replace with actual defaults
    all_channels = default_channels + args.add_channels

    # Start the Telegram client
    client = TelegramClient('aggrbot', api_id, api_hash)
    with client:
        client.loop.run_until_complete(main(client, all_channels))

