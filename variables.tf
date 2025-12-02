variable "input" {
  description = "This is an example of an input."
  type        = string
  default     = "test"
}

variable "region" {
  
default = "us-east-1"

}

variable "email_endpoint" {
  description = "The email address to subscribe to the SNS topic."
  type        = string
  default     = "akashjnair701@gmail.com"
  
}

variable "deepseek_api_key" {
  description = "DeepSeek API Key for the cost advisor"
  type        = string
  sensitive   = true
}

variable "slack_signing_secret" {
description = "Slack Signing Secret for request verification"
  type        = string
  sensitive   = true
}

variable "alert_email" {
  description = "DeepSeek API Key for the cost advisor"
  type        = string
  sensitive   = true
}


