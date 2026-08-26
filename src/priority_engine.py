class PriorityEngine:

    def rank(self, survivors):

        for survivor in survivors:

            confidence = survivor.get("confidence", 0)
            risk = survivor.get("risk", 0)
            distance = survivor.get("distance", 100)

            # Higher confidence and risk = higher priority
            # Shorter distance = slightly higher priority
            score = (
                confidence * 50
                + risk * 40
                + max(0, 10 - distance)
            )

            survivor["priority_score"] = round(score, 2)

        # Sort highest priority first
        survivors.sort(
            key=lambda x: x["priority_score"],
            reverse=True
        )

        # Assign priority numbers
        for index, survivor in enumerate(survivors):
            survivor["priority"] = index + 1

        return survivors