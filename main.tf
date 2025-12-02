
resource "terraform_data" "this" {
  input = {
    example = var.input
  }
}

resource "aws_sns_topic" "alerts" {
  name = "chat-alerts"
}

resource "aws_lambda_function" "chatbot" {
  function_name = "chatbot-lambda"
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"  
  runtime       = "python3.12"

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  timeout = 120
  memory_size = 512

  environment {
    variables = {
      DEEPSEEK_API_KEY_PATH = "/costbot/deepseek_api_key"
      SLACK_SECRET_PATH     = "/costbot/slack_signing_secret"

      SNS_TOPIC_ARN         = aws_sns_topic.cost_alerts.arn
    }
  }
}

resource "aws_sns_topic_subscription" "email_subscription" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.email_endpoint
  
}
resource "aws_dynamodb_table" "chat_history" {
  name           = "chat-history"
  billing_mode   = "PAY_PER_REQUEST"
  read_capacity  = 5
  write_capacity = 5
  hash_key       = "user_id"
  range_key      = "timestamp"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  tags = {
    Name = "chat-history"
  }

  lifecycle {
    ignore_changes = [
      read_capacity,
      write_capacity,
    ]
  }
}
resource "aws_apigatewayv2_api" "chat_api" {
  name = "chatbot-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "chat_lambda_integration" {
  api_id = aws_apigatewayv2_api.chat_api.id
  integration_type = "AWS_PROXY"
  integration_uri = aws_lambda_function.chatbot.arn
  integration_method = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "chat_route" {
  api_id = aws_apigatewayv2_api.chat_api.id
  route_key = "POST /chat"
  target = "integrations/${aws_apigatewayv2_integration.chat_lambda_integration.id}"
  authorization_type =  "NONE"  
}

resource "aws_apigatewayv2_stage" "chat_stage" {
  api_id = aws_apigatewayv2_api.chat_api.id
  name = "prod"
  auto_deploy = true
}

resource "aws_lambda_permission" "api_gateway_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.chatbot.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.chat_api.execution_arn}/*/*"
}

resource "aws_apigatewayv2_route" "slack_route" {
  api_id    = aws_apigatewayv2_api.chat_api.id
  route_key = "POST /slack"
  target    = "integrations/${aws_apigatewayv2_integration.chat_lambda_integration.id}"
}

resource "aws_apigatewayv2_integration" "lambda_integration" {
  api_id           = aws_apigatewayv2_api.chat_api.id
  integration_type = "AWS_PROXY"
  integration_method = "POST"
  integration_uri  = aws_lambda_function.chatbot.arn
  payload_format_version = "2.0"
}

resource "aws_ssm_parameter" "deepseek_key" {
  name        = "/costbot/deepseek_api_key"
  description = "DeepSeek API Key managed outside of Terraform"
  type        = "SecureString"
  value       = "CHANGE_ME_MANUALLY_IN_CONSOLE" # Dummy value

  # CRITICAL: This tells Terraform "Don't check if the value changed"
  lifecycle {
    ignore_changes = [value]
  }

  tags = {
    Environment = "Production"
    Project     = "CostBot"
  }
}

# D. Alarm: Anti-Spam (Protect DeepSeek Bill)
resource "aws_cloudwatch_metric_alarm" "high_usage_alarm" {
  alarm_name          = "costbot-high-traffic"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "Invocations"
  namespace           = "AWS/Lambda"
  period              = "300" # 5 minutes
  statistic           = "Sum"
  threshold           = "50"  # If > 50 chats in 5 mins, something is wrong
  alarm_description   = "Warning: High traffic detected. Check DeepSeek usage."
  alarm_actions       = [aws_sns_topic.cost_alerts.arn]
  
  dimensions = {
    FunctionName = aws_lambda_function.chatbot.function_name
  }
}


