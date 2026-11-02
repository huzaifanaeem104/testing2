# -*- coding: utf-8 -*-
"""
Fix OPB/2026/09/0002 partner lines imported from Excel minus-credits as DEBIT.

Excel Credit column negative = still CREDIT (we still have to pay them).
Importer posted abs(negative credit) as DEBIT. This script swaps those 91 lines
Debit -> Credit and adds 2x the total on 301006 Equity Equalization so the JE stays balanced.

No Excel file is needed on the server. The 91 rows are embedded below.and intead 

DEFAULT IS DRY-RUN. Nothing is written unless AGES_OPB_APPLY=1.

Copy this file to the server, for example /tmp/fix_opb_negative_credits.py

1) DRY-RUN on Testing_DB:

   export AGES_OPB_APPLY=0
   sudo -u odoo /opt/odoo-venv/bin/python /opt/odoo/odoo/odoo-bin shell \\
     -c /etc/odoo.conf -d Testing_DB --no-http <<'PY'
   exec(open("/tmp/fix_opb_negative_credits.py").read())
   PY

2) If dry-run shows 91 flips, 0 missing, then APPLY on Testing_DB only:

   export AGES_OPB_APPLY=1
   sudo -u odoo /opt/odoo-venv/bin/python /opt/odoo/odoo/odoo-bin shell \\
     -c /etc/odoo.conf -d Testing_DB --no-http <<'PY'
   exec(open("/tmp/fix_opb_negative_credits.py").read())
   PY

Adjust odoo-bin / venv / conf if your server paths differ. Keep -d Testing_DB.
APPLY on AGES_Production is blocked unless AGES_OPB_ALLOW_PROD=1.
"""

import os
import re
import csv
from collections import defaultdict

from odoo import fields
from odoo.exceptions import UserError

MOVE_NAME = os.environ.get("AGES_OPB_MOVE", "OPB/2026/09/0002")
APPLY = os.environ.get("AGES_OPB_APPLY") == "1"
REPORT_CSV = os.environ.get("AGES_OPB_CSV", "/tmp/opb_negative_credit_flip.csv")
EQUALIZATION_CODE = os.environ.get("AGES_OPB_EQ_CODE", "301006")
ALLOW_PROD = os.environ.get("AGES_OPB_ALLOW_PROD") == "1"
PROD_DB_NAMES = {"AGES_Production", "AGES", "ages_production"}

# (excel_head, partner_name, abs_amount, excel_credit)
FLIP_ROWS = [
    ('Equity / SHARE CAPITAL', 'Naeem Raza /Abdul Majid 50% 50%', 294285680.0, -294285680.0),
    ('LONG TERM LOANS FROM ASSOCIATED COMPANIES', 'ALHAMD LOGISTICES | CLIENT', 12310442.0, -12310442.0),
    ('LONG TERM LOANS FROM DIRECTORS', 'ABDUL MAJID', 750000.0, -750000.0),
    ('LONG TERM LOANS FROM DIRECTORS', 'NAEEM RAZA', 250000.0, -250000.0),
    ('CREDITOR FOR RAW MATERIAL |  SUPP', 'ABDUL REHMAN CRUSH SUPPLIER | SINDHRI', 11188325.0, -11188325.0),
    ('CREDITOR FOR RAW MATERIAL |  SUPP', 'ALI ASPHALATE | CHEMICAL SUPPLIER', 19912116.0, -19912116.0),
    ('CREDITOR FOR RAW MATERIAL |  SUPP', 'ALI REHMAN BRICKS SUPPLIER | SINDHRI', 70000.0, -70000.0),
    ('CREDITOR FOR RAW MATERIAL |  SUPP', 'ASHOKE KUMAR CRUSH SUPPLIER | SINDHRI', 3016550.0, -3016550.0),
    ('CREDITOR FOR RAW MATERIAL |  SUPP', 'ASLAM SUPPLIER | SAND | PIONEER', 1.0, -1.0),
    ('CREDITOR FOR RAW MATERIAL |  SUPP', 'CHAND SUPPLIER | BRICKS |SINDHRI', 115000.0, -115000.0),
    ('CREDITOR FOR RAW MATERIAL |  SUPP', 'KOHAT BRICKS SUPPLIER | SINDHRI', 165000.0, -165000.0),
    ('CREDITOR FOR RAW MATERIAL |  SUPP', 'M ALI SUPPLIER | CRUSH SAND | ULTIMATE (AL MOIZ 1 VEGETABLE ROAD WAREHOUSE ) CSMBANK', 2443376.0, -2443376.0),
    ('CREDITOR FOR RAW MATERIAL |  SUPP', 'MUKHTIAR SAND SUPPLIER | UNICOL |', 367611.0, -367611.0),
    ('CREDITOR FOR SERVICES | SUB', 'BAKRAAN KHAN EXCAVATION PC | SINDHRI', 1.0, -1.0),
    ('CREDITOR FOR SERVICES | SUB', 'SHABRAT KHAN EXCAVATION PC & SAND SUPPLIER | ISM', 509745.0, -509745.0),
    ('CREDITOR FOR SERVICES | SUB', 'ZAFAR PC | EXCAVATION | ALMOIZ-1', 27038.0, -27038.0),
    ('CREDITOR FOR SERVICES | SUB', 'ZAREEF KHAN | EXCAVATION PC | CHASHMA', 75608.0, -75608.0),
    ('CREDITOR FOR SERVICES | SUB', 'TARIQ PC | GHASSU', 567377.0, -567377.0),
    ('CREDITOR FOR SERVICES | SUB', 'FIAZ AHMED BRICK PC | SINDHRI', 66150.0, -66150.0),
    ('CREDITOR FOR SERVICES | SUB', 'GHULAM MUSTAFA PILLING PC | SINDHRI', 253240.0, -253240.0),
    ('CREDITOR FOR SERVICES | SUB', 'M AMIN CONCRETE PC | SINDHARI', 147857.0, -147857.0),
    ('CREDITOR FOR SERVICES | SUB', 'FIAZ AHMED STEEL PC | SINDHRI', 158600.0, -158600.0),
    ('CREDITOR FOR SERVICES | SUB', 'IRFAN STEEL PC | ITTEFAQ SM', 23566.0, -23566.0),
    ('CREDITOR FOR SERVICES | SUB', 'SHAH MUHAMMAD STEEL PC | SINDHRI', 96221.0, -96221.0),
    ('CREDITOR FOR SERVICES | SUB', 'ZUBAIR PC | STEEL | ALMOIZ 1', 150134.0, -150134.0),
    ('CREDITOR FOR SERVICES | SUB', 'GHULAM MURTAZA WATERPROOFING PC | SINDHRI', 13386.0, -13386.0),
    ('CREDITOR FOR SERVICES | SUB', 'IMRAN SHUTTERING PC | SINDHARI', 8628.0, -8628.0),
    ('CREDITOR FOR SERVICES | SUB', 'MAQSOOD AHMED SHUTTERING PC | SINDHRI', 53981.0, -53981.0),
    ('CREDITOR FOR SERVICES | SUB', 'NASEER AHMED SHUTTERING PC | SINDHRI', 5844.0, -5844.0),
    ('CREDITOR FOR SERVICES | SUB', 'NASIR PC | SHUTTRING | NOON | SINDHRI', 34259.0, -34259.0),
    ('CREDITOR FOR SERVICES | SUB', 'ZAFAR IQBAL DISMANTLING PC | CHASHMA', 88441.0, -88441.0),
    ('CREDITORS FOR SERVICES-RENTAL MACHINERY', 'AMJAD CRANE 250 | SINDHRI SM', 1018363.0, -1018363.0),
    ('CREDITORS FOR SERVICES-RENTAL MACHINERY', 'HAJI MUSTAFA LOADER | SINDHRI', 159505.0, -159505.0),
    ('CREDITORS FOR SERVICES-RENTAL MACHINERY', 'SAIF ULLAH TM 046 | SINDHRI', 1270002.0, -1270002.0),
    ('CREDITORS FOR SERVICES-RENTAL MACHINERY', 'SAIF UR REHMAN TM | SINDHRI', 951767.0, -951767.0),
    ('RETENTION MONEY PAYABLES', 'AKHTIYAR AHMED SHUTTERING PC | SINDHRI', 66527.0, -66527.0),
    ('RETENTION MONEY PAYABLES', 'AMEER HAMZA BRICK PC | SINDHRI', 13293.0, -13293.0),
    ('RETENTION MONEY PAYABLES', 'AMIR BUX SHUTTRING PC | ISM', 58793.0, -58793.0),
    ('RETENTION MONEY PAYABLES', 'FARMAN ALI BRICK WORK PC | SINDHRI', 25091.0, -25091.0),
    ('RETENTION MONEY PAYABLES', 'FIAZ AHMED BRICK PC | SINDHRI', 50286.0, -50286.0),
    ('RETENTION MONEY PAYABLES', 'GHULAM SHABIR PC | BRICK WORK | KHAN DAIRY | SINDHRI', 55932.0, -55932.0),
    ('RETENTION MONEY PAYABLES', 'GUL BAHAR PC | SHUTTERING | SINDHRI / NOON', 47006.0, -47006.0),
    ('RETENTION MONEY PAYABLES', 'HAYYAT BRICK PC | SINDHRI SM', 87203.0, -87203.0),
    ('RETENTION MONEY PAYABLES', 'HIDAYAT KHAN PC CHEMICAL | NOON | SINDHRI', 31517.0, -31517.0),
    ('RETENTION MONEY PAYABLES', 'IJAZ SHUTTERING PC | SINDHRI', 44151.0, -44151.0),
    ('RETENTION MONEY PAYABLES', 'IMRAN KHAN STEEL PC | SINDHRI', 271507.0, -271507.0),
    ('RETENTION MONEY PAYABLES', 'IMRAN SHUTTERING PC | SINDHARI', 70977.0, -70977.0),
    ('RETENTION MONEY PAYABLES', 'IRFAN STEEL PC | ITTEFAQ SM', 37985.0, -37985.0),
    ('RETENTION MONEY PAYABLES', 'JALAL KHAN ROAD PC | ALMOIZ 1', 100762.0, -100762.0),
    ('RETENTION MONEY PAYABLES', 'JAMSHAID POINTING PC | SINDHRI', 13202.0, -13202.0),
    ('RETENTION MONEY PAYABLES', 'JAVAID | DISMANTLING', 69827.0, -69827.0),
    ('RETENTION MONEY PAYABLES', 'KHIZAR HAYYAT BRICK PC | SINDHRI', 10669.0, -10669.0),
    ('RETENTION MONEY PAYABLES', 'KHUDAI NAZAR EXCAVATION PC | SINDHRI', 88155.0, -88155.0),
    ('RETENTION MONEY PAYABLES', 'LIAQAT ALI SHUTTERING PC | SINDHRI', 62313.0, -62313.0),
    ('RETENTION MONEY PAYABLES', 'M FAROOQ BRICK PC | SINDHARI', 63635.0, -63635.0),
    ('RETENTION MONEY PAYABLES', 'MANZOOR ALI SHUTTERING PC | SINDHRI', 70284.0, -70284.0),
    ('RETENTION MONEY PAYABLES', 'MAQBOOL AHMED BRICK PC | SINDHARI', 26371.0, -26371.0),
    ('RETENTION MONEY PAYABLES', 'MAQSOOD AHMED SHUTTERING PC | SINDHRI', 37436.0, -37436.0),
    ('RETENTION MONEY PAYABLES', 'MAZHAR | SHUTTERING PC | NOON | SINDHRI', 55543.0, -55543.0),
    ('RETENTION MONEY PAYABLES', 'MUHAMMAD AKRAM PC | FINISHING| ITEFFAQ', 2330.0, -2330.0),
    ('RETENTION MONEY PAYABLES', 'MUHAMMAD MUNEER PC | BRICKS | AMOIZ 1', 181607.0, -181607.0),
    ('RETENTION MONEY PAYABLES', 'MUHAMMAD SHERAZ BRICK PC | SINDHRI', 43448.0, -43448.0),
    ('RETENTION MONEY PAYABLES', 'MUMTAZ AHMED BRICK PC | SINDHRI', 28044.0, -28044.0),
    ('RETENTION MONEY PAYABLES', 'NADEEM BRICKS WORK', 14603.0, -14603.0),
    ('RETENTION MONEY PAYABLES', 'NADEEM PC | BRICK WORK | ULTIMATE', 157.0, -157.0),
    ('RETENTION MONEY PAYABLES', 'NASEER AHMED SHUTTERING PC | SINDHRI', 204166.0, -204166.0),
    ('RETENTION MONEY PAYABLES', 'NASIR PC | SHUTTRING | NOON | SINDHRI', 56694.0, -56694.0),
    ('RETENTION MONEY PAYABLES', 'NAWAZ PC | CONCRETE WORK | KHAN DAIRY', 134541.0, -134541.0),
    ('RETENTION MONEY PAYABLES', 'QADIR BUX SHUTTERING PC | SINDHRI', 27458.0, -27458.0),
    ('RETENTION MONEY PAYABLES', 'QAISAR PC | SHUTTRING | ULTIMATE | SINDHRI', 188003.0, -188003.0),
    ('RETENTION MONEY PAYABLES', 'QURBAN ALI FINISHING PC | SINDHRI', 7646.0, -7646.0),
    ('RETENTION MONEY PAYABLES', 'RAFIQ FINISHING WORK PC | SINDHRI', 24223.0, -24223.0),
    ('RETENTION MONEY PAYABLES', 'RAMZAN BRICK WORK PC | SINDHRI / NEXT', 84869.0, -84869.0),
    ('RETENTION MONEY PAYABLES', 'RIAZ ALI ABIDI STEEL PC | SINDHRI', 101228.0, -101228.0),
    ('RETENTION MONEY PAYABLES', 'SHABRAT KHAN EXCAVATION PC & SAND SUPPLIER | ISM', 24437.0, -24437.0),
    ('RETENTION MONEY PAYABLES', 'SHAH JAN STEEL PC | SINDHRI SM', 91918.0, -91918.0),
    ('RETENTION MONEY PAYABLES', 'SHAH MUHAMMAD STEEL PC | SINDHRI', 117754.0, -117754.0),
    ('RETENTION MONEY PAYABLES', 'SHAHID STEEL PC | SINDHRI SM', 8253.0, -8253.0),
    ('RETENTION MONEY PAYABLES', 'SHAMAS U DIN BRICK PC | SINDHRI', 15679.0, -15679.0),
    ('RETENTION MONEY PAYABLES', 'SIRAJ HUSSAIN SHUTTERING PC | SINDHARI', 13136.0, -13136.0),
    ('RETENTION MONEY PAYABLES', 'WAZEER AHMED FLOOR CONCRETE PC | SINDHRI', 25572.0, -25572.0),
    ('RETENTION MONEY PAYABLES', 'ZAFAR IQBAL DISMANTLING PC | CHASHMA', 53811.0, -53811.0),
    ('RETENTION MONEY PAYABLES', 'ZAHID HUSSAIN STEEL PC | SINDHRI', 23300.0, -23300.0),
    ('RETENTION MONEY PAYABLES', 'ZUBAIR PC | STEEL | ALMOIZ 1', 81275.0, -81275.0),
    ('MOBILIZATION ADVANCE', 'ALLIANCE SM | CLIENT |', 2385068.0, -2385068.0),
    ('MOBILIZATION ADVANCE', 'ALMOIZ 1 | CLIENT |', 126881.0, -126881.0),
    ('MOBILIZATION ADVANCE', 'Bandhi SUGAR MILLS | CLIENT |', 5874378.0, -5874378.0),
    ('MOBILIZATION ADVANCE', 'CHASHMA SUGAR MILLS | CLIENTS', 784735.0, -784735.0),
    ('MOBILIZATION ADVANCE', 'DEHARKI SUGAR MILLS | CLIENT |', 31638277.0, -31638277.0),
    ('MOBILIZATION ADVANCE', 'ITTEFAQ SUGAR MILLS | CLIENT |', 2582000.0, -2582000.0),
    ('MOBILIZATION ADVANCE', 'SINDHARI SUGAR MILLS | CLIENT |', 122499000.0, -122499000.0),
]

def _norm(name):
    name = (name or "").upper().replace("|", " ")
    name = re.sub(r"[^A-Z0-9]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def _flip_rows():
    rows = []
    for head, partner, amount, excel_credit in FLIP_ROWS:
        rows.append(
            {
                "head": head,
                "partner": partner,
                "key": _norm(partner),
                "excel_credit": excel_credit,
                "amount": amount,
            }
        )
    return rows


def _move_totals(move):
    debit = sum(move.line_ids.mapped("debit"))
    credit = sum(move.line_ids.mapped("credit"))
    return debit, credit, debit - credit


def _find_equalization(env, company):
    Account = env["account.account"].with_company(company)
    account = Account.search(
        [("code", "=", EQUALIZATION_CODE), ("company_ids", "in", company.ids)],
        limit=1,
    )
    if not account:
        account = Account.search(
            [("name", "ilike", "Equity Equalization"), ("company_ids", "in", company.ids)],
            limit=1,
        )
    return account


def run(env):
    dbname = env.cr.dbname
    print("Database:", dbname)
    if APPLY and dbname in PROD_DB_NAMES and not ALLOW_PROD:
        raise UserError(
            "Refusing APPLY on %s. Use Testing_DB, or set AGES_OPB_ALLOW_PROD=1." % dbname
        )

    excel_rows = _flip_rows()
    move = env["account.move"].search([("name", "=", MOVE_NAME)], limit=1)
    if not move:
        raise UserError("Journal entry %s was not found in this database." % MOVE_NAME)

    lines = move.line_ids.filtered(lambda line: line.partner_id)
    by_key = defaultdict(list)
    for line in lines:
        by_key[_norm(line.partner_id.name)].append(line)

    matches = []
    missing = []
    used = env["account.move.line"]
    for excel in excel_rows:
        candidates = list(by_key.get(excel["key"]) or [])
        if not candidates:
            for key, group in by_key.items():
                if excel["key"] and (excel["key"] in key or key in excel["key"]):
                    candidates = list(group)
                    break
        pick = env["account.move.line"]
        for line in candidates:
            if line in used:
                continue
            if abs(line.debit - excel["amount"]) < 0.51 and line.credit < 0.51:
                pick = line
                break
        if not pick:
            missing.append(excel)
            continue
        used |= pick
        matches.append((excel, pick))

    already_credit = []
    to_flip = []
    for excel, line in matches:
        if line.credit >= excel["amount"] - 0.51 and line.debit < 0.51:
            already_credit.append((excel, line))
        else:
            to_flip.append((excel, line))

    debit0, credit0, diff0 = _move_totals(move)
    flip_amount = sum(line.debit for _excel, line in to_flip)
    extra_debit = env.company.currency_id.round(2.0 * flip_amount)
    eq_account = _find_equalization(env, move.company_id)

    print("============================================================")
    print("Move:", move.name, "id=", move.id, "state=", move.state)
    print("Excel minus-credits:", len(excel_rows))
    print("Matched already Credit (skip):", len(already_credit))
    print("Matched Odoo DEBIT to flip:", len(to_flip))
    print("Excel minus-credits not found as Odoo debit:", len(missing))
    print("Current OPB totals  Dr {:,.2f}  Cr {:,.2f}  diff {:,.2f}".format(debit0, credit0, diff0))
    print("Flip amount (will move Debit -> Credit): {:,.2f}".format(flip_amount))
    print("Balancing extra Debit needed: {:,.2f}".format(extra_debit))
    print("Equalization account:", eq_account.display_name if eq_account else "NOT FOUND")
    print("APPLY:", APPLY)
    print("CSV:", REPORT_CSV)
    print("============================================================")

    with open(REPORT_CSV, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "status",
                "partner",
                "excel_credit",
                "odoo_line_id",
                "account",
                "current_debit",
                "current_credit",
                "new_debit",
                "new_credit",
            ]
        )
        for excel, line in to_flip:
            writer.writerow(
                [
                    "FLIP",
                    excel["partner"],
                    excel["excel_credit"],
                    line.id,
                    line.account_id.display_name,
                    line.debit,
                    line.credit,
                    0.0,
                    line.debit,
                ]
            )
        for excel in missing:
            writer.writerow(
                ["MISSING", excel["partner"], excel["excel_credit"], "", "", "", "", "", ""]
            )

    print("\nFirst 15 flips:")
    for excel, line in to_flip[:15]:
        print(
            "  {:>14,.2f}  {}  [{}]".format(
                line.debit, excel["partner"], line.account_id.code
            )
        )
    if missing:
        print("\nMissing from OPB debit (not flipped):")
        for excel in missing[:20]:
            print("  {:>14,.2f}  {}".format(excel["amount"], excel["partner"]))

    if not APPLY:
        print("\nDry-run only. Re-run with AGES_OPB_APPLY=1 on Testing_DB after review.")
        return

    if missing:
        raise UserError(
            "%s Excel minus-credit rows were not found as OPB debit. Not applying. See %s"
            % (len(missing), REPORT_CSV)
        )
    if not to_flip:
        print("Nothing to flip.")
        return
    if not eq_account:
        raise UserError("Account %s (Equity Equalization) not found." % EQUALIZATION_CODE)
    if abs(diff0) > 0.51:
        raise UserError("OPB is not balanced before the fix (diff %s)." % diff0)

    for _excel, line in to_flip:
        if line.matched_debit_ids or line.matched_credit_ids or line.full_reconcile_id:
            line.remove_move_reconcile()

    if move.state == "posted":
        move.button_draft()

    for _excel, line in to_flip:
        amount = line.debit
        line.with_context(check_move_validity=False).write(
            {
                "debit": 0.0,
                "credit": amount,
            }
        )

    debit1, credit1, diff1 = _move_totals(move)
    needed = env.company.currency_id.round(credit1 - debit1)
    if needed < 0:
        raise UserError("Unexpected extra debit after swap: %s" % needed)

    eq_line = move.line_ids.filtered(
        lambda line: line.account_id == eq_account and not line.partner_id
    )[:1]
    if eq_line:
        eq_line.with_context(check_move_validity=False).write(
            {
                "debit": eq_line.debit + needed,
                "credit": eq_line.credit,
                "name": (eq_line.name or "")
                + " | Reclass Excel minus-credit that was posted as debit",
            }
        )
    else:
        move.with_context(check_move_validity=False).write(
            {
                "line_ids": [
                    fields.Command.create(
                        {
                            "account_id": eq_account.id,
                            "name": "Reclass Excel minus-credit that was posted as debit",
                            "debit": needed,
                            "credit": 0.0,
                        }
                    )
                ]
            }
        )

    debit2, credit2, diff2 = _move_totals(move)
    print(
        "After fix, still draft: Dr {:,.2f}  Cr {:,.2f}  diff {:,.2f}".format(
            debit2, credit2, diff2
        )
    )
    if abs(diff2) > 0.51:
        raise UserError("OPB would not balance after fix (diff %s). Not posting." % diff2)

    move.action_post()
    env.cr.commit()
    print("Posted", move.name, "state=", move.state)
    ashoke = move.line_ids.filtered(
        lambda line: line.partner_id and "ASHOKE" in (line.partner_id.name or "").upper()
    )
    for line in ashoke:
        print(
            "ASHOKE now: Dr {:,.2f} Cr {:,.2f}  {}".format(
                line.debit, line.credit, line.account_id.display_name
            )
        )


run(env)
