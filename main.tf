
resource "terraform_data" "this" {
  input = {
    example = var.input
  }
}

resource "aws_sns_topic" "alerts" {
  name = "chat-alerts"
}

resource "aws_sns_topic_subscription" "email_subscription" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.email_endpoint
  
}
resource "aws_dynamodb_table" "chat_history" {
  name         = "chat-history"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "message_id"
  range_key = "timestamp"

attribute {
    name = "timestamp"
    type = "S"
  }
  attribute {
    name = "message_id"
    type = "S"
  }

  global_secondary_index {
    name            = "UserTimestampIndex"
    hash_key        = "user_id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  tags = {
    Name        = "chat-history"
    Environment = "dev"
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



