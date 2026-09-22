"""CRM blueprint.

No routes yet. Reserved for the contacts/leads/clients milestone.
"""

from flask import Blueprint

crm_bp = Blueprint("crm", __name__, url_prefix="/crm")
