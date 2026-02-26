resource "cloudflare_d1_database" "valencia_events" {
  account_id = var.account_id
  name       = "valencia-events"
}

resource "cloudflare_pages_project" "dashboard" {
  account_id        = var.account_id
  name              = var.pages_project_name
  production_branch = var.pages_production_branch

  build_config = {
    build_command   = var.pages_build_command
    destination_dir = var.pages_destination_dir
    root_dir        = var.pages_root_dir
  }

  # This sets runtime bindings/env for Pages Functions.
  # If you serve fully static content only, these bindings are harmless.
  deployment_configs = {
    production = {
      d1_databases = {
        DB = {
          id = cloudflare_d1_database.valencia_events.id
        }
      }
      env_vars = {
        SESSION_TTL_HOURS = {
          type  = "plain_text"
          value = tostring(var.session_ttl_hours)
        }
        API_BASE_URL = {
          type  = "plain_text"
          value = var.worker_custom_domain != "" ? "https://${var.worker_custom_domain}" : ""
        }
      }
      compatibility_date = "2026-02-25"
    }
    preview = {
      d1_databases = {
        DB = {
          id = cloudflare_d1_database.valencia_events.id
        }
      }
      env_vars = {
        SESSION_TTL_HOURS = {
          type  = "plain_text"
          value = tostring(var.session_ttl_hours)
        }
      }
      compatibility_date = "2026-02-25"
    }
  }
}

resource "cloudflare_pages_domain" "dashboard" {
  count = var.pages_custom_domain != "" ? 1 : 0

  account_id   = var.account_id
  project_name = cloudflare_pages_project.dashboard.name
  name         = var.pages_custom_domain
}

# Attach an existing Worker service to a route (if provided).
resource "cloudflare_workers_route" "api" {
  count = var.worker_route_pattern != "" ? 1 : 0

  zone_id = var.zone_id
  pattern = var.worker_route_pattern
  script  = var.worker_service_name
}

# Alternatively attach an existing Worker service to a custom domain.
resource "cloudflare_workers_custom_domain" "api" {
  count = var.worker_custom_domain != "" ? 1 : 0

  account_id  = var.account_id
  zone_id     = var.zone_id
  hostname    = var.worker_custom_domain
  service     = var.worker_service_name
  environment = "production"
}
