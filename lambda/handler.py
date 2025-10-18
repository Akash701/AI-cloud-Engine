import boto3
import os
import datetime
import json
import requests
import time
from decimal import Decimal
import logging
import signal
import contextlib
import uuid
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# -------- Helpers -------- #

def get_deepseek_api_key():
    """Get DeepSeek API key from Environment Variables"""
    api_key = os.getenv('DEEPSEEK_API_KEY')  # Change this!
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY environment variable not set")
    print(f"[DEBUG] Using API key from env, length: {len(api_key)}")
    return api_key

def call_deepseek_api(api_key, prompt, retries=2):
    """Call DeepSeek API instead of OpenAI"""
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    body = {
        "model": "deepseek-chat",  
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "max_tokens": 500,
        "temperature": 0.3,
        "stream": False  
    }

    last_error = None 
    for i in range(retries):
        try:
            print(f"[DEBUG] Attempt {i+1} - Calling DeepSeek API...")
            
            resp = requests.post(url, headers=headers, json=body, timeout=20)
            print(f"[DEBUG] Response status: {resp.status_code}")
            
            resp.raise_for_status()
            data = resp.json()
            print(f"[DEBUG] DeepSeek response received successfully")
            return data["choices"][0]["message"]["content"]
            
        except requests.exceptions.Timeout:
            error_msg = f"DeepSeek API timeout on attempt {i+1}"
            print(error_msg)
            last_error = error_msg
            if i < retries - 1:  
                time.sleep(1)
            continue  
            
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error {resp.status_code}: {resp.text}")
            last_error = e
            
            if hasattr(e, 'response') and e.response.status_code >= 500:
                if i < retries - 1:
                    time.sleep(1)
                    continue
            break  
            
        except Exception as e:
            print(f"Attempt {i+1} failed: {e}")
            last_error = e
            if i < retries - 1:
                time.sleep(1)
    
    if last_error:
        return f""" **AWS Cost Analysis** (AI Service Temporarily Unavailable)

I encountered an issue with the AI analysis service. Please try again in a few moments.

Technical details: {str(last_error)}"""
    else:
        return "Unable to analyze costs at the moment. Please try again later."

def build_prompt(cost_summary: dict, instructions: str, user_id: str = None) -> str:
    """Build the prompt for DeepSeek with conversation history"""
    summary_lines = ["Here is the recent AWS cost breakdown:"]
    for service, cost in cost_summary.items():
        summary_lines.append(f"- {service}: ${cost:.2f}")
    summary_text = "\n".join(summary_lines)

    instruction_text = f"\n\nInstructions: {instructions}"

    # Add conversation history if user_id provided
    history_text = ""
    if user_id:
        recent_history = get_recent_history(user_id, limit=5)
        if recent_history:
            history_text = "\n\nRecent conversation history (for context):\n"
            for chat in recent_history:
                # Truncate long responses to save tokens
                truncated_answer = chat['answer'][:200] + "..." if len(chat['answer']) > 200 else chat['answer']
                history_text += f"User: {chat['question']}\n"
                history_text += f"Assistant: {truncated_answer}\n\n"

    full_prompt = f"""{summary_text}{instruction_text}{history_text}

Please provide a clear, helpful analysis of these AWS costs. Consider the conversation history if provided to maintain context and avoid repeating information."""
    
    print(f"[DEBUG] Prompt built with history: {len(history_text) > 0}")
    return full_prompt

def get_last_n_days_cost(n: int):
    """Fetch AWS cost data"""
    ce = boto3.client('ce')
    end = datetime.date.today()
    start = end - datetime.timedelta(days=n)

    response = ce.get_cost_and_usage(
        TimePeriod={'Start': start.strftime('%Y-%m-%d'), 'End': end.strftime('%Y-%m-%d')},
        Granularity='DAILY',
        Metrics=['UnblendedCost'],
        GroupBy=[{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
    )

    cost_summary = {}
    for result_by_time in response.get('ResultsByTime', []):
        for group in result_by_time['Groups']:
            service = group['Keys'][0]
            amount = Decimal(group['Metrics']['UnblendedCost']['Amount'])
            cost_summary[service] = cost_summary.get(service, Decimal(0)) + amount

    print(f"[DEBUG] Retrieved costs for {len(cost_summary)} services")
    return {k: float(v) for k, v in cost_summary.items()}

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Function timed out!")

# -------- Lambda Entrypoint -------- #

def lambda_handler(event, context):
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(25)
    try:
        print(f"[DEBUG] Lambda invoked with event: {json.dumps(event)}")
        
        # Get parameters from event
        days = event.get('days', 7)
        instructions = event.get('instructions', "Summarize AWS costs in plain English.")
        chat_history = event.get('chat_history', [])
        user_id = event.get('user_id', 'default_user')

        if not user_id and chat_history:
            user_id = 'legacy_user'
       
        cost_summary = get_last_n_days_cost(days)
        print(f"[DEBUG] Cost summary: {cost_summary}")

        prompt = build_prompt(cost_summary, instructions, user_id)
        deepseek_api_key = get_deepseek_api_key()  
        answer = call_deepseek_api(deepseek_api_key, prompt)
        if user_id and user_id not in ['default_user', 'legacy_user']:
            save_chat(user_id, instructions, answer)
        return {
            "statusCode": 200,
            "body": json.dumps({
                "cost_data": cost_summary,
                "analysis": answer,
                "days_analyzed": days,
                "user_id": user_id or 'anonymous'
            })
        }
    except TimeoutException:
         logger.error("Lambda timed out after 25 seconds")
         return {
            "statusCode": 200,
            "body": json.dumps({
                "error": "Request timed out",
                "fallback_analysis": "Cost analysis is taking longer than expected. Try with fewer days (1-3) for faster results."
            })
        }
    except Exception as e:
        logger.error(f"Lambda failed: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
    finally:
        signal.alarm(0)

def save_chat(user_id, question, answer):
    """Save conversation to DynamoDB"""
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('chat-history')
    
    try:
        item = {
            'user_id': user_id,
            'timestamp': datetime.utcnow().isoformat(),
            'question': question,
            'answer': answer,
            'message_id': str(uuid.uuid4())  # For uniqueness
        }
        
        table.put_item(Item=item)
        print(f"✅ Saved chat history for user: {user_id}")
        return True
    except Exception as e:
        print(f"❌ Error saving chat history: {e}")
        return False

def get_recent_history(user_id, limit=5):
    """Get recent conversation history for a user"""
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('chat-history')
    
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user_id),
            ScanIndexForward=False,  # Most recent first (descending)
            Limit=limit,
            IndexName='UserTimestampIndex'  # Use GSI for efficient querying
        )
        
        # Return in chronological order (oldest first) for context
        history = sorted(response.get('Items', []), 
                        key=lambda x: x['timestamp'])
        
        print(f"✅ Retrieved {len(history)} recent messages for user: {user_id}")
        return history
    except Exception as e:
        print(f"❌ Error fetching history: {e}")
        return []
    


