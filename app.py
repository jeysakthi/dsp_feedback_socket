
import os
import time
import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")  # Required for Socket Mode

# Initialize Bolt App
app = App(token=SLACK_BOT_TOKEN)

# In-memory storage
feedback_store = []
user_feedback_state = {}

# ---------------------------
# Slack API helpers
# ---------------------------
def get_user_name(user_id):
    url = "https://slack.com/api/users.info"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    params = {"user": user_id}
    resp = requests.get(url, headers=headers, params=params).json()
    print(f"✅ Fetched user name for {user_id}: {resp}")
    return resp.get("user", {}).get("real_name", "Unknown")

def get_channel_name(channel_id):
    url = "https://slack.com/api/conversations.info"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    params = {"channel": channel_id}
    resp = requests.get(url, headers=headers, params=params).json()
    print(f"✅ Fetched channel name for {channel_id}: {resp}")
    return resp.get("channel", {}).get("name", "Unknown")

def send_slack_message(url, payload):
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}", "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=payload)
    print(f"✅ Slack API Response: {resp.status_code}, {resp.text}")
    return resp.json()

# ---------------------------
# Send Yes button
# ---------------------------
def send_yes_button(channel, thread_ts):
    url = "https://slack.com/api/chat.postMessage"
    payload = {
        "channel": channel,
        "thread_ts": thread_ts,
        "text": "Would you like to provide feedback?",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "Would you like to provide feedback?"},
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Yes"},
                    "style": "primary",
                    "action_id": "show_feedback_form"
                }
            }
        ]
    }
    print(f"✅ Sending Yes button to channel {channel}, thread {thread_ts}")
    send_slack_message(url, payload)

# ---------------------------
# Send feedback form and capture ts
# ---------------------------
def send_feedback_form(channel, thread_ts, user_id):
    url = "https://slack.com/api/chat.postMessage"
    payload = {
        "channel": channel,
        "thread_ts": thread_ts,
        "text": "Please provide your feedback",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*Rate your experience (1-10):*"},
                "accessory": {
                    "type": "static_select",
                    "action_id": "rating_select",
                    "placeholder": {"type": "plain_text", "text": "Select a rating"},
                    "options": [{"text": {"type": "plain_text", "text": str(i)}, "value": str(i)} for i in range(1, 11)]
                }
            },
            {
                "type": "input",
                "block_id": "feedback_block",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "feedback_text",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Your feedback here..."}
                },
                "label": {"type": "plain_text", "text": "Feedback (optional)"}
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Submit Feedback"},
                        "style": "primary",
                        "action_id": "submit_feedback"
                    }
                ]
            }
        ]
    }
    print(f"✅ Sending feedback form to channel {channel}, thread {thread_ts}")
    resp = send_slack_message(url, payload)
    form_ts = resp.get("ts")
    if user_id and form_ts:
        user_feedback_state[user_id] = user_feedback_state.get(user_id, {})
        user_feedback_state[user_id]["form_ts"] = form_ts
        print(f"✅ Captured form message ts: {form_ts}")

# ---------------------------
# Update form with personalized thank you
# ---------------------------
def update_feedback_form(channel, ts, user_name):
    url = "https://slack.com/api/chat.update"
    payload = {
        "channel": channel,
        "ts": ts,
        "text": "Feedback submitted ✅",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"Thank you, *{user_name}*! Your feedback has been recorded."}
            }
        ]
    }
    print(f"✅ Updating feedback form for channel {channel}, ts {ts}")
    send_slack_message(url, payload)

# ---------------------------
# Event: Listen for messages
# ---------------------------
@app.event("message")
def handle_message_events(body, say):
    event = body.get("event", {})
    user_text = event.get("text", "")
    channel_id = event.get("channel", "")
    thread_ts = event.get("thread_ts", event.get("ts", ""))

    print(f"✅ Received message: {user_text} in channel {channel_id}, thread {thread_ts}")

    if "This issue is resolved" in user_text:
        print("✅ Trigger phrase detected, sending Yes button...")
        send_yes_button(channel_id, thread_ts)

# ---------------------------
# Action: Yes button clicked
# ---------------------------
@app.action("show_feedback_form")
def handle_yes_button(ack, body):
    ack()
    user_id = body.get("user", {}).get("id")
    channel_id = body.get("channel", {}).get("id")
    thread_ts = body.get("container", {}).get("thread_ts") or body.get("container", {}).get("message_ts")

    state = user_feedback_state.get(user_id, {})
    if thread_ts in state.get("submitted_threads", []):
        print("❌ User already submitted feedback for this thread.")
        return

    user_name = get_user_name(user_id)
    user_feedback_state[user_id] = user_feedback_state.get(user_id, {})
    user_feedback_state[user_id]["user_name"] = user_name
    print(f"✅ Yes button clicked by {user_name}. Channel: {channel_id}, Thread TS: {thread_ts}")
    send_feedback_form(channel_id, thread_ts, user_id)

# ---------------------------
# Action: Rating selected
# ---------------------------
@app.action("rating_select")
def handle_rating_select(ack, body):
    ack()
    user_id = body.get("user", {}).get("id")
    rating = body["actions"][0].get("selected_option", {}).get("value")
    if user_id and rating:
        user_feedback_state[user_id] = user_feedback_state.get(user_id, {})
        user_feedback_state[user_id]["rating"] = rating
        print(f"✅ Rating selected: {rating}")

# ---------------------------
# Action: Feedback text entered
# ---------------------------
@app.action("feedback_text")
def handle_feedback_text(ack, body):
    ack()
    user_id = body.get("user", {}).get("id")
    feedback_text = body["actions"][0].get("value", "")
    if user_id:
        user_feedback_state[user_id] = user_feedback_state.get(user_id, {})
        user_feedback_state[user_id]["comments"] = feedback_text
        print(f"✅ Feedback text entered: {feedback_text}")

# ---------------------------
# Action: Submit feedback
# ---------------------------
@app.action("submit_feedback")
def handle_submit_feedback(ack, body):
    ack()
    user_id = body.get("user", {}).get("id")
    channel_id = body.get("channel", {}).get("id")
    thread_ts = body.get("container", {}).get("thread_ts") or body.get("container", {}).get("message_ts")
    state = user_feedback_state.get(user_id, {})

    if thread_ts in state.get("submitted_threads", []):
        print("❌ Duplicate submission detected for this thread!")
        return

    rating = state.get("rating")
    comments = ""
    state_values = body.get("state", {}).get("values", {})
    if "feedback_block" in state_values:
        comments = state_values["feedback_block"]["feedback_text"].get("value", "")

    if not rating:
        print("❌ Rating missing!")
        return

    state.setdefault("submitted_threads", []).append(thread_ts)
    user_name = state.get("user_name") or get_user_name(user_id)
    channel_name = get_channel_name(channel_id)
    timestamp = time.time()

    feedback_data = {
        "channel_name": channel_name,
        "channel_id": channel_id,
        "user_id": user_id,
        "user_name": user_name,
        "thread_ts": thread_ts,
        "rating": rating,
        "comments": comments,
        "timestamp": timestamp
    }
    print("✅ Final Feedback Data:", feedback_data)

    feedback_store.append(feedback_data)
    requests.post("https://feedback-jeysakthi1140-p6js52a9.leapcell.dev/feedback", json=feedback_data)

    form_ts = state.get("form_ts")
    if form_ts:
        update_feedback_form(channel_id, form_ts, user_name)
    else:
        print("❌ No form_ts found, cannot update form message!")

# ---------------------------
# Start Socket Mode
# ---------------------------
if __name__ == "__main__":
    print("✅ Starting Slack bot in Socket Mode...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()
