output "output" {
  value       = terraform_data.this.output
  description = "This is an example of an output."
}

output "chat_api_invoke_url" {
  value       = "${aws_apigatewayv2_stage.chat_stage.invoke_url}/chat"
  description = "POST /chat endpoint for chatbot Lambda"
}
