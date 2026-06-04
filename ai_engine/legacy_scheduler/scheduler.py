from typing import List, Dict, Any, Optional

try:
    from .cp_sat_solver import CPSatSolver
except ImportError:
    from cp_sat_solver import CPSatSolver

class CSPSolver:
    """
    Wrapper class matching the original greedy/CSP solver interface,
    mapping the execution to the Google OR-Tools CP-SAT solver.
    """
    def __init__(
        self,
        subjects: List[Dict],
        faculty: List[Dict],
        timeslots: List[Dict],
        constraints: Optional[Dict] = None,
        locked_slots: Optional[List[Dict]] = None
    ):
        self.solver = CPSatSolver(
            subjects=subjects,
            faculty=faculty,
            timeslots=timeslots,
            constraints=constraints,
            locked_slots=locked_slots
        )

    def solve(self) -> List[Dict[str, Any]]:
        return self.solver.solve()
