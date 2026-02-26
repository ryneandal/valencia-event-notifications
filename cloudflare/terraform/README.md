# Terraform template (Cloudflare)

This template provisions Cloudflare infra for the dashboard/app:

- D1 database for user/session data
- Pages project for frontend
- Optional Pages custom domain
- Optional Worker route/custom-domain attachment for an existing Worker service

## Prerequisites

- Terraform >= 1.6
- Cloudflare API token with permissions for Pages, Workers, D1, Zones
- Existing Worker service deployed (recommended via Wrangler in CI)

## Usage

```bash
cd cloudflare/terraform
cp terraform.tfvars.example terraform.tfvars
# edit values
terraform init
terraform plan
terraform apply
```

## Notes

- This template intentionally does **not** upload Worker code with Terraform.
  - Keep Worker code deployment in Wrangler/CI (`wrangler deploy`) and let Terraform own account/zone resources.
- After D1 is created, apply schema from `../worker/src/schema.sql`.
