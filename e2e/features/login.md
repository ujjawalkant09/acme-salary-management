# Oracle: login

Sign-in and what each role may do. Run: `uv run python oracle_kit.py login`

| Id | Scenario | Changes data |
|---|---|---|
| S1 | the HR Admin signs in and sees their name and role | no |
| S2 | a wrong password shows an error and stays on sign-in | no |
| S3 | the HR Viewer sees salaries but no way to change them | no |

## Click paths
- **S1.** Open `/`. Enter `priya.sharma@acme.example` and the admin password, click **Sign in**. The side menu shows Home, People, Insights, Imports; the user menu at the bottom shows "Priya Sharma, HR Admin"; the header has **Add employee**.
- **S2.** Open `/`. Enter the admin email and the password `not-the-password`, click **Sign in**. Under the form: "That email and password don't match…". The side menu does not appear.
- **S3.** Sign in as `arjun.mehta@acme.example`. On People search `ACM-000010` and open Siddharth Reddy. The salary is shown; there is no **Change salary**, **Edit details**, **Mark as left** or **Add employee** button; the user menu says HR Viewer.
