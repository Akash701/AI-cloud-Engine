# 1. The Lambda Role (The Identity)
resource "aws_iam_role" "lambda_role" {
  name = "costbot-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

# 2. The Least-Privilege Policy (The Permissions)
resource "aws_iam_role_policy" "lambda_policy" {
  name = "costbot-logic-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # 1. Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # 2. Cost Explorer
      {
        Effect = "Allow"
        Action = ["ce:GetCostAndUsage"]
        Resource = "*"
      },
      # 3. DynamoDB (Chat History)
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:UpdateItem"
        ]
        Resource = aws_dynamodb_table.chat_history.arn
      },
      # 4. SSM (Secrets)
      {
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        Resource = "arn:aws:ssm:*:*:parameter/costbot/*"
      },
      # 5. NEW PERMISSION: Allow Lambda to Call Itself (Async)
      {
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        # Allow it to invoke ANY function in this account (easiest for now)
        # Or you can restrict it to just itself using the function ARN
        Resource = aws_lambda_function.chatbot.arn
      }
    ]
  })
}