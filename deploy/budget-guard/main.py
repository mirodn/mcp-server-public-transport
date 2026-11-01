"""
Budget guard: makes the Cloud Run service private once the monthly budget is used up.

Triggered by Cloud Billing budget notifications via Pub/Sub. Removing the public
(allUsers) invoker binding stops all billable traffic; re-open it with
`gcloud run services add-iam-policy-binding ... --member=allUsers --role=roles/run.invoker`.
"""
import base64
import json
import os

import functions_framework
from google.cloud import run_v2

# Full resource name: projects/<project>/locations/<region>/services/<service>
SERVICE = os.environ["SERVICE_NAME"]


@functions_framework.cloud_event
def stop_on_budget(cloud_event):
    notification = json.loads(base64.b64decode(cloud_event.data["message"]["data"]))
    cost = notification["costAmount"]
    budget = notification["budgetAmount"]
    currency = notification.get("currencyCode", "")

    # Budget notifications arrive several times a day, also below the threshold
    if cost < budget:
        print(f"Cost {cost} {currency} below budget {budget} {currency}, nothing to do")
        return

    client = run_v2.ServicesClient()
    policy = client.get_iam_policy(request={"resource": SERVICE})

    changed = False
    for binding in policy.bindings:
        if binding.role == "roles/run.invoker" and "allUsers" in binding.members:
            binding.members.remove("allUsers")
            changed = True

    if changed:
        client.set_iam_policy(request={"resource": SERVICE, "policy": policy})
        print(f"Budget exceeded ({cost}/{budget} {currency}): {SERVICE} is now private")
    else:
        print(f"Budget exceeded ({cost}/{budget} {currency}): {SERVICE} already private")
