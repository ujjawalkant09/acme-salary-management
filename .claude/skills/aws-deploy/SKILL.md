---
name: aws-deploy
description: Deploy ACME Salary Management to AWS (one EC2 server, Docker Compose) at acme.docrelay.in, and turn the demo server on or off to save money. Use when the user asks to deploy, release, start, stop, wake up, shut down or check the status of the AWS server, or to tear it down.
---

# aws-deploy

One command deploys everything; two more turn the demo server on and off.
All commands run from the repo root on the author's laptop.

| Ask | Command | Who runs it |
|---|---|---|
| Deploy / release the current commit | `.claude/skills/aws-deploy/scripts/deploy.sh` | Claude or the author |
| Preview infrastructure changes only | `.claude/skills/aws-deploy/scripts/deploy.sh --plan` | Claude or the author |
| Is it on? | `.claude/skills/aws-deploy/scripts/server.sh status` | Claude or the author |
| Turn it on for a demo | `.claude/skills/aws-deploy/scripts/server.sh start [hours]` | Claude or the author |
| Turn it off | `.claude/skills/aws-deploy/scripts/server.sh stop` | Claude or the author |
| Show the demo passwords | `.claude/skills/aws-deploy/scripts/logins.sh` | **Author only**, in their own terminal |
| Delete everything | `.claude/skills/aws-deploy/scripts/destroy.sh` | **Author only**, in their own terminal |

`logins.sh` and `destroy.sh` refuse to run when their output is captured, so Claude cannot run them.

## Credential rules (Claude must follow these)
- **Never read or print** `.env`, `backend/.env`, `~/.aws/credentials`, `~/.aws/config`, or any SSM parameter value. Don't `cat`, `grep`, `source` or `echo` them, and never run `aws ... --with-decryption` yourself.
- Never ask the author to paste keys, tokens or passwords into the chat. If a credential is wrong, say which one and how they can fix it themselves.
- Never add `set -x`, `--debug` or extra logging to these scripts: it would print secrets.
- Never change the scripts so a secret travels in a command-line argument, SSM command text, CloudFormation parameter, Docker image or log. Secrets only travel through pipes.
- If a command's output ever shows a secret, stop, tell the author which secret to rotate, and don't repeat it.

## How it works
- **`deploy.sh`**: checks tools and the AWS identity (refuses root keys); applies `infra/stack.yml` with CloudFormation; creates missing secrets in SSM Parameter Store with random values (never changes existing ones); builds the image for `linux/arm64` from the repo-root `Dockerfile` and pushes it to ECR tagged with the commit (needs a clean git tree); points `acme` in GoDaddy at the Elastic IP; copies `server/` to the server through S3 and runs `remote-update.sh` with SSM; waits for `https://$DOMAIN/api/v1/health`; schedules the auto-stop.
- **`server.sh start`**: starts the server, waits for the site and schedules it to back up and stop itself after `AUTO_STOP_HOURS` (or the hours given; 0 = never). Running it again on a running server just resets the timer.
- **`server.sh stop`**: backs up the database and files to S3, then stops. The Elastic IP stays, so DNS never changes.
- **On the server** (`server/`): `remote-update.sh` writes `/opt/acme/.env` (root-only) straight from SSM, pulls the image, runs `alembic upgrade head`, swaps containers and goes back to the previous image if the app is unhealthy. `backup.sh` runs nightly (03:00 IST), before every stop and before an auto-stop.

## What the app image provides
- The repo-root `Dockerfile` building for arm64, serving FastAPI and the built UI on port **8000**.
- `GET /api/v1/health`, `alembic.ini` in the working directory, `python -m app.worker`, `tar` and `python` in the image.
- The Postgres driver `psycopg` (the URL is `postgresql+psycopg://`), and uploads stored under `STORAGE_DIR` (`/data/storage`).
- `python -m scripts.seed --if-empty`: seeds the demo data and logins (from `DEMO_ADMIN_PASSWORD` / `DEMO_VIEWER_PASSWORD`) on a fresh database only.

## One-time setup (author)
1. AWS: create IAM user `acme-deployer` with `AdministratorAccess`, create an access key, run `aws configure --profile acme` (region `ap-south-1`).
2. GoDaddy: in the repo-root `.env`, `GODADDY_API=<personal access token>` or `KEY:SECRET` (production, from developer.godaddy.com).
3. `cp .claude/skills/aws-deploy/config.env.example .claude/skills/aws-deploy/config.env` and set `ALERT_EMAIL`.
4. After the first deploy, confirm the AWS Budgets subscription email.

## Cost (Mumbai, estimates)
- **Stopped:** about $6/month (Elastic IP ~$3.6, 20 GB disk ~$2).
- **Running:** about 2 cents per hour more.
- The $10 budget emails at $8 actual or $10 forecast. It is an alert, not a cap.

## Checking changes to this skill
Run from this folder:
```bash
uvx --from shellcheck-py shellcheck scripts/*.sh server/*.sh tests/stubs/*
uvx cfn-lint infra/stack.yml
npx --yes bats@1.11.1 tests
```
