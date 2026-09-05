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

The defaults match the Git-connected production project: the repository root is
`/`, the build installs and runs the package in `cloudflare/`, and Pages serves
`cloudflare/pages/public`. Production and preview Pages Functions share
`pages_functions_compatibility_date`, whose default matches the current Worker
compatibility date.

Before applying changes, validate the configuration:

```bash
terraform fmt -check
terraform validate
terraform plan
```

To roll back an infrastructure change, revert the configuration commit, review
the resulting plan, and apply it. Worker code rollback remains a Wrangler
deployment concern and is intentionally outside this Terraform state.

## Notes

- This template intentionally does **not** upload Worker code with Terraform.
  - Keep Worker code deployment in Wrangler/CI (`wrangler deploy`) and let
    Terraform own account/zone resources.
- After D1 is created, apply schema from `../worker/src/schema.sql`.
