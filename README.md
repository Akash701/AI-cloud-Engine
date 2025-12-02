A serverless FinOps platform that audits AWS infrastructure costs, identifies waste (idle resources, unattached volumes), and **automatically generates Terraform code** to fix the issues using GenAI.

## **🏗️ Architecture**

This is not a simple wrapper. It is an event-driven, asynchronous serverless application designed to bypass Slack's 3-second timeout limits while ensuring bank-grade security.

graph TD  
    User((User)) \--\>|/costbot| Slack\[Slack Interface\]  
    Slack \--\>|Webhook (POST)| APIGW\[AWS API Gateway\]  
    APIGW \--\>|Trigger| Lambda\[AWS Lambda (Python)\]  
      
    subgraph "AWS Cloud (Terraform Managed)"  
        Lambda \--\>|1. Fetch Secrets| SSM\[SSM Parameter Store\]  
        Lambda \--\>|2. Get Cost Data| CE\[AWS Cost Explorer\]  
        Lambda \--\>|3. Read/Write Context| DDB\[(DynamoDB History)\]  
        Lambda \-.-\>|Async Self-Call| Lambda  
    end  
      
    subgraph "External AI"  
        Lambda \--\>|4. Analyze Data| DeepSeek\[DeepSeek LLM API\]  
    end  
      
    DeepSeek \--\>|5. Insight| Lambda  
    Lambda \--\>|6. Report| Slack

## **🚀 Key Features**

* **🧠 Context-Aware AI Analysis:** Uses **RAG (Retrieval Augmented Generation)** to combine real-time AWS Cost Explorer data with a static "Knowledge Base" of Terraform templates.  
* **⚡ Async Self-Invocation Pattern:** Implements a sophisticated threading logic to bypass Slack's 3-second webhook timeout by having the Lambda function trigger a background process.  
* **🔒 Zero-Trust Security:** No hardcoded secrets. All API keys are managed via **AWS Systems Manager (SSM) Parameter Store** and fetched at runtime.  
* **🛡️ Least Privilege IAM:** Custom IAM policies scoped strictly to required resources (no AdministratorAccess wildcarding).  
* **💾 Conversation State:** Uses **DynamoDB (On-Demand)** to maintain chat history, allowing the AI to understand follow-up questions (e.g., *"How do I fix **that**?"*).  
* **💰 Financial Guardrails:** Integrated AWS Budgets and CloudWatch Alarms to monitor the bot's own infrastructure costs.

## **🛠️ Tech Stack**

| Component | Technology | Purpose |
| :---- | :---- | :---- |
| **IaC** | Terraform | State management, drift detection, resource provisioning. |
| **Compute** | AWS Lambda | Serverless execution of the Python logic. |
| **API** | API Gateway (HTTP) | Webhook receiver for Slack slash commands. |
| **Database** | DynamoDB | Storing user conversation history for context. |
| **AI Model** | DeepSeek V3 | Cost analysis and HCL code generation. |
| **Security** | AWS SSM & IAM | Secret injection and permission scoping. |
| **Observability** | CloudWatch | Logs, error metrics, and latency alarms. |

## **💻 How to Run This Project**

### **Prerequisites**

* AWS Account & CLI configured.  
* Terraform installed.  
* A Slack Workspace (for the App).  
* DeepSeek API Key.

### **1\. Clone the Repo**

git clone \[https://github.com/Akash701/AI-cloud-Engine.git\](https://github.com/Akash701/AI-cloud-Engine.git)  
cd AI-cloud-Engine

### **2\. Set up Secrets (SSM)**

Do not put secrets in Terraform. Run these commands to store them securely in AWS:

aws ssm put-parameter \--name "/costbot/deepseek\_api\_key" \--type "SecureString" \--value "sk-..."  
aws ssm put-parameter \--name "/costbot/slack\_signing\_secret" \--type "SecureString" \--value "..."

### **3\. Deploy Infrastructure**

terraform init  
terraform apply \-auto-approve

### **4\. Connect to Slack**

* Copy the **Invoke URL** output by Terraform.  
* Paste it into your Slack App's "Slash Command" configuration.

## **🧠 Engineering Design Decisions**

### **Why Async Self-Invocation?**

Slack requires a response within 3000ms. DeepSeek LLM takes \~5000ms to analyze financial data.  
Solution: The Lambda accepts the request, spawns a non-blocking background thread (or invokes itself asynchronously), sends a "200 OK" to Slack immediately, and then posts the final report to the response\_url callback.

### **Why DynamoDB On-Demand?**

The chat traffic is spiky. Using **Provisioned Capacity** would waste money during idle hours. **On-Demand** ensures we pay exactly $0.00 when the bot is not in use.

### **Why SSM Parameter Store?**

Hardcoding secrets in variables.tf is a security risk (state file leakage). fetching them at runtime via boto3 ensures that even if the Git repo is compromised, the keys remain safe in AWS.

## **👤 Author**

**Akash J Nair** \- Cloud & DevOps Engineer

* [LinkedIn](http://linkedin.com/in/akash-jayaprakash-nair-118a82203)  
* [GitHub](https://github.com/Akash701)

*Open to Cloud Engineering opportunities.*