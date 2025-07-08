from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
from datetime import datetime
import os
from dotenv import load_dotenv
from datetime import timedelta


# Initialize Flask app
app = Flask(__name__)

# Load environment variables
load_dotenv()
MONGO_URI = os.getenv("mongodb+srv://webhookuser:webhookpass123@cluster0.rabc123.mongodb.net/")
DB_NAME = "webhook_db"

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db["actions"]

# Webhook endpoint
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    event_type = request.headers.get("X-GitHub-Event")

    if not data or not event_type:
        return jsonify({"error": "Invalid payload or event type"}), 400

    # Initialize document
    document = {
        "request_id": None,
        "author": None,
        "action": None,
        "from_branch": None,
        "to_branch": None,
        "timestamp": (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M:%S IST")
    }

    if event_type == "push":
        commits = data.get("commits", [])
        is_merge = False
        for commit in commits:
            if "Merge" in commit.get("message", ""):
                # Handle as MERGE
                document["action"] = "MERGE"
                document["request_id"] = commit["id"]
                document["author"] = commit["author"]["name"]
                document["to_branch"] = data["ref"].split("/")[-1]

                # Try to extract 'from_branch' from merge message
                message = commit["message"]
                if "Merge branch" in message:
                    parts = message.split("'")
                    if len(parts) > 1:
                        document["from_branch"] = parts[1]
                is_merge = True
                break

            if not is_merge:
                # Handle as regular PUSH
                document["action"] = "PUSH"
                document["request_id"] = data["after"]
                document["author"] = data["pusher"]["name"]
                document["to_branch"] = data["ref"].split("/")[-1]
                document["from_branch"] = None


    elif event_type == "pull_request":
        if data["action"] in ["opened", "reopened"]:
            document["action"] = "PULL_REQUEST"
            document["request_id"] = str(data["pull_request"]["id"])
            document["author"] = data["pull_request"]["user"]["login"]
            document["from_branch"] = data["pull_request"]["head"]["ref"]
            document["to_branch"] = data["pull_request"]["base"]["ref"]

    elif event_type == "push" and data.get("created") is False and data.get("deleted") is False:
        # Detecting a merge by checking if the push is to a branch with a merge commit
        commits = data.get("commits", [])
        for commit in commits:
            if "Merge" in commit["message"]:
                document["action"] = "MERGE"
                document["request_id"] = commit["id"]
                document["author"] = commit["author"]["name"]
                document["to_branch"] = data["ref"].split("/")[-1]
                # Extract source branch from commit message (e.g., "Merge branch 'dev' into 'master'")
                message = commit["message"]
                if "Merge branch" in message:
                    parts = message.split("'")
                    if len(parts) > 1:
                        document["from_branch"] = parts[1]
                break

    # Save to MongoDB if action is set
    if document["action"]:
        collection.insert_one(document)
        return jsonify({"status": "success"}), 200
    else:
        return jsonify({"status": "ignored"}), 200

# API to fetch events for the UI
@app.route("/events", methods=["GET"])
def get_events():
    events = list(collection.find({}, {"_id": 0}).sort("timestamp", -1).limit(100))
    formatted_events = []
    for event in events:
        if event["action"] == "PUSH":
            formatted_events.append(f"{event['author']} pushed to {event['to_branch']} on {event['timestamp']}")
        elif event["action"] == "PULL_REQUEST":
            formatted_events.append(
                f"{event['author']} submitted a pull request from {event['from_branch']} to {event['to_branch']} on {event['timestamp']}"
            )
        elif event["action"] == "MERGE":
            formatted_events.append(
                f"{event['author']} merged branch {event['from_branch']} to {event['to_branch']} on {event['timestamp']}"
            )
    return jsonify(formatted_events)

# Render the UI
@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)