# -------- 1. The Emergency Notification System (SNS) -------- #

resource "aws_sns_topic" "cost_alerts" {
  name = "aws-cost-alerts-topic"
}

# Subscribe your email to the topic
resource "aws_sns_topic_subscription" "email_alert" {
  topic_arn = aws_sns_topic.cost_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Allow AWS Budgets to publish to this topic
resource "aws_sns_topic_policy" "default" {
  arn = aws_sns_topic.cost_alerts.arn
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AWSBudgets-publishing"
        Effect = "Allow"
        Principal = {
          Service = "budgets.amazonaws.com"
        }
        Action   = "SNS:Publish"
        Resource = aws_sns_topic.cost_alerts.arn
      }
    ]
  })
}

# -------- 2. The Financial Firewall (AWS Budget) -------- #

resource "aws_budgets_budget" "monthly_budget" {
  name              = "monthly-10-dollar-budget"
  budget_type       = "COST"
  limit_amount      = "10"
  limit_unit        = "USD"
  time_period_start = "2025-01-01_00:00"
  time_unit         = "MONTHLY"

  # Alert 1: Warn me when I hit 80% ($8.00)
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = ["your-email@example.com"] # <--- CHANGE THIS
    subscriber_sns_topic_arns  = [aws_sns_topic.cost_alerts.arn]
  }

  # Alert 2: SCREAM if I'm forecasted to hit 100%
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = ["your-email@example.com"] # <--- CHANGE THIS
  }
}

# -------- 3. Operational Health (CloudWatch Alarms) -------- #

# A. Metric Filter: Count "Error" or "Exception" in Lambda logs
resource "aws_cloudwatch_log_metric_filter" "lambda_error_filter" {
  name           = "ChatbotErrorFilter"
  pattern        = "?ERROR ?Error ?Exception" # Look for these keywords
  log_group_name = "/aws/lambda/${aws_lambda_function.chatbot.function_name}"

  metric_transformation {
    name      = "ChatbotErrorCount"
    namespace = "CostBotMetrics"
    value     = "1"
  }
}

# B. Alarm: Trigger if we see errors
resource "aws_cloudwatch_metric_alarm" "lambda_error_alarm" {
  alarm_name          = "costbot-error-alarm"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "ChatbotErrorCount"
  namespace           = "CostBotMetrics"
  period              = "60" # Check every 60 seconds
  statistic           = "Sum"
  threshold           = "0" # If even 1 error occurs
  alarm_description   = "This metric monitors python errors in the chatbot"
  alarm_actions       = [aws_sns_topic.cost_alerts.arn]
}

# C. Alarm: Trigger if Lambda is too slow (> 10 seconds)
resource "aws_cloudwatch_metric_alarm" "lambda_latency_alarm" {
  alarm_name          = "costbot-latency-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = "60"
  statistic           = "Average"
  threshold           = "10000" # 10,000ms = 10s
  alarm_description   = "Alert if Chatbot takes longer than 10s"
  alarm_actions       = [aws_sns_topic.cost_alerts.arn]
  
  dimensions = {
    FunctionName = aws_lambda_function.chatbot.function_name
  }
}