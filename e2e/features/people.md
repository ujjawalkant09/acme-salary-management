# Oracle: people

The People list: paging, search, the empty state, opening a person. Run: `uv run python oracle_kit.py people`

| Id | Scenario | Changes data |
|---|---|---|
| S1 | the list opens with a full first page and a head count | no |
| S2 | searching an employee code finds exactly that person | no |
| S3 | a search that matches no one says so, and Clear brings everyone back | no |
| S4 | clicking a row opens that person, and Back returns to the list | no |

## Click paths
Signed in as the HR Admin, on **People**:
- **S1.** The line above the table reads "N people"; the table has 20 rows (fewer if N < 20); the pager reads "Page 1 of …".
- **S2.** Type `ACM-000010` in the search box. The count reads "1 person", the row is ACM-000010, and the link has `?q=ACM-000010`.
- **S3.** Note the count, then type `zzqx-no-such-person`. "No one matches" shows, the count is "0 people". Click **Clear all filters**: the count is back to the first value and the search box is empty.
- **S4.** Click the first row. The person's page opens at `/people/<id>`, titled with the row's name. Click **Back to People**: the list is back at `/people`.
