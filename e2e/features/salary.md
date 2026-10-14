# Oracle: salary

Changing a salary, a retried save, two people editing at once, and form checks. Run: `ORACLE_ALLOW_WRITES=1 uv run python oracle_kit.py salary`

S1–S3 change data, so they SKIP unless `ORACLE_ALLOW_WRITES=1`. Use a throwaway database (see the e2e README). Each scenario uses its own employee, so they never get in each other's way.

| Id | Scenario | Employee | Changes data |
|---|---|---|---|
| S1 | the HR Admin raises a salary and sees it on the page and in the history | ACM-000101 | yes |
| S2 | the answer to a save is lost, Save again records the change once | ACM-000102 | yes |
| S3 | two admins edit at once: the second save is refused, nothing overwritten | ACM-000103 | yes |
| S4 | a zero or non-numeric salary is refused before anything is sent | ACM-000104 | no |

## Click paths
Signed in as the HR Admin, search the employee on **People** and open them:
- **S1.** Count the Salary history rows. Click **Change salary**, add 1,000 to the amount, choose reason **Merit**, click **Save salary change**. "Salary change saved" shows, the dialog closes, the Yearly salary shows the new amount, and the history has one more row: today, Merit, Priya Sharma.
- **S2.** By hand: open the browser's dev tools, set the network to Offline *just after* clicking **Save salary change** (the oracle does this precisely: it lets the request reach the server, then drops the answer). "Can't reach the server" shows and the dialog stays open. Go back online, click **Save salary change** again: it succeeds, and the history has exactly **one** new row. Both requests carry the same `Idempotency-Key` header.
- **S3.** Open the same employee in two browser windows (or one normal and one private window, both signed in as admin). In window A change the salary (+1,000) and save. In window B, without reloading, change it (+5,000) and save: "This employee was changed by someone else. Reload to see the latest." Reload B: it shows A's amount, and the history has one new row, not two.
- **S4.** Click **Change salary**, choose a reason, enter `0`, click **Save salary change**: "The salary must be more than 0." Enter `12abc`, save: "Use numbers only…". The dialog stays open and the Network tab shows no POST.
