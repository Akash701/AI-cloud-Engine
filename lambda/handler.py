import json
import boto3
import os
import requests
import base64
import urllib.parse
import threading
import time
from datetime import datetime, date, timedelta
from decimal import Decimal
from boto3.dynamodb.conditions import Key

# Initialize Clients
ce_client = boto3.client('ce')
ssm = boto3.client('ssm')
lambda_client = boto3.client('lambda')
dynamodb = boto3.resource('dynamodb')

# Table Name (Matches Terraform)
TABLE_NAME = "chat-history"
table = dynamodb.Table(TABLE_NAME)

# -------- Secret Fetcher -------- #
def get_secret(parameter_name):
    if not parameter_name: return None
    try:
        response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
        return response['Parameter']['Value']
    except Exception as e:
        print(f"❌ Secret Error: {e}")
        return None

SLACK_SIGNING_SECRET = get_secret(os.getenv('SLACK_SECRET_PATH'))
DEEPSEEK_API_KEY = get_secret(os.getenv('DEEPSEEK_API_KEY_PATH'))

# -------- Memory Management (DynamoDB) -------- #

def save_interaction(user_id, query, response_text):
    """Saves the Q&A pair to DynamoDB"""
    try:
        # TTL (Time To Live) - Optional, keep chat for 3 days
        timestamp = str(int(time.time()))
        table.put_item(Item={
            'user_id': user_id,
            'timestamp': timestamp,
            'query': query,
            'response': response_text,
            'date_readable': datetime.now().isoformat()
        })
    except Exception as e:
        print(f"⚠️ Memory Write Error: {e}")

def get_context(user_id):
    """Fetches last 3 messages for context"""
    try:
        # Query last 3 items (Reverse order)
        response = table.query(
            KeyConditionExpression=Key('user_id').eq(user_id),
            ScanIndexForward=False, # Get newest first
            Limit=3
        )
        history = ""
        # Reverse back to chronological order for the AI
        for item in reversed(response.get('Items', [])):
            history += f"User: {item['query']}\nAI: {item['response']}\n"
        return history
    except Exception as e:
        print(f"⚠️ Memory Read Error: {e}")
        return ""

# -------- Core Logic -------- #

def get_last_n_days_cost(n):
    # (Same as before)
    try:
        end = date.today()
        start = end - timedelta(days=n)
        response = ce_client.get_cost_and_usage(
            TimePeriod={'Start': start.strftime('%Y-%m-%d'), 'End': end.strftime('%Y-%m-%d')},
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
            GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
        )
        cost_summary = {}
        for result in response.get('ResultsByTime', []):
            for group in result['Groups']:
                service = group['Keys'][0]
                amount = Decimal(group['Metrics']['UnblendedCost']['Amount'])
                if amount > 0:
                    cost_summary[service] = cost_summary.get(service, Decimal(0)) + amount
        return {k: float(v) for k, v in cost_summary.items()}
    except Exception:
        return {"Error": "Cost data unavailable"}

def call_deepseek_api(prompt):
    # (Same as before)
    try:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        body = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 600
        }
        response = requests.post(url, headers=headers, json=body, timeout=45)
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"AI Error: {str(e)}"

def process_background_task(payload):
    print("⏳ Starting background analysis...")
    response_url = payload['response_url']
    days = payload['days']
    query = payload['query']
    user_name = payload['user_name']
    user_id = payload['user_id'] # Needed for Memory

    # 1. Get Cost Data
    costs = get_last_n_days_cost(days)
    total = sum(costs.values())

    # 2. Fetch History (Memory)
    chat_history = get_context(user_id)

    # 3. Build Prompt with History
    prompt = f"""
    Act as a FinOps Engineer.
    
    Current Spend: ${total:.2f}
    Breakdown: {json.dumps(costs)}
    
    PREVIOUS CONVERSATION:
    {chat_history}
    
    NEW USER QUERY: {query}
    
    Answer the new query using the cost data and context.
    """
    
    # 4. Get AI Response
    ai_analysis = call_deepseek_api(prompt)
    
    # 5. Save to Memory
    save_interaction(user_id, query, ai_analysis)
    
    # 6. Post to Slack
    slack_message = {
        "response_type": "in_channel",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"💰 Cost Advisor: Last {days} Days"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*User:* {user_name}\n\n{ai_analysis}"}
            }
        ]
    }
    requests.post(response_url, json=slack_message)
    print("✅ Finished.")

# -------- Main Handler -------- #

def lambda_handler(event, context):
    # CASE 1: Background Call
    if event.get('is_background_task'):
        process_background_task(event)
        return

    # CASE 2: Slack Call
    try:
        body = event.get('body', '')
        if event.get('isBase64Encoded', False):
            body = base64.b64decode(body).decode('utf-8')
        
        params = dict(urllib.parse.parse_qsl(body))
        user_text = params.get('text', '7')
        user_name = params.get('user_name', 'User')
        user_id = params.get('user_id', 'unknown') # Capture User ID for memory
        response_url = params.get('response_url')

        days = 7
        query = "General"
        parts = user_text.split(' ', 1)
        if parts[0].isdigit():
            days = min(int(parts[0]), 60)
            if len(parts) > 1: query = parts[1]
        else:
            query = user_text

        # Async Invoke
        payload = {
            'is_background_task': True,
            'response_url': response_url,
            'days': days,
            'query': query,
            'user_name': user_name,
            'user_id': user_id
        }
        
        lambda_client.invoke(
            FunctionName=context.function_name,
            InvocationType='Event',
            Payload=json.dumps(payload)
        )

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "response_type": "ephemeral",
                "text": "🧠 Checking memory & costs... (Wait ~5s)"
            })
        }

    except Exception as e:
        print(f"Error: {e}")
        return {"statusCode": 200, "body": "Error processing"}