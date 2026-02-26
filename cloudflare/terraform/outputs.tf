output "d1_database_id" {
  value       = cloudflare_d1_database.valencia_events.id
  description = "D1 database ID"
}

output "pages_project_name" {
  value       = cloudflare_pages_project.dashboard.name
  description = "Pages project name"
}

output "pages_project_subdomain" {
  value       = cloudflare_pages_project.dashboard.subdomain
  description = "Default *.pages.dev subdomain"
}

output "pages_custom_domain" {
  value       = var.pages_custom_domain != "" ? cloudflare_pages_domain.dashboard[0].name : null
  description = "Configured custom domain (if any)"
}

output "worker_custom_domain" {
  value       = var.worker_custom_domain != "" ? cloudflare_workers_custom_domain.api[0].hostname : null
  description = "Configured API worker custom domain (if any)"
}
