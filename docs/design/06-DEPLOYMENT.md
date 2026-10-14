# 06 · Deployment and secrets

**One AWS EC2 server in Mumbai (ap-south-1), running the app with Docker Compose.** It is also the public demo link for reviewers. No load balancer, no container cluster, no managed database: the brief asks for good judgment, not the most complex system, and one server comfortably handles 10,000 employees (and 50,000).

## 1. Environments
| Environment | Where | Database | Purpose |
|---|---|---|---|
| Local | `docker compose up` on a laptop | Postgres container | Development |
| CI | GitHub Actions | SQLite (fast unit tests) + Postgres service container | Every push and pull request |
| Production / demo | One EC2 server, `docker compose` | Postgres container on the server's disk | The deployed app |

Local and production use **the same Docker image and almost the same Compose file**; only environment variables and the HTTPS proxy differ.

## 2. Why one server is enough
- **Data size:** 10,000 employees with a few salary entries each is about 50,000 rows; even 50,000 employees is roughly 250,000 rows, tens of megabytes. Postgres with our indexes answers list and Insights queries in milliseconds.
- **Load:** a small HR team; targets assume about 5 people working at once.
- **Background work** (imports, the daily rate fetch) runs in a separate worker container on the same machine.
- **Cost and simplicity:** one machine to understand, deploy, back up and explain.

**What we accept:** if the server goes down, the app is down until it restarts (Docker restarts containers automatically; the server can be restored from backups). For an HR tool used in office hours, that's a reasonable trade.

## 3. Region: Mumbai (ap-south-1)
| Option | Verdict |
|---|---|
| **Mumbai (ap-south-1)** | **Chosen**: closest AWS region to India, which has the most employees |
| Singapore (ap-southeast-1) | Close to India, Singapore and Australia |
| US East (N. Virginia) | Closest to the US, Canada and Brazil; far from India |

The app, database and file storage share the region: no cross-region delay or transfer cost. Users in the Americas get more network delay per request (server-side targets unchanged). Nothing in the code depends on the region.
**Data protection laws** are out of scope for this assessment; the app keeps personal data to a minimum.

## 4. The server
```mermaid
flowchart LR
    User[HR Admin / HR Viewer] -- "HTTPS :443" --> Caddy
    subgraph EC2["EC2 t3.small, Mumbai (Docker Compose)"]
      Caddy[Caddy: HTTPS, automatic certificate] --> App[Web app container: FastAPI + built React UI]
      App --> PG[(Postgres container, data on EBS disk)]
      Worker[Worker container: imports, daily rate fetch] --> PG
    end
    App -- "instance IAM role" --> S3[(S3: photos, documents, imports, nightly backups)]
    Worker -- "reads import files" --> S3
    Worker -- "daily, outbound HTTPS" --> FX[Frankfurter API: ECB rates]
    EC2 -- "Docker awslogs driver" --> CW[CloudWatch Logs]
    GHA[GitHub Actions] -- "OIDC: short-lived role" --> ECR[(ECR image registry)]
    GHA -- "SSM Run Command: pull and restart" --> EC2
```
- **Instance:** `t3.small` (2 vCPU, 2 GB RAM), 20 GB encrypted EBS disk, Ubuntu LTS with automatic security updates, an **Elastic IP** so the address never changes.
- **Containers (Docker Compose):**
  - **Caddy** serves HTTPS and gets a free Let's Encrypt certificate automatically. It needs a hostname: a domain if you have one, otherwise a free `<elastic-ip>.sslip.io` name that points to the server.
  - **Web app**: the one image we build (FastAPI serving the API and the built React UI).
  - **Worker**: the same image started with `python -m app.worker`; processes imports from the Postgres job table and runs the daily rate fetch. No message broker.
  - **Postgres 16** with its data on the server's disk; not reachable from the internet.
  - Every container has `restart: unless-stopped` and a health check.
- **Firewall (security group):** only ports 80 and 443 are open. **No SSH port**: admin access uses AWS Systems Manager (Session Manager), so there are no SSH keys to lose.
- **Files:** photos, documents and import uploads go to a private, encrypted **S3** bucket (public access blocked; downloads through short-lived signed links). The server reaches S3 through its **IAM instance role**, so there are no access keys.
- **Logs:** containers send structured logs to **CloudWatch Logs** through Docker's `awslogs` driver (Q38). No alerting or tracing.
- **Rough cost:** about $20–25 a month (`t3.small` ~$15, disk ~$2, Elastic IP ~$4, S3 and logs pennies). New AWS accounts get sign-up credits. These are estimates; check AWS pricing.

## 5. Backups and recovery
- **Nightly database dump** (`pg_dump`, compressed) uploaded to S3 by a small cron container; S3 keeps 14 days, then deletes old dumps automatically.
- **Weekly EBS snapshot** of the whole disk (Amazon Data Lifecycle Manager), 4 kept.
- **Restore:** start a fresh server from the setup script, restore the latest dump; target about 2 hours. Documented and tried once before the demo.

## 6. Setup and deploys (no Terraform)
- `deploy/` in the repo holds: `docker-compose.prod.yml`, `Caddyfile`, `bootstrap.sh` (installs Docker, the CloudWatch log driver settings and the backup cron; run once as EC2 user data) and a step-by-step `README.md` for the one-time AWS setup (instance, Elastic IP, security group, IAM roles, S3 bucket, ECR repository).
- **Deploy on merge to `main`:** GitHub Actions runs the tests, builds the image, pushes it to ECR (signed in through OIDC, no stored AWS keys), then uses **SSM Run Command** to tell the server to `docker compose pull && docker compose up -d`. Database migrations run when the app starts. A smoke test calls `/api/v1/health`; on failure the previous image tag is restored with the same command.

## 7. Secrets management
**Rule: no secret is ever in the repo, the Docker image or the logs.**

| Secret | Local | GitHub Actions | Server |
|---|---|---|---|
| `POSTGRES_PASSWORD` / `DATABASE_URL` | `.env` (git-ignored) | Not needed (CI uses a throwaway DB) | **SSM Parameter Store (SecureString)**, written to the server's `.env` (readable only by root) at deploy time |
| `SECRET_KEY` (signs session cookies) | `.env` | — | SSM Parameter Store |
| `DEMO_ADMIN_PASSWORD`, `DEMO_VIEWER_PASSWORD` (used once by the seed, stored as hashes in `users`) | `.env` | — | SSM Parameter Store |
| S3 and CloudWatch access | Local folder / console logs | — | **IAM instance role**: no keys |
| AWS deploy access | — | **OIDC** role, limited to pushing to one ECR repository and running one SSM command on one instance | — |

Also: `.env.example` with fake values is committed; the app refuses to start if a required secret is missing; `gitleaks` in CI blocks pushes containing keys; logs never include secrets, salaries or personal data.

## 8. How it would scale (documented, not built)
The app keeps no session state on the server, so growth is a series of small steps:
1. **Bigger server** (`t3.medium` / `t3.large`): covers far more than 50,000 employees.
2. **Database off the box** to RDS PostgreSQL: managed backups, failover.
3. **Two or more app servers behind a load balancer** (an Auto Scaling group), with the cache and rate limits moved to Redis (a config change) and the worker container moved to its own machine.
4. **Frontend on S3 + CloudFront** if users spread worldwide: CloudFront serves the UI from S3 and routes `/api/*` to the servers, so the app stays on one domain (no CORS or cross-site cookie problems).

**Considered and rejected for now:** frontend on S3 + CloudFront with the API on EC2. It would mean two origins (CORS, cross-site login cookies that browsers increasingly block) or extra CloudFront routing and cache invalidation on every deploy, for a tiny gain: the UI is about 1 MB, cached by the browser, and used by a small HR team.

## 9. Demo access
The app is public, so it's behind sign-in with **two demo logins** (HR Admin and HR Viewer). The credentials go to reviewers in the submission email and the README; passwords are never in the repo. Login attempts are rate-limited.
