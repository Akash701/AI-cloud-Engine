resource "aws_iam_user_policy_attachment" "dynamodb_fullaccess" {
  user       = "terraform-user"
  policy_arn = "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess"
}
# IAM Role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "lambda-chatbot-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

# Inline Policy
resource "aws_iam_role_policy" "lambda_inline_policy" {
  name = "lambda-inline-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "lambda:CreateFunction",
          "lambda:GetFunction",
          "lambda:UpdateFunctionCode",
          "lambda:UpdateFunctionConfiguration",
          "lambda:DeleteFunction",
          "iam:PassRole",          
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ce:GetCostAndUsage"
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:UpdateItem"
        ]
        Resource = "*" 
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:PutParameter"
        ]
        Resource = "*" 
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = "*" 
      }
    ]
  })
}

# resource "aws_iam_user_policy" "terraform_user_lambda_policy" {
#   name = "terraform-user-lambda-policy"
#   user = "lambda-chatbot-role" 

#   policy = jsonencode({
#     Version = "2012-10-17"
#     Statement = [
#       {
#         Effect = "Allow"
#         Action = [
          
#         ]
#         Resource = "*"
#       }
#     ]
#   })
# }


resource "aws_iam_user_policy_attachment" "terraform_user_lambda_managed" {
  user       = "terraform-user"  
  policy_arn = "arn:aws:iam::aws:policy/AWSLambda_FullAccess"
}

resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Attach AWS managed policy for SSM read/write
resource "aws_iam_user_policy_attachment" "ssm_managed" {
  user       = "terraform-user"
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMFullAccess"
}

resource "aws_iam_policy" "terraform_user_api_gateway" {
  name        = "TerraformAPIGatewayPolicy"
  description = "Minimal permissions for Terraform to manage API Gateway"
  policy      = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect   = "Allow",
        Action   = [
          "apigateway:GET",
          "apigateway:POST",
          "apigateway:PUT",
          "apigateway:DELETE",
          "apigateway:PATCH"
        ],
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_user_policy_attachment" "attach_api_gateway" {
  user       = "terraform-user"
  policy_arn = aws_iam_policy.terraform_user_api_gateway.arn
}

resource "aws_dynamodb_table" "chat_history" {
  name         = "chat-history"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "user_id"        
  range_key    = "timestamp"     

  attribute {
    name = "user_id"
    type = "S"
  }
  attribute {
    name = "timestamp"
    type = "S"
  }

  # Add Global Secondary Index for efficient querying
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

# resource "aws_lambda_function" "chatbot" {
#   function_name = "chatbot-lambda"
#   role          = aws_iam_role.lambda_role.arn
#   handler       = "index.handler"
#   runtime       = "python3.11"
# }
