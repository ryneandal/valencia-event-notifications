variable "cloudflare_api_token" {
  description = "Cloudflare API token with Workers/Pages/D1 permissions"
  type        = string
  sensitive   = true
}

variable "account_id" {
  description = "Cloudflare account ID"
  type        = string
}

variable "zone_id" {
  description = "Cloudflare zone ID"
  type        = string
}

variable "pages_project_name" {
  description = "Pages project name"
  type        = string
  default     = "valencia-events-dashboard"
}

variable "pages_production_branch" {
  description = "Production branch for Pages"
  type        = string
  default     = "main"
}

variable "pages_build_command" {
  description = "Build command for Pages"
  type        = string
  default     = "pnpm --dir cloudflare install --frozen-lockfile && pnpm --dir cloudflare build"
}

variable "pages_destination_dir" {
  description = "Build output dir for Pages"
  type        = string
  default     = "cloudflare/pages/public"
}

variable "pages_root_dir" {
  description = "Root dir for Pages"
  type        = string
  default     = "/"
}

variable "pages_functions_compatibility_date" {
  description = "Compatibility date shared by production and preview Pages Functions"
  type        = string
  default     = "2026-09-04"
}

variable "pages_custom_domain" {
  description = "Optional custom domain for Pages dashboard, e.g. dashboard.example.com"
  type        = string
  default     = ""
}

variable "worker_service_name" {
  description = "Existing Worker service name for API (deployed via Wrangler or other CI)"
  type        = string
  default     = "valencia-events-api"
}

variable "worker_route_pattern" {
  description = "Optional Workers route pattern to map API worker, e.g. example.com/api/*"
  type        = string
  default     = ""
}

variable "worker_custom_domain" {
  description = "Optional worker custom domain, e.g. api.example.com"
  type        = string
  default     = ""
}

variable "session_ttl_hours" {
  description = "Session TTL exposed to Pages Functions environment"
  type        = number
  default     = 24
}
