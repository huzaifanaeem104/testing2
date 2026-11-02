# -*- coding: utf-8 -*-
# from odoo import http


# class AgesCustomReports(http.Controller):
#     @http.route('/ages_custom_reports/ages_custom_reports', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/ages_custom_reports/ages_custom_reports/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('ages_custom_reports.listing', {
#             'root': '/ages_custom_reports/ages_custom_reports',
#             'objects': http.request.env['ages_custom_reports.ages_custom_reports'].search([]),
#         })

#     @http.route('/ages_custom_reports/ages_custom_reports/objects/<model("ages_custom_reports.ages_custom_reports"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('ages_custom_reports.object', {
#             'object': obj
#         })

