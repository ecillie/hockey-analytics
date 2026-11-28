variable "subscription_id" {
  description = "Azure subscription where TradeValue bootstrap resources will be created."
  type        = string
}

variable "state_storage_account_name" {
  description = "Globally unique name for the Terraform state storage account."
  type        = string
}

variable "budget_amount" {
  description = "Monthly Cost Management budget for the subscription, in the billing currency."
  type        = number
  default     = 1
}

variable "budget_contact_emails" {
  description = "Email addresses that receive budget alerts."
  type        = list(string)

  validation {
    condition     = length(var.budget_contact_emails) > 0
    error_message = "Provide at least one budget alert email address."
  }
}
