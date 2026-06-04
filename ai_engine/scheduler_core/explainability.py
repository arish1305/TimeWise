from typing import List, Dict, Any

def generate_selection_reason(best_score: float, subscores: Dict[str, float], health_metrics: Dict[str, float]) -> str:
    """
    Formulates a human-readable explanation of why the selected schedule is optimized.
    """
    reasons = []
    if subscores.get("spread", 0.0) >= 85.0:
        reasons.append("subjects are spread naturally across days to optimize student absorption")
    if subscores.get("faculty", 0.0) >= 85.0:
        reasons.append("faculty members have compact teaching windows and breathing space")
    if subscores.get("student", 0.0) >= 85.0:
        reasons.append("student load is balanced daily without difficult course clustering")
    if subscores.get("uniqueness", 0.0) >= 90.0:
        reasons.append("cross-section uniqueness has been maximized to avoid duplication")
        
    if not reasons:
        reasons.append("it achieves the highest global score across all comfort metrics")
        
    reason_str = "Selected candidate because: " + ", ".join(reasons) + f" (Global score: {best_score}/100)."
    return reason_str

def get_rejection_reason(score: float, subscores: Dict[str, float], index: int) -> str:
    """
    Formulates a human-readable explanation for why a specific candidate was rejected.
    """
    reasons = []
    
    # Identify the weakest subscore
    weakest_metric = min(subscores.keys(), key=lambda k: subscores[k])
    weakest_val = subscores[weakest_metric]
    
    if weakest_val < 70.0:
        if weakest_metric == "spread":
            reasons.append("poor subject spread and spacing gaps")
        elif weakest_metric == "faculty":
            reasons.append("faculty teaching block overload or isolated gaps")
        elif weakest_metric == "student":
            reasons.append("consecutive theory overload or heavy course clustering")
        elif weakest_metric == "period":
            reasons.append("repetitive timeslot patterns for subjects")
        elif weakest_metric == "uniqueness":
            reasons.append("cross-section duplicate patterns")
            
    if not reasons:
        reasons.append("lower overall quality score")
        
    return f"Candidate #{index} (Score: {score}) rejected due to: " + ", ".join(reasons) + "."
