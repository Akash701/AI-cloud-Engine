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

# -------- Initialize Clients -------- #
ce_client = boto3.client('ce')
ssm = boto3.client('ssm')
lambda_client = boto3.client('lambda')
dynamodb = boto3.resource('dynamodb')

# Configuration
TABLE_NAME = "chat-history"
table = dynamodb.Table(TABLE_NAME)

# -------- Secret Management -------- #

def get_secret(parameter_name):
    """Fetch secure parameter from SSM"""
    if not parameter_name: return None
    try:
        response = ssm.get_parameter(Name=parameter_name, WithDecryption=True)
        return response['Parameter']['Value']
    except Exception as e:
        print(f"❌ Secret Error: {e}")
        return None

# Load Secrets from SSM (Paths provided by Terraform)
SLACK_SIGNING_SECRET = get_secret(os.getenv('SLACK_SECRET_PATH'))
DEEPSEEK_API_KEY = get_secret(os.getenv('DEEPSEEK_API_KEY_PATH'))

# -------- Knowledge Base (Terraform Templates) -------- #

def get_terraform_hints(cost_summary):
    """Returns relevant Terraform snippets based on the cost driver."""
    if not cost_summary:
        return ""
    
    # Sort services by cost
    expensive_service = max(cost_summary, key=cost_summary.get)
    print(f"🔍 DEBUG: Cost driver identified as: '{expensive_service}'")
    
    # Keyword-based matching (More robust than exact match)
    hints = {
        "Compute": """
        # TIP: Use Spot Instances for non-critical workloads to save money.
        resource "aws_launch_template" "example" {
          instance_market_options {
            market_type = "spot"
          }
        }
        """,
        
        "Storage": """
        # TIP: Use Lifecycle Rules to move old S3 data to Glacier.
        resource "aws_s3_bucket_lifecycle_configuration" "bucket-config" {
          rule {
            id = "archive"
            status = "Enabled"
            transition {
              days = 30
              storage_class = "STANDARD_IA"
            }
          }
        }
        """,
        
        "VPC": """
        # TIP: NAT Gateways are expensive (~$32/mo). If this is a dev env, delete it.
        # To remove in Terraform, comment out or delete the resource:
        # resource "aws_nat_gateway" "example" { 
        #   allocation_id = aws_eip.nat.id
        #   subnet_id     = aws_subnet.public.id
        # }
        """,
        
        "Database": """
        # TIP: Enable auto-pause for Aurora Serverless to stop charges when idle.
        resource "aws_db_instance" "default" {
          serverlessv2_scaling_configuration {
            min_capacity = 0.5
            max_capacity = 1.0
          }
        }
        """
    }
    
    # Check if any keyword matches the service name
    for keyword, snippet in hints.items():
        if keyword in expensive_service or expensive_service in keyword:
            return snippet
            
    return "No specific Terraform template available for this service."

# -------- Memory Management (DynamoDB) -------- #

def save_interaction(user_id, query, response_text):
    try:
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
    try:
        response = table.query(
            KeyConditionExpression=Key('user_id').eq(user_id),
            ScanIndexForward=False, 
            Limit=3
        )
        history = ""
        for item in reversed(response.get('Items', [])):
            history += f"User: {item['query']}\nAI: {item['response']}\n"
        return history
    except Exception as e:
        print(f"⚠️ Memory Read Error: {e}")
        return ""

# -------- Core Logic -------- #

def get_last_n_days_cost(n):
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

def build_cost_prompt(cost_summary, query, days, history):
    total = sum(cost_summary.values())
    tf_hint = get_terraform_hints(cost_summary)
    
    prompt = f"""
    Act as a Senior Cloud DevOps Engineer. 
    Analyze the following AWS spend data.
    
    DATA:
    Total: ${total:.2f}
    Breakdown: {json.dumps(cost_summary)}
    
    CHAT HISTORY:
    {history}
    
    USER QUERY: {query}
    
    CONTEXT (Reference Snippets):
    {tf_hint}
    
    INSTRUCTIONS:
    1. Identify the primary cost driver.
    2. Suggest 1 technical optimization.
    3. CRITICAL: YOU MUST PROVIDE A TERRAFORM CODE SNIPPET (HCL) based on the Context provided above. 
       Even if the savings are small, show the code for demonstration purposes.
    4. Explicitly state this is a suggestion.
    
    Output Format:
    - **Analysis:** (Short summary)
    - **Terraform Fix:** (Code block)
    - **Safety:** (Warning)
    """
    return prompt

def call_deepseek_api(prompt):
    try:
        url = "https://api.deepseek.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        body = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800
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
    user_id = payload['user_id']

    costs = get_last_n_days_cost(days)
    chat_history = get_context(user_id)
    
    prompt = build_cost_prompt(costs, query, days, chat_history)
    ai_analysis = call_deepseek_api(prompt)
    
    save_interaction(user_id, query, ai_analysis)
    
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
    print(f"Event: {json.dumps(event)[:200]}")

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
        user_id = params.get('user_id', 'unknown')
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
                "text": "🧠 Analyzing AWS costs... (Wait ~5s)"
            })
        }

    except Exception as e:
        print(f"Error: {e}")
        return {"statusCode": 200, "body": "Error processing"}