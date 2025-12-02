data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/lambda.zip"
}

# resource "aws_lambda_function" "chatbot" {
#   function_name = "chatbot-lambda"
#   role          = aws_iam_role.lambda_role.arn
#   handler       = "handler.lambda_handler"  
#   runtime       = "python3.12"

#   filename         = data.archive_file.lambda_zip.output_path
#   source_code_hash = data.archive_file.lambda_zip.output_base64sha256

#   timeout = 120
#   memory_size = 512

#   environment {
#     variables = {
#       DEEPSEEK_API_KEY_PATH = "/costbot/deepseek_api_key"
#       SLACK_SECRET_PATH     = "/costbot/slack_signing_secret"
#     }
#   }
# }