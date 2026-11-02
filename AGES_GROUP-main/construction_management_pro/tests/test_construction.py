from odoo.tests.common import TransactionCase


class TestConstructionManagement(TransactionCase):
    def setUp(self):
        super().setUp()
        self.project = self.env["project.project"].create({
            "name": "Test Construction Project",
            "is_construction": True,
        })
        self.product = self.env["product.product"].create({
            "name": "Concrete Test Material",
            "standard_price": 10.0,
        })

    def test_boq_amount(self):
        boq = self.env["construction.boq"].create({
            "project_id": self.project.id,
            "line_ids": [(0, 0, {
                "line_type": "material",
                "product_id": self.product.id,
                "description": self.product.name,
                "quantity": 5.0,
                "uom_id": self.product.uom_id.id,
                "unit_cost": 10.0,
            })],
        })
        self.assertEqual(boq.total_amount, 50.0)

    def test_task_progress(self):
        task = self.env["project.task"].create({
            "name": "Test Task",
            "project_id": self.project.id,
            "is_construction_task": True,
            "planned_qty": 100.0,
            "executed_qty": 25.0,
        })
        self.assertEqual(task.construction_progress, 25.0)
