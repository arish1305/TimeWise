import logging
from typing import List, Dict, Any, Optional
from . import constraint_diagnostics

logger = logging.getLogger(__name__)

def explain_feasibility(
    subjects: List[Dict[str, Any]],
    faculty: List[Dict[str, Any]],
    timeslots: List[Dict[str, Any]],
    constraints: Dict[str, Any],
    locked_slots: List[Dict[str, Any]],
    is_feasible: bool,
    custom_reasons: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Creates a feasibility report explaining constraints that cause scheduling failure.
    """
    if is_feasible:
        return {
            "status": "FEASIBLE",
            "reasons": []
        }
        
    reasons = custom_reasons or []
    if not reasons:
        try:
            reasons = constraint_diagnostics.diagnose_infeasibility(
                subjects=subjects,
                faculty=faculty,
                timeslots=timeslots,
                constraints=constraints,
                locked_slots=locked_slots
            )
        except Exception as e:
            reasons = [f"Failed to diagnose core constraint conflicts: {str(e)}"]
            
    return {
        "status": "INFEASIBLE",
        "reasons": reasons
    }
