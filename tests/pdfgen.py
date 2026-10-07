# Builds small text PDFs from scratch, so the tests never need real customer files


def _esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text(x, y, s, size=10):
    return f"BT /F1 {size} Tf {x} {y} Td ({_esc(s)}) Tj ET"


def build(pages):
    n = len(pages)
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>", 3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"}
    kids = []
    for i, ops in enumerate(pages):
        page_id, content_id = 4 + 2 * i, 5 + 2 * i
        content = "\n".join(ops).encode("latin-1")
        objs[page_id] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents {content_id} 0 R"
                         " /Resources << /Font << /F1 3 0 R >> >> >>").encode()
        objs[content_id] = b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"
        kids.append(f"{page_id} 0 R")
    objs[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {n} >>".encode()
    out, offsets = bytearray(b"%PDF-1.4\n"), {}
    for k in sorted(objs):
        offsets[k] = len(out)
        out += f"{k} 0 obj\n".encode() + objs[k] + b"\nendobj\n"
    xref, size = len(out), max(objs) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    for k in range(1, size):
        out += f"{offsets[k]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def invoice(title, issuer, fields, header, rows):
    ops, y = [text(50, 800, title, 18), text(50, 776, issuer, 12)], 746
    for k, v in fields:
        ops.append(text(50, y, f"{k}: {v}", 11))
        y -= 16
    y -= 20
    x0, colw, rh, ncol, nrow = 50, 100, 20, len(header), len(rows) + 1
    ops.append("0.5 w")
    ops += [f"{x0} {y - i * rh} m {x0 + colw * ncol} {y - i * rh} l S" for i in range(nrow + 1)]
    ops += [f"{x0 + j * colw} {y} m {x0 + j * colw} {y - nrow * rh} l S" for j in range(ncol + 1)]
    ops += [text(x0 + j * colw + 4, y - 14, h) for j, h in enumerate(header)]
    for i, r in enumerate(rows):
        ops += [text(x0 + j * colw + 4, y - 14 - (i + 1) * rh, c) for j, c in enumerate(r)]
    ops.append(text(50, 60, f"Thank you for your business - {issuer} - Terms Net 30", 9))
    return build([ops])


def acme(n=1):
    if n == 1:
        return invoice("TAX INVOICE", "Acme Trading Sdn Bhd",
                       [("Invoice No", "INV-2026-0091"), ("Date", "12/09/2026"), ("Customer", "Beta Retail"), ("Total", "1,250.00")],
                       ["Item", "Description", "Qty", "Price"],
                       [["A100", "Blue Widget", "10", "50.00"], ["A200", "Red Widget", "5", "150.00"]])
    return invoice("TAX INVOICE", "Acme Trading Sdn Bhd",
                   [("Invoice No", "INV-2026-0107"), ("Date", "20/09/2026"), ("Customer", "Gamma Mart"), ("Total", "300.00")],
                   ["Item", "Description", "Qty", "Price"],
                   [["A300", "Green Widget", "3", "100.00"]])


def orbit():
    return invoice("PURCHASE ORDER", "Orbit Logistics Bhd",
                   [("PO Number", "PO-77812"), ("Order Date", "01/09/2026"), ("Supplier", "Delta Parts"), ("Deliver To", "Warehouse 4")],
                   ["SKU", "Product", "Units", "Unit Cost", "Amount"],
                   [["S-1", "Bolt M8", "200", "0.50", "100.00"], ["S-2", "Nut M8", "200", "0.25", "50.00"]])


BECON_ITEMS = [
    ("1210302", ["UHU Glue Stic 8.2g", "ReNATURE/MINECRAFT/MONSTER/SO", "NIC"], "576", "PCS", "2.7500", "1,584.00", "90000060"),
    ("1210303", ["UHU Glue Stic 21g", "ReNATURE/MINECRAFT/MONSTER/SO", "NIC"], "120", "PCS", "5.3200", "638.40", "90000065"),
    ("1210356", ["UHU White Glue 122ml (97033515)"], "72", "UNIT", "3.4105", "245.56", "97-033-515"),
    ("1210620", ["Faber-Castell Tack-It 42pcs 30gsm", "(187079)"], "150", "PACK", "2.0700", "310.50", "187079"),
    ("1210621", ["Faber-Castell Tack-It 90pcs 50gsm", "(187054)"], "150", "PACK", "2.9200", "438.00", "187054"),
]


def becon():
    # each item spans several printed lines: code + description, wrapped description, the numbers, a second code
    ops, y = [text(50, 800, "BECON ENTERPRISE SDN BHD", 12), text(50, 780, "Purchase Order 231020"),
              text(50, 760, "No. Item Code Description Warehouse Quantity Unit Price Total")], 740
    for n, (code, desc, qty, uom, price, total, code2) in enumerate(BECON_ITEMS, 1):
        ops.append(text(50, y, f"{n} {code} {desc[0]}"))
        y -= 14
        for more in desc[1:]:
            ops.append(text(110, y, more))
            y -= 14
        ops.append(text(300, y, f"PP001-00 {qty} {uom} {price} {total} 0.00 {total}"))
        y -= 14
        ops.append(text(60, y, code2))
        y -= 22
    ops += [text(350, y - 10, "Subtotal MYR 3,216.46"), text(350, y - 26, "Total MYR 3,216.46")]
    return build([ops])


def po_item(n, code, desc_lines, qty, uom, price, code2, glue=False):
    total = f"{float(price) * int(qty):,.2f}"
    desc = desc_lines[0]
    for prev, line in zip(desc_lines, desc_lines[1:]):
        desc += line if glue and len(prev.split()) == 1 else " " + line
    return {"n": n, "code": code, "lines": desc_lines, "desc": desc, "qty": qty, "uom": uom, "price": price, "total": total, "code2": code2}


def becon_po(items, po="231020", per_page=4, header_extra="", stray_after=None, stray="Note: partial delivery accepted",
             date="15.09.26"):
    # a BECON-style purchase order: header block on every page, items over several lines, totals on the last page
    pages_n = max(1, -(-len(items) // per_page))
    head = ["Original", "BECON ENTERPRISE SDN BHD (82256-V)", "Tel: +603-55656151 Fax: +603-5569 4325", f"Purchase Order {po}",
            "Delivery Date: 14.09.26 Supplier GST No: NA", "Attn: TEE MENG WAI (SAM) Acc No: F024 Date: " + date,
            ("No. Item Code Description Warehouse Quantity Unit Price Total Excl. Tax " + header_extra).strip()]
    pages, lines = [], []
    for k, it in enumerate(items):
        if k % per_page == 0:
            if lines:
                pages.append(lines + [f"E. & O.E. Valerie Time: 15:57 Page: {len(pages) + 1}/ {pages_n}"])
            lines = list(head)
        lines.append(f"{it['n']} {it['code']} {it['lines'][0]}")
        lines += it["lines"][1:]
        lines.append(f"PP001-00 {it['qty']} {it['uom']} {it['price']} {it['total']}" + (" 0.00" if header_extra else ""))
        if it["code2"]:
            lines.append(it["code2"])
        if stray_after == k:
            lines.append(stray)
    subtotal = f"{sum(float(i['total'].replace(',', '')) for i in items):,.2f}"
    lines += [f"Payment Terms: 90 Day Subtotal MYR {subtotal}", "Rounding", f"Total MYR {subtotal}",
              f"E. & O.E. Valerie Time: 15:57 Page: {len(pages) + 1}/ {pages_n}"]
    pages.append(lines)
    return build([[text(40, 810 - 13 * i, line, 9) for i, line in enumerate(page)] for page in pages]), subtotal


PO_COLUMNS = [("PO No.", "doc"), ("Date", "doc"), ("Delivery Date", "doc"), ("Tel", "doc"), ("Fax", "doc"), ("Acc No.", "doc"),
              ("Item No.", "row"), ("Item Code 1", "row"), ("Item Code 2", "row"), ("Description", "row"), ("SKU", "row"),
              ("Quantity", "row"), ("UOM", "row"), ("Unit Price (MYR)", "row"), ("Total Excl. Tax (MYR)", "row"), ("Subtotal", "row")]


def becon_sheet(items, po, subtotal, date="15.09.26"):
    rows = [{"_doc": 0, "PO No.": po, "Date": date, "Delivery Date": "14.09.26", "Tel": "+603-55656151", "Fax": "+603-5569 4325",
             "Acc No.": "F024", "Item No.": str(it["n"]), "Item Code 1": it["code"], "Item Code 2": it["code2"] or "",
             "Description": it["desc"], "SKU": "PP001-00", "Quantity": it["qty"], "UOM": it["uom"], "Unit Price (MYR)": it["price"],
             "Total Excl. Tax (MYR)": it["total"], "Subtotal": f"MYR {subtotal}"} for it in items]
    return {"columns": [{"name": n, "kind": k} for n, k in PO_COLUMNS], "rows": rows}


TRAIN_ITEMS = [
    po_item(1, "1210302", ["UHU Glue Stic 8.2g", "ReNATURE/MINECRAFT/MONSTER/SO", "NIC"], "576", "PCS", "2.7500", "90000060", glue=True),
    po_item(2, "1210356", ["UHU White Glue 122ml (97033515)"], "72", "UNIT", "3.4105", "97-033-515"),
    po_item(3, "1260175", ["Faber-Castell Classic Colour Pencils In", "SlimFlexi Case 12L (115890)"], "84", "BOX", "9.0800", "115890"),
    po_item(4, "1480521-01", ["Faber-Castell White Board Marker W20 -", "Black (254099)"], "80", "PCS", "1.3900", "254099"),
    po_item(5, "1290081-2BB", ["Faber-Castell RX Gel Pen 0.5mm 2s/pkt -", "Blue & Black (249903)"], "50", "PKT", "2.3180", "249903"),
    po_item(6, "1480802-SET4", ["Faber-Castell Textliner 46 Metallic wallet of", "4pcs (154640)"], "10", "PKT", "12.7490", "154640"),
]

NEW_ITEMS = [
    po_item(1, "1160205", ["Faber-Castell Dust-Free Eraser (187130)"], "90", "PCS", "0.8693", "187130"),
    po_item(2, "1210307", ["UHU Gum Adhesive No:40981 60ml"], "48", "TUBE", "8.3220", "91040981"),
    po_item(3, "1250935", ["Faber-Castell Mechanical Pencil Apollo", "0.5mm (232593)"], "50", "PKT", "6.4500", "232593"),
    po_item(4, "1290084-4M", ["Faber-Castell Ball Pen Click X7 0.7mm", "4s/pkt - 2 Blue/1 Black/1 Red (142254)"], "40", "PKT", "2.4320", "142254"),
    po_item(5, "1480802-04", ["Faber-Castell Textliner 46 (1546) Super", "Fluorescent Green"], "10", "PCS", "2.6078", "154663"),
    po_item(6, "1210303", ["UHU Glue Stic 21g", "ReNATURE/MINECRAFT/MONSTER/SO", "NIC"], "120", "PCS", "5.3200", "90000065", glue=True),
    po_item(7, "1481301-01", ["Faber-Castell OHP Marker (S) Permanent", "1523 - Black"], "10", "PCS", "3.1873", "152399"),
]


def econ_item(code, bar, desc, unit, pack, qty, price, tail=None, desc_on_bar=False, tail_next_page=False):
    return {"code": code, "bar": bar, "desc": desc, "unit": unit, "pack": pack, "qty": qty, "price": price,
            "amount": f"{float(qty) * float(price):,.2f}", "tail": tail, "on_bar": desc_on_bar, "tail_next_page": tail_next_page}


def econ_po(po, ship, items, addr=None):
    return {"po": po, "ship": ship, "items": items, "addr": addr}


VENDOR_LEFT = ["FABER-CASTELL TRADINGSDN BHD", "NO. 9 JLN TP2", "TMN PERINDUSTRIAN SIMEUEP"]


def econsave(pos, per_page=3):
    # an ECONSAVE-style file: several purchase orders, each value on its own line, spilled numbers after an item
    pages, docs = [], []
    for k, o in enumerate(pos):
        chunks = [o["items"][i:i + per_page] for i in range(0, len(o["items"]), per_page)]
        ref = o["po"].split("-")[1]
        total = sum(float(i["amount"].replace(",", "")) for i in o["items"])
        qty = sum(float(i["qty"]) for i in o["items"])
        for n, chunk in enumerate(chunks, 1):
            lines = ["Purchase Order", "PDTReference No. :", ref, f"Purchase OrderNo. : {o['po']}", "Purchase OrderDate : 28/09/2026",
                     f"Printed on : 30/09/2026 09:17:{30 + k + n}", f"Page : {n} of {len(chunks)} ExpectedReceive Date &Time: 28/10/2026 18:00:00",
                     "Vendor Ship-To Location", f"10586 FABE18 {o['ship']}"]
            if o.get("addr"):
                lines += [f"{left} {right}" for left, right in zip(VENDOR_LEFT, o["addr"])] + ["47620 SUBANGJAYA, SELANGOR"]
            else:
                lines.append("FABER-CASTELL TRADINGSDN BHD ECONSAVECASH&CARRY SDN BHD")
            lines += ["Item Description SKU/Order Unit Order Pack Total Unit Price Amount", "Barcode Capacity Free Unit Qty. (RM) (RM)"]
            lines += [it["tail"] for it in chunks[n - 2][-1:] if n > 1 and it["tail"] and it["tail_next_page"]]
            for it in chunk:
                lines.append(it["code"])
                if it["on_bar"]:
                    lines.append(f"{it['bar']} {it['desc']}")
                else:
                    lines += [it["bar"], it["desc"]]
                lines += ["10.00", it["unit"], it["pack"], "0.00", f"{float(it['qty']):.2f} {it['price']} {it['amount']}"]
                if it["tail"] and not (it["tail_next_page"] and it is chunk[-1] and n < len(chunks)):
                    lines.append(it["tail"])
            if n == len(chunks):
                lines += [f"Grand Total {qty:,.2f} {total:,.2f}", "* This iscomputer generated, no signatureis required.*"]
            pages.append(lines)
        docs.append({"PO No.": o["po"], "Purchase Order Date": "28/09/2026", "Printed on": f"30/09/2026 09:17:{31 + k}",
                     "Expected Receive Date & Time": "28/10/2026 18:00:00", "Vendor": "10586 FABE18", "Ship-To Location": o["ship"],
                     "Grand Total": f"{total:,.2f}", **({"Address": " ".join([o["ship"]] + o["addr"])} if o.get("addr") else {})})
    rows = [{"_doc": k, **docs[k], "Item Barcode": f"{it['code']} {it['bar']}", "Description": it["desc"] + (f" {it['tail']}" if it["tail"] else ""),
             "SKU/Order Unit Capacity": f"10.00 {it['unit']}", "Order Pack Free Unit": f"{it['pack']} 0.00",
             "Total Qty.": f"{float(it['qty']):.2f}", "Unit Price (RM)": it["price"], "Amount (RM)": it["amount"]}
            for k, o in enumerate(pos) for it in o["items"]]
    cols = [(c, "doc") for c in docs[0] if c != "_doc"] + [(c, "row") for c in ["Item Barcode", "Description", "SKU/Order Unit Capacity",
                                                                             "Order Pack Free Unit", "Total Qty.", "Unit Price (RM)", "Amount (RM)"]]
    pdf = build([[text(40, 810 - 13 * i, line, 9) for i, line in enumerate(page)] for page in pages])
    return pdf, {"columns": [{"name": n, "kind": k} for n, k in cols], "rows": rows}


ECON_A = [econ_item("543000158", "9556089435109", "FC CLICK BPEN-R0.5MMBLK 4S 142595", "1UNITx1", "2.00", "20", "3.0600"),
          econ_item("543710011", "9556089885331", "DUST FREE ERASER- 7086-30 PB3S 187087", "1 UNIT", "1.00", "10", "1.5000", desc_on_bar=True),
          econ_item("543000130", "9555684642479", "FC GRIP X5 BPEN-R0.5MM2BL/1BK 3S", "1UNITx1", "1.00", "10", "2.8600", tail="547309"),
          econ_item("543010056", "9555684646903", "FC RXGEL PEN 0.5 BLUE/BLACK 2S 249903", "1UNITx1", "1.00", "10", "2.8600")]
ECON_B = [econ_item("543000134", "9555684635082", "FC GRIP X7 B/PEN 0.7MM2BL/1BK 3S", "1 UNIT", "1.00", "10", "3.5900", tail="547407"),
          econ_item("543000135", "9555684635112", "FC GRIP X7 BPEN-R 0.7MM MIX 3S 547408", "1UNITx1", "2.00", "20", "3.5900"),
          econ_item("543710026", "9555684697691", "FC DF ERASER SIZE 48 BLK B10F2 187049", "1 UNIT", "1.00", "10", "3.6600")]


SMO_COLUMNS = [("PO No.", "doc"), ("Store Code", "doc"), ("No", "row"), ("Item Code", "row"), ("Barcode", "row"), ("SKU Description", "row"),
               ("Unit Price", "row"), ("UOM", "row"), ("Qty Ctn", "row"), ("Qty Pcs", "row"), ("Gross Amount", "row"), ("Nett Amount", "row")]
CTN_X, PCS_X = 410, 428


def smo_po(orders):
    # each item over four lines: its number alone, then its FC- code, its barcode, and the description with the amounts;
    # cartons and pieces print the quantity in the same way, only under a different column;
    # a store name given as several lines is printed wrapped, and an order may name the address line under it
    pages, rows = [], []
    for d, (po, printed, items, *address) in enumerate(orders):
        printed = [printed] if isinstance(printed, str) else list(printed)
        store = " ".join(printed)
        ops = [text(40, 800, "Purchase Order", 14), text(40, 780, f"PO No. {po}"), text(40, 760, "Deliver To"),
               text(40, 748, f"{store[:3].upper()} - SYARIKAT MUDA OSMAN SDN BHD"), text(40, 736, "(BRN-198701005114)")]
        ops += [text(40, 724 - 12 * k, line) for k, line in enumerate(printed)]
        ops += [text(40, 724 - 12 * len(printed), (address or ["Unit No L3 - 01 & 02,"])[0]),
               text(40, 690, "No Art/MCode SKU Description Cost Price UOM Qty FOC Gross Nett"),
               text(CTN_X, 678, "Ctn"), text(PCS_X, 678, "Pcs"), text(470, 678, "Amount"), text(520, 678, "Amount")]
        y = 660
        for n, (code, bar, desc, price, uom, qty, unit) in enumerate(items, 1):
            amount = f"{float(price) * int(qty):.2f}"
            ops += [text(40, y, str(n)), text(60, y - 12, f"FC-{code}"), text(60, y - 24, bar), text(60, y - 36, f"{code} {desc}"),
                    text(320, y - 36, price), text(370, y - 36, uom), text(CTN_X if unit == "ctn" else PCS_X, y - 36, qty),
                    text(470, y - 36, amount), text(520, y - 36, amount)]
            rows.append({"_doc": d, "PO No.": po, "Store Code": store, "No": str(n), "Item Code": code, "Barcode": bar,
                         "SKU Description": f"{code} {desc}", "Unit Price": price, "UOM": uom,
                         "Qty Ctn": qty if unit == "ctn" else "", "Qty Pcs": qty if unit == "pcs" else "",
                         "Gross Amount": amount, "Nett Amount": amount})
            y -= 50
        pages.append(ops)
    return build(pages), {"columns": [{"name": n, "kind": k} for n, k in SMO_COLUMNS], "rows": rows}


SMO_TRAIN = [("HQ292380", "SMO Bookstores East Coast Mall (ECM)",
              [("381811", "282479170000", "FC DESKTOP SHARPENER PLUS", "17.6000", "PCS", "1", "pcs"),
               ("178318", "281485130000", "FABER-CASTELL 18CM STRAIGHT RULER", "29.2800", "B0020", "1", "ctn"),
               ("584800", "281293170000", "3P FC SINGLE HOLE SHARPENER", "29.3000", "B0010", "2", "ctn"),
               ("100028295", "282066040000", "FC DESKTOP SHARPENER ANGLE", "23.7600", "PCS", "3", "pcs")]),
             ("HQ292381", "SMO Bookstores Mahkota Square",
              [("178315", "281037820000", "FABER-CASTELL 15CM STRAIGHT RULER", "39.6500", "B0050", "1", "ctn"),
               ("584603", "282348960000", "CLICK BOX SHARPENER", "28.9200", "PCS", "2", "pcs"),
               ("401151", "282499550000", "FC STAPLER NO. 10 BLUE BOX OF 1", "21.6020", "B0006", "1", "ctn")]),
             ("HQ292382", "SMO Bookstores Pekan",
              [("584900", "281293180000", "3P FC SHARPENER OVAL CLASSIC", "29.3000", "B0010", "4", "ctn"),
               ("381811", "282479170000", "FC DESKTOP SHARPENER PLUS", "17.6000", "PCS", "5", "pcs")])]
SMO_WRAPPED = [("HQ292383", ("SMO Bookstores Tanah Merah Kompleks", "Humaira"),
                [("311802", "281921940000", "2B 12X FC TRI-GRIP PENCIL", "34.0200", "B0006", "2", "ctn")])]
SMO_NEW = [("HQ292390", "SMO Bookstores Raub",
            [("178330", "281485140000", "FABER-CASTELL 30CM STRAIGHT RULER", "41.4800", "B0020", "3", "pcs"),
             ("584803", "281900140000", "3P FC SINGLE HOLE SHARPENER PASTEL", "29.3000", "B0010", "6", "ctn"),
             ("100028295", "282066040000", "FC DESKTOP SHARPENER ANGLE", "23.7600", "PCS", "7", "ctn")])]


def purchase_orders(orders=6, pages_per_order=4, items_per_page=12):
    # a long, packed PDF like the ECONSAVE file: several orders, each running over several pages
    pages, truth, code = [], [], 8880000000000
    for o in range(orders):
        po = f"PO{50100 + o}"
        for k in range(1, pages_per_order + 1):
            ops = [text(50, 800, "PURCHASE ORDER", 16), text(50, 780, f"Purchase Order No.: {po}"),
                   text(400, 780, f"Page: {k} of {pages_per_order}")]
            y = 740
            for i in range(items_per_page):
                code += 7
                ops.append(text(50, y, f"{code} Item {o}-{k}-{i} pencil box {i + 3} PCS {(i + 1) * 1.25:.2f} {(i + 3) * 4.75:.2f}"))
                truth.append((po, str(code)))
                y -= 18
            pages.append(ops)
    return build(pages), truth
