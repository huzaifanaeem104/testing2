{
    "name": "Patient Basic",
    "version": "1.0",
    "category": "Healthcare",
    "summary": "Basic clinic patient management",
    "description": "Patient Basic Management",
    "author": "Huzaifa Naeem",
    "license": "LGPL-3",

    "depends": [
        "base",
    ],

    "data": [
        "security/ir.model.access.csv",
        "views/patient_views.xml",
    ],

    "installable": True,
    "application": True,
}