from odoo import models, fields


class PatientBasic(models.Model):

    _name = "patient.basic"
    _description = "Patient Basic"
    _order = "id desc"

    patient_id = fields.Char(
        string="Patient ID",
        required=True,
        copy=False,
        readonly=True,
        default="New"
    )

    name = fields.Char(
        string="Patient Name",
        required=True
    )

    age = fields.Integer(
        string="Age"
    )

    date_of_birth = fields.Date(
        string="Date of Birth"
    )

    phone = fields.Char(
        string="Phone"
    )

    blood_group = fields.Selection(
        [
            ("a_positive", "A+"),
            ("a_negative", "A-"),
            ("b_positive", "B+"),
            ("b_negative", "B-"),
            ("ab_positive", "AB+"),
            ("ab_negative", "AB-"),
            ("o_positive", "O+"),
            ("o_negative", "O-"),
        ],
        string="Blood Group"
    )

    gender = fields.Selection(
        [
            ("male", "Male"),
            ("female", "Female"),
            ("other", "Other"),
        ],
        string="Gender"
    )

    visit_fee = fields.Float(
        string="Visit Fee"
    )

    status = fields.Selection(
        [
            ("admitted", "Admitted"),
            ("discharged", "Discharged"),
        ],
        string="Status",
        default="admitted",
        required=True
    )

    notes = fields.Text(
        string="Notes"
    )