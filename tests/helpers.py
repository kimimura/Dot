import csv
import io

ACME_COLUMNS = ["Invoice No", "Date", "Customer", "Total", "Item", "Description", "Qty", "Price"]


def upload(client, pdf, name="acme.pdf"):
    return client.post("/api/convert?wait=1", data={"file": (io.BytesIO(pdf), name)})


def csv_rows(resp):
    return list(csv.reader(io.StringIO(resp.data.decode("utf-8-sig"))))


def columns(env):
    return [c["name"] for c in env["table"]["columns"]]
