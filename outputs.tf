output "output" {
  value       = terraform_data.this.output
  description = "This is an example of an output."
}

output "chat_api_invoke_url" {
  value       = "${aws_apigatewayv2_stage.chat_stage.invoke_url}/chat"
  description = "POST /chat endpoint for chatbot Lambda"
}


output "dynamodb_table_name" {
  value       = aws_dynamodb_table.chat_history.name 
  description = "Name of the DynamoDB table for chat history"
}

# Output the API Gateway URL
output "chat_api_invoke_url_full" {
  description = "API Gateway invocation URL"
  value       = "${aws_apigatewayv2_api.chat_api.api_endpoint}/${aws_apigatewayv2_stage.chat_stage.name}"
}