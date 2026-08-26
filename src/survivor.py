class SurvivorEngine:

    def __init__(self):
        self.next_id = 1

    def create_candidate(
        self,
        confidence,
        location,
        evidence
    ):

        survivor_id = f"S{self.next_id:02d}"

        survivor = {
            "survivor_id": survivor_id,
            "confidence": round(confidence, 3),
            "location": location,
            "evidence": evidence
        }

        self.next_id += 1

        return survivor