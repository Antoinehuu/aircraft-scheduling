import unittest

import highspy

from src import preprocess_flights
from src.highs import build_and_solve


class HiGHSFleetTests(unittest.TestCase):
    def solve(self, schedule, aircraft, costs=None):
        flights = [
            {"id": i, "origin": origin, "dest": dest, "departure": dep, "arrival": arr}
            for i, (origin, dest, dep, arr) in enumerate(schedule, 1)
        ]
        costs = costs if costs is not None else [[1] * len(aircraft) for _ in flights]
        airports = {airport for origin, dest, _, _ in schedule for airport in (origin, dest)}
        data = preprocess_flights(flights, airports, aircraft)
        model, x, y, z = build_and_solve(
            len(flights), 0, 0, flights, costs, [], aircraft, airports, {}, [], data,
            maintenance=False,
        )
        self.assertEqual((y, z), ({}, {}))
        model.setOptionValue("output_flag", False)
        model.run()
        return model, x

    def test_simultaneous_departures_require_two_aircraft(self):
        schedule = [("A", "B", 5, 10), ("A", "C", 5, 15)]
        model, _ = self.solve(schedule, {0: "A"})
        self.assertEqual(model.getModelStatus(), highspy.HighsModelStatus.kInfeasible)

        model, _ = self.solve(schedule, {0: "A", 1: "A"})
        self.assertEqual(model.getModelStatus(), highspy.HighsModelStatus.kOptimal)

    def test_same_time_connection_charges_both_flights(self):
        schedule = [("A", "B", 5, 10), ("B", "C", 10, 15)]
        model, _ = self.solve(schedule, {0: "A"}, [[2], [7]])
        self.assertEqual(model.getModelStatus(), highspy.HighsModelStatus.kOptimal)
        self.assertEqual(model.getObjectiveValue(), 9)

    def test_connection_requires_the_arrival_airport(self):
        schedule = [("A", "B", 5, 10), ("C", "A", 10, 15)]
        model, _ = self.solve(schedule, {0: "A"})
        self.assertEqual(model.getModelStatus(), highspy.HighsModelStatus.kInfeasible)

    def test_each_aircraft_operates_a_route(self):
        schedule = [("A", "B", 5, 10), ("B", "A", 10, 15), ("A", "C", 15, 20)]
        model, x = self.solve(schedule, {0: "A", 1: "A"}, [[1, 10], [1, 10], [1, 3]])
        self.assertEqual(model.getModelStatus(), highspy.HighsModelStatus.kOptimal)
        self.assertEqual(model.getObjectiveValue(), 5)
        self.assertEqual(model.val(x[3, 1]), 1)
