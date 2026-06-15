# This file is part of wger Workout Manager.
#
# wger Workout Manager is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# wger Workout Manager is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License

# Standard Library
from dataclasses import asdict
from decimal import Decimal

# Django
from django.core.cache import cache
from django.test import SimpleTestCase

# wger
from wger.core.tests.base_testcase import WgerTestCase
from wger.manager.dataclasses import SetConfigData
from wger.manager.models import (
    MaxRepetitionsConfig,
    MaxWeightConfig,
    RepetitionsConfig,
    RestConfig,
    RiRConfig,
    SetsConfig,
    SlotEntry,
    WeightConfig,
    WorkoutLog,
)
from wger.manager.models.abstract_config import (
    MAX_COMPOUND_RIR,
    MAX_COMPOUND_VALUE,
    OperationChoices,
    StepChoices,
)
from wger.utils.cache import CacheKeyMapper


class SlotEntryTestCase(WgerTestCase):
    """
    Test the slot entry calculations
    """

    slot_entry: SlotEntry

    def setUp(self):
        super().setUp()

        self.slot_entry = SlotEntry(
            slot_id=1,
            exercise_id=1,
            order=1,
        )
        self.slot_entry.save()

    def test_auto_add_order(self):
        """
        Test that the order is automatically added if not provided
        """
        SlotEntry.objects.filter(slot_id=1).delete()

        slot_entry_1 = SlotEntry(slot_id=1, exercise_id=1)
        slot_entry_1.save()

        slot_entry_2 = SlotEntry(slot_id=1, exercise_id=2, order=None)
        slot_entry_2.save()

        slot_entry_3 = SlotEntry(slot_id=1, exercise_id=3, order=7)
        slot_entry_3.save()

        slot_entry_4 = SlotEntry(slot_id=1, exercise_id=3)
        slot_entry_4.save()

        self.assertEqual(slot_entry_1.order, 1)
        self.assertEqual(slot_entry_2.order, 2)
        self.assertEqual(slot_entry_3.order, 7)
        self.assertEqual(slot_entry_4.order, 8)

    def test_weight_config(self):
        """
        Test that the weight is correctly calculated for each step / iteration
        """

        # Initial value
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=1,
            value=80,
            operation=OperationChoices.REPLACE,
        ).save()

        # Increase by 2.5
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=3,
            value=2.5,
            operation=OperationChoices.PLUS,
        ).save()

        # Replace with 42
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=6,
            value=42,
            operation=OperationChoices.REPLACE,
        ).save()

        # Reduce by 2
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=7,
            value=2,
            operation=OperationChoices.MINUS,
        ).save()

        # Increase by 10%
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=8,
            value=10,
            operation=OperationChoices.PLUS,
            step=StepChoices.PERCENT,
        ).save()

        self.assertEqual(self.slot_entry.calculate_weight(1), 80)
        self.assertEqual(self.slot_entry.calculate_weight(2), 80)
        self.assertEqual(self.slot_entry.calculate_weight(3), 82.5)
        self.assertEqual(self.slot_entry.calculate_weight(4), 82.5)
        self.assertEqual(self.slot_entry.calculate_weight(5), 82.5)
        self.assertEqual(self.slot_entry.calculate_weight(6), 42)
        self.assertEqual(self.slot_entry.calculate_weight(7), 40)
        self.assertEqual(self.slot_entry.calculate_weight(8), 44)

    def test_weight_config_with_logs(self):
        """
        Test that the weight is correctly calculated for each step / iteration
        if there are logs
        """

        self.slot_entry.weight_rounding = 2.5
        self.slot_entry.repetition_rounding = 2
        self.slot_entry.save()

        # Initial value
        SetsConfig(slot_entry=self.slot_entry, iteration=1, value=4).save()
        RepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=5).save()
        RestConfig(slot_entry=self.slot_entry, iteration=1, value=120).save()
        RiRConfig(slot_entry=self.slot_entry, iteration=1, value=2).save()
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=1,
            value=80,
        ).save()

        # Increase weight by 2.5 at iteration 2
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=2,
            value=2.5,
            operation=OperationChoices.PLUS,
            step=StepChoices.ABSOLUTE,
            requirements={'rules': ['weight', 'repetitions']},
        ).save()

        # Replace weight with 42 at iteration 5, no logs needed
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=5,
            value=42,
            operation=OperationChoices.REPLACE,
            step=StepChoices.ABSOLUTE,
        ).save()

        # Only did 4x82.5 at iteration 2
        WorkoutLog(
            exercise_id=1,
            user_id=1,
            routine_id=1,
            slot_entry=self.slot_entry,
            iteration=2,
            weight=82.5,
            repetitions=4,
        ).save()

        # Did 5x82.5 at iteration 3
        WorkoutLog(
            exercise_id=1,
            user_id=1,
            routine_id=1,
            slot_entry=self.slot_entry,
            iteration=3,
            weight=82.5,
            repetitions=5,
        ).save()

        self.assertDictEqual(
            asdict(self.slot_entry.get_config_data(1)),
            asdict(
                SetConfigData(
                    slot_entry_id=self.slot_entry.pk,
                    exercise=1,
                    sets=4,
                    weight=Decimal(80),
                    weight_rounding=Decimal(2.5),
                    weight_unit=1,
                    weight_unit_name='kg',
                    repetitions=Decimal(4),
                    repetitions_unit=1,
                    repetitions_unit_name='Repetitions',
                    repetitions_rounding=2,
                    rir=Decimal(2),
                    rest=120,
                )
            ),
        )

        self.assertDictEqual(
            asdict(self.slot_entry.get_config_data(2)),
            asdict(
                SetConfigData(
                    slot_entry_id=self.slot_entry.pk,
                    exercise=1,
                    sets=4,
                    weight=Decimal(80),
                    weight_rounding=Decimal(2.5),
                    weight_unit=1,
                    weight_unit_name='kg',
                    repetitions=Decimal(4),
                    repetitions_unit=1,
                    repetitions_unit_name='Repetitions',
                    repetitions_rounding=2,
                    rir=Decimal(2),
                    rest=120,
                )
            ),
        )

        self.assertDictEqual(
            asdict(self.slot_entry.get_config_data(3)),
            asdict(
                SetConfigData(
                    slot_entry_id=self.slot_entry.pk,
                    exercise=1,
                    sets=4,
                    weight=Decimal(80),
                    weight_rounding=Decimal('2.5'),
                    weight_unit=1,
                    weight_unit_name='kg',
                    repetitions=Decimal(4),
                    repetitions_unit=1,
                    repetitions_unit_name='Repetitions',
                    repetitions_rounding=2,
                    rir=Decimal(2),
                    rest=120,
                )
            ),
        )

        self.assertDictEqual(
            asdict(self.slot_entry.get_config_data(4)),
            asdict(
                SetConfigData(
                    slot_entry_id=self.slot_entry.pk,
                    exercise=1,
                    sets=4,
                    weight=Decimal(82.5),
                    weight_rounding=Decimal('2.5'),
                    weight_unit=1,
                    weight_unit_name='kg',
                    repetitions=Decimal(4),
                    repetitions_rounding=2,
                    repetitions_unit=1,
                    repetitions_unit_name='Repetitions',
                    rir=Decimal(2),
                    rest=120,
                )
            ),
        )

        self.assertDictEqual(
            asdict(self.slot_entry.get_config_data(5)),
            asdict(
                SetConfigData(
                    slot_entry_id=self.slot_entry.pk,
                    exercise=1,
                    sets=4,
                    weight=Decimal('42.5'),
                    weight_rounding=Decimal('2.5'),
                    weight_unit=1,
                    weight_unit_name='kg',
                    repetitions=Decimal(4),
                    repetitions_rounding=2,
                    repetitions_unit=1,
                    repetitions_unit_name='Repetitions',
                    rir=Decimal(2),
                    rest=120,
                )
            ),
        )

        self.assertDictEqual(
            asdict(self.slot_entry.get_config_data(6)),
            asdict(
                SetConfigData(
                    slot_entry_id=self.slot_entry.pk,
                    exercise=1,
                    sets=4,
                    weight=Decimal(42.5),
                    weight_rounding=Decimal('2.5'),
                    weight_unit=1,
                    weight_unit_name='kg',
                    repetitions=Decimal(4),
                    repetitions_rounding=2,
                    repetitions_unit=1,
                    repetitions_unit_name='Repetitions',
                    rir=Decimal(2),
                    rest=120,
                )
            ),
        )

    def test_requirements_sets_met(self):
        """
        Test that the sets are correctly calculated if there are requirements
        """
        self.slot_entry.weight_rounding = 2.5
        self.slot_entry.repetition_rounding = 2
        self.slot_entry.save()

        # Initial value
        SetsConfig(
            slot_entry=self.slot_entry,
            iteration=1,
            value=5,
        ).save()
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=1,
            value=50,
        ).save()
        RestConfig(
            slot_entry=self.slot_entry,
            iteration=1,
            value=90,
        ).save()

        # Increase sets by 1 at iteration 2
        SetsConfig(
            slot_entry=self.slot_entry,
            iteration=2,
            value=1,
            operation=OperationChoices.PLUS,
            step=StepChoices.ABSOLUTE,
            requirements={'rules': ['weight', 'rest']},
        ).save()

        # Rest is ok
        WorkoutLog(
            exercise_id=1,
            user_id=1,
            routine_id=1,
            slot_entry=self.slot_entry,
            iteration=1,
            weight=50,
            rest=100,
            repetitions=4,
        ).save()

        self.assertDictEqual(
            asdict(self.slot_entry.get_config_data(1)),
            asdict(
                SetConfigData(
                    slot_entry_id=self.slot_entry.pk,
                    exercise=1,
                    sets=5,
                    weight=Decimal(50),
                    weight_rounding=Decimal(2.5),
                    weight_unit=1,
                    weight_unit_name='kg',
                    rest=Decimal(90),
                )
            ),
        )

        # Sets did increase
        self.assertDictEqual(
            asdict(self.slot_entry.get_config_data(2)),
            asdict(
                SetConfigData(
                    slot_entry_id=self.slot_entry.pk,
                    exercise=1,
                    sets=6,
                    weight=Decimal(50),
                    weight_rounding=Decimal(2.5),
                    weight_unit=1,
                    weight_unit_name='kg',
                    rest=Decimal(90),
                )
            ),
        )

    def test_requirements_sets_unmet(self):
        """
        Test that the sets are correctly calculated if there are requirements
        """

        self.slot_entry.weight_rounding = 2.5
        self.slot_entry.repetition_rounding = 2
        self.slot_entry.save()

        # Initial value
        SetsConfig(
            slot_entry=self.slot_entry,
            iteration=1,
            value=5,
        ).save()
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=1,
            value=50,
        ).save()
        RestConfig(
            slot_entry=self.slot_entry,
            iteration=1,
            value=90,
        ).save()

        # Increase sets by 1 at iteration 2
        SetsConfig(
            slot_entry=self.slot_entry,
            iteration=2,
            value=1,
            operation=OperationChoices.PLUS,
            step=StepChoices.ABSOLUTE,
            requirements={'rules': ['weight', 'rest']},
        ).save()

        # Rest too low
        WorkoutLog(
            exercise_id=1,
            user_id=1,
            routine_id=1,
            slot_entry=self.slot_entry,
            iteration=1,
            weight=50,
            rest=80,
            repetitions=4,
        ).save()

        self.assertEqual(
            self.slot_entry.get_config_data(1),
            SetConfigData(
                slot_entry_id=self.slot_entry.pk,
                exercise=1,
                sets=5,
                weight=Decimal(50),
                weight_rounding=Decimal(2.5),
                weight_unit=1,
                weight_unit_name='kg',
                rest=90,
            ),
        )

        # Sets don't increase
        self.assertEqual(
            self.slot_entry.get_config_data(2),
            SetConfigData(
                slot_entry_id=self.slot_entry.pk,
                exercise=1,
                sets=5,
                weight=Decimal(50),
                weight_rounding=Decimal(2.5),
                weight_unit=1,
                weight_unit_name='kg',
                rest=90,
            ),
        )

    def test_requirements_sets_null_values(self):
        """
        Test that the sets are correctly calculated if there are requirements but
        some values are null (e.g. there is a rule to check for RiR but there is no
        RiR config)
        """

        self.slot_entry.weight_rounding = 2.5
        self.slot_entry.repetition_rounding = 2
        self.slot_entry.save()

        # Initial values
        SetsConfig(slot_entry=self.slot_entry, iteration=1, value=4).save()
        RepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=5).save()
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=1,
            value=80,
        ).save()

        # Increase weight by 2.5 at iteration 2, depends on RiR
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=2,
            value=2.5,
            operation=OperationChoices.PLUS,
            step=StepChoices.ABSOLUTE,
            requirements={'rules': ['rir']},
        ).save()

        # Logs
        WorkoutLog(
            exercise_id=1,
            user_id=1,
            routine_id=1,
            slot_entry=self.slot_entry,
            iteration=1,
            weight=None,
            rest=80,
            repetitions=4,
            rir=2,
        ).save()

        config_data = self.slot_entry.get_config_data(2)
        self.assertEqual(config_data.rir, None)
        self.assertEqual(config_data.weight, 80)

    def test_weight_config_with_logs_and_range(self):
        """
        Test that the weight is correctly calculated for each step / iteration
        if there are logs and there is a weight / rep range.

        Also covers that the upper bound of the range progresses across iterations
        and is not pinned to the value of the first iteration.
        """

        self.slot_entry.weight_rounding = 2.5
        self.slot_entry.repetition_rounding = 2
        self.slot_entry.save()

        # Initial value: 5-6 reps x 80-100 kg
        RepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=5).save()
        MaxRepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=6).save()
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=1,
            value=80,
        ).save()

        MaxWeightConfig(
            slot_entry=self.slot_entry,
            iteration=1,
            value=100,
        ).save()

        # Upper bound rises to 8 reps x 120 kg at iteration 3
        MaxWeightConfig(slot_entry=self.slot_entry, iteration=3, value=120).save()
        MaxRepetitionsConfig(slot_entry=self.slot_entry, iteration=3, value=8).save()

        # Only did 4x82.5 at iteration 2
        WorkoutLog(
            exercise_id=1,
            user_id=1,
            routine_id=1,
            slot_entry=self.slot_entry,
            iteration=2,
            weight=82.5,
            repetitions=4,
        ).save()

        # 5x80 at iteration 3
        WorkoutLog(
            exercise_id=1,
            user_id=1,
            routine_id=1,
            slot_entry=self.slot_entry,
            iteration=3,
            weight=80,
            repetitions=5,
        ).save()

        self.assertEqual(
            self.slot_entry.get_config_data(1),
            SetConfigData(
                slot_entry_id=self.slot_entry.pk,
                exercise=1,
                sets=1,
                weight=Decimal(80),
                weight_unit=1,
                weight_unit_name='kg',
                max_weight=Decimal(100),
                weight_rounding=Decimal('2.5'),
                repetitions=Decimal(4),
                repetitions_rounding=2,
                repetitions_unit=1,
                repetitions_unit_name='Repetitions',
                max_repetitions=Decimal(6),
                rir=None,
                rest=None,
            ),
        )

        self.assertEqual(
            self.slot_entry.get_config_data(2),
            SetConfigData(
                slot_entry_id=self.slot_entry.pk,
                exercise=1,
                sets=1,
                weight=Decimal(80),
                weight_unit=1,
                weight_unit_name='kg',
                max_weight=Decimal(100),
                weight_rounding=Decimal('2.5'),
                repetitions=Decimal(4),
                repetitions_unit=1,
                repetitions_unit_name='Repetitions',
                repetitions_rounding=2,
                max_repetitions=Decimal(6),
                rir=None,
                rest=None,
            ),
        )

        # The upper bound has progressed to its iteration-3 value
        self.assertEqual(
            self.slot_entry.get_config_data(3),
            SetConfigData(
                slot_entry_id=self.slot_entry.pk,
                exercise=1,
                sets=1,
                weight=Decimal(80),
                weight_unit=1,
                weight_unit_name='kg',
                max_weight=Decimal(120),
                weight_rounding=Decimal('2.5'),
                repetitions=Decimal(4),
                repetitions_unit=1,
                repetitions_unit_name='Repetitions',
                repetitions_rounding=2,
                max_repetitions=Decimal(8),
                rir=None,
                rest=None,
            ),
        )

    def test_weight_config_custom_python_class(self):
        """
        Test that the weight is correctly calculated for each step / iteration
        if there is custom python code defined
        """

        # Initial value with custom python code
        self.slot_entry.class_name = 'dummy'
        self.slot_entry.save()
        SetsConfig(slot_entry=self.slot_entry, iteration=1, value=5).save()
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=1,
            value=100,
            operation=OperationChoices.REPLACE,
        ).save()
        RepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=5).save()
        RestConfig(slot_entry=self.slot_entry, iteration=1, value=120).save()
        RiRConfig(slot_entry=self.slot_entry, iteration=1, value=2).save()

        self.assertEqual(
            self.slot_entry.get_config_data(1),
            SetConfigData(exercise=1, sets=2, weight=24, repetitions=1, rir=2, rest=120),
        )
        self.assertEqual(
            self.slot_entry.get_config_data(2),
            SetConfigData(exercise=2, sets=4, weight=42, repetitions=10, rir=1, rest=90),
        )
        self.assertEqual(
            self.slot_entry.get_config_data(3),
            SetConfigData(exercise=2, sets=4, weight=42, repetitions=10, rir=1, rest=90),
        )

    def test_empty_configs(self):
        """
        Test that the correct config is calculated if there are no configs at all
        """
        self.assertDictEqual(
            asdict(self.slot_entry.get_config_data(1)),
            asdict(
                SetConfigData(
                    slot_entry_id=self.slot_entry.pk,
                    exercise=1,
                    sets=1,
                    max_sets=None,
                    weight=None,
                    weight_rounding=None,
                    weight_unit=None,
                    repetitions=None,
                    repetitions_rounding=None,
                    repetitions_unit=None,
                    rir=None,
                    rest=None,
                )
            ),
        )

    def test_has_progression_flag(self):
        """Tests that the has_progression flag is automatically set"""

        self.assertFalse(self.slot_entry.has_progression)
        SetsConfig(slot_entry=self.slot_entry, iteration=1, value=4).save()
        SetsConfig(slot_entry=self.slot_entry, iteration=2, value=6).save()

        self.assertTrue(self.slot_entry.has_progression)

    def test_cache_get_config_data(self):
        """Tests that cache used in get_config_data is correctly (re)set"""

        key = CacheKeyMapper.slot_entry_configs_key(self.slot_entry.pk)

        set_config = SetsConfig(slot_entry=self.slot_entry, iteration=1, value=4)
        set_config.save()

        self.assertIsNone(cache.get(key))
        self.slot_entry.get_config_data(1)
        self.assertTrue(cache.get(key))

        set_config.value = 5
        set_config.save()
        self.assertIsNone(cache.get(key))

    def test_delayed_config_not_served_from_constant_cache(self):
        """
        A config that only takes effect after the first iteration yields a different
        result per iteration, so priming the cache with iteration 1 must not poison
        the result of a later iteration
        """
        WeightConfig(slot_entry=self.slot_entry, iteration=3, value=100).save()

        # Iteration 1, where the config is not active yet, populates the cache
        self.assertIsNone(self.slot_entry.get_config_data(1).weight)

        # Iteration 3 must reflect the config, not the cached iteration-1 result
        self.assertEqual(self.slot_entry.get_config_data(3).weight, Decimal(100))


class MaxConfigProgressionRegressionTestCase(WgerTestCase):
    """
    Regression tests for the latent ``max_*`` iteration-key mismatch (PR-1).

    ``max_iterations`` is keyed with underscores ('max_repetitions') while
    ``load_all_configs`` returns keys without ('maxrepetitions'). Before the fix
    both advancement sites wrote the non-underscored key while the final read used
    the underscored one, so a progressing ``Max*Config`` was stuck at iteration 1.
    """

    slot_entry: SlotEntry

    def setUp(self):
        super().setUp()

        self.slot_entry = SlotEntry(slot_id=1, exercise_id=1, order=1)
        self.slot_entry.repetition_rounding = 1
        self.slot_entry.save()

        # Bottom of the rep range so that ``max_repetitions`` is emitted in the output
        RepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=8).save()

    def test_max_config_progression_advances_no_requirements(self):
        """
        Simplest repro: a progressing MaxRepetitionsConfig with *no* requirements
        (the unconditional advance branch). Fails on master, passes after the fix.
        """

        MaxRepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=12).save()
        MaxRepetitionsConfig(slot_entry=self.slot_entry, iteration=3, value=14).save()

        self.assertEqual(self.slot_entry.get_config_data(1).max_repetitions, Decimal(12))
        self.assertEqual(self.slot_entry.get_config_data(3).max_repetitions, Decimal(14))

    def test_max_config_progression_advances_with_requirements(self):
        """
        Same, but the progressing top is requirement-gated (the requirement-gated
        advance branch). The gate is met, so the top must advance to 14.
        """

        MaxRepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=12).save()
        MaxRepetitionsConfig(
            slot_entry=self.slot_entry,
            iteration=3,
            value=14,
            requirements={'rules': ['repetitions']},
        ).save()

        # Logs at iteration 2 are evaluated for iteration 3; 8 >= calculate_repetitions (8)
        WorkoutLog(
            exercise_id=1,
            user_id=1,
            routine_id=1,
            slot_entry=self.slot_entry,
            iteration=2,
            repetitions=8,
        ).save()

        self.assertEqual(self.slot_entry.get_config_data(3).max_repetitions, Decimal(14))

    def test_max_weight_config_progression_advances_no_requirements(self):
        """
        The latent bug affected *all* ``Max*Config`` output, not only repetitions.
        Mirror of the headline repro with a progressing ``MaxWeightConfig``.
        """

        WeightConfig(slot_entry=self.slot_entry, iteration=1, value=80).save()
        MaxWeightConfig(slot_entry=self.slot_entry, iteration=1, value=100).save()
        MaxWeightConfig(slot_entry=self.slot_entry, iteration=3, value=110).save()

        self.assertEqual(self.slot_entry.get_config_data(1).max_weight, Decimal(100))
        self.assertEqual(self.slot_entry.get_config_data(3).max_weight, Decimal(110))


class DoubleProgressionTestCase(WgerTestCase):
    """
    Tests for the ``max_repetitions`` / ``max_weight`` requirement rules and the
    ``all_sets`` matching modifier (PR-2 core double progression).
    """

    slot_entry: SlotEntry

    def setUp(self):
        super().setUp()

        self.slot_entry = SlotEntry(slot_id=1, exercise_id=1, order=1)
        self.slot_entry.save()

    def _build_double_progression(
        self,
        requirements,
        *,
        slot_entry=None,
        sets=3,
        repeat=False,
    ):
        """Range 8-12 reps over ``sets`` sets, +2.5 kg gated by ``requirements``."""

        entry = slot_entry or self.slot_entry
        entry.weight_rounding = Decimal('2.5')
        entry.repetition_rounding = 1
        entry.save()

        SetsConfig(slot_entry=entry, iteration=1, value=sets).save()
        RepetitionsConfig(slot_entry=entry, iteration=1, value=8).save()
        MaxRepetitionsConfig(slot_entry=entry, iteration=1, value=12).save()
        WeightConfig(slot_entry=entry, iteration=1, value=80).save()
        WeightConfig(
            slot_entry=entry,
            iteration=2,
            value=Decimal('2.5'),
            operation=OperationChoices.PLUS,
            step=StepChoices.ABSOLUTE,
            repeat=repeat,
            requirements=requirements,
        ).save()

    def _log_set(self, iteration, repetitions, *, slot_entry=None, weight=80, **kwargs):
        WorkoutLog(
            exercise_id=1,
            user_id=1,
            routine_id=1,
            slot_entry=slot_entry or self.slot_entry,
            iteration=iteration,
            weight=weight,
            repetitions=repetitions,
            **kwargs,
        ).save()

    def test_max_repetitions_holds_until_top(self):
        """Headline case: weight holds at 10 reps, advances once the top (12) is hit"""

        self._build_double_progression({'rules': ['max_repetitions']})

        self._log_set(1, repetitions=10)
        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal(80))

        self._log_set(2, repetitions=12)
        self.assertEqual(self.slot_entry.get_config_data(3).weight, Decimal('82.5'))

    def test_max_repetitions_vs_repetitions(self):
        """``repetitions`` bumps at the bottom (8); ``max_repetitions`` does not"""

        entry_max = SlotEntry(slot_id=1, exercise_id=2, order=2)
        entry_max.save()

        self._build_double_progression({'rules': ['repetitions']})
        self._build_double_progression({'rules': ['max_repetitions']}, slot_entry=entry_max)

        self._log_set(1, repetitions=8)
        self._log_set(1, repetitions=8, slot_entry=entry_max)

        # bottom-of-range rule advances at 8
        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal('82.5'))
        # top-of-range rule holds at 8
        self.assertEqual(entry_max.get_config_data(2).weight, Decimal(80))

    def test_max_repetitions_any_policy_opt_out(self):
        """Without ``all_sets`` the permissive 'any' default advances on one top set"""

        self._build_double_progression({'rules': ['max_repetitions']})

        # 12 / 8 / 8 - only one set hit the top
        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=8)
        self._log_set(1, repetitions=8)

        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal('82.5'))

    def test_max_repetitions_all_sets_strict_holds(self):
        """Canonical 3x12: 12/8/8 with ``all_sets`` holds (not every set at the top)"""

        self._build_double_progression({'rules': ['max_repetitions'], 'all_sets': True})

        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=8)
        self._log_set(1, repetitions=8)

        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal(80))

    def test_max_repetitions_all_sets_strict_advances(self):
        """Canonical 3x12: 12/12/12 with ``all_sets`` advances"""

        self._build_double_progression({'rules': ['max_repetitions'], 'all_sets': True})

        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=12)

        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal('82.5'))

    def test_all_sets_under_logging_holds(self):
        """Logging only two sets when 3 are prescribed holds (prescribed count gate)"""

        self._build_double_progression({'rules': ['max_repetitions'], 'all_sets': True})

        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=12)

        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal(80))

    def test_all_sets_over_logging_holds(self):
        """An extra sub-top set (12/12/12/8) holds under ``all_sets``"""

        self._build_double_progression({'rules': ['max_repetitions'], 'all_sets': True})

        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=8)

        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal(80))

    def test_all_sets_over_logging_all_top_advances(self):
        """Four genuine top sets (12/12/12/12) advance (4 >= 3 and all at the top)"""

        self._build_double_progression({'rules': ['max_repetitions'], 'all_sets': True})

        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=12)

        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal('82.5'))

    def test_all_sets_empty_logs_no_advance(self):
        """``all_sets`` with no logs for the prior iteration holds (0 >= prescribed)"""

        self._build_double_progression({'rules': ['max_repetitions'], 'all_sets': True})

        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal(80))

    def test_gated_intermittent_qualification_does_not_backfill(self):
        """
        Gated progression earns exactly ONE +2.5 step per qualifying iteration and
        must NOT back-fill increments for the iterations it was skipped.

        The lifter only hits all 3 top sets once (logs for iteration 2), so the
        weight settles at one earned step (82.5) for every later iteration instead
        of jumping to two steps (85) by treating the calendar index as the count.
        """
        self._build_double_progression(
            {'rules': ['max_repetitions'], 'all_sets': True}, repeat=True
        )

        # Qualify only at iteration 2 (3 sets all at the top); nothing before/after.
        self._log_set(2, repetitions=12)
        self._log_set(2, repetitions=12)
        self._log_set(2, repetitions=12)

        self.assertEqual(self.slot_entry.get_config_data(3).weight, Decimal('82.5'))
        self.assertEqual(self.slot_entry.get_config_data(4).weight, Decimal('82.5'))
        self.assertEqual(self.slot_entry.get_config_data(5).weight, Decimal('82.5'))

    def test_gated_two_qualifications_with_a_gap(self):
        """
        Qualifying at iterations 2 and 4 (skipping 3) earns exactly two steps
        (85 = base + 2 * 2.5), not the back-filled four steps (90) the old code
        produced by jumping the pointer to the calendar index.
        """
        self._build_double_progression(
            {'rules': ['max_repetitions'], 'all_sets': True}, repeat=True
        )

        for _ in range(3):
            self._log_set(2, repetitions=12)
        for _ in range(3):
            self._log_set(4, repetitions=12)

        self.assertEqual(self.slot_entry.get_config_data(5).weight, Decimal(85))

    def test_gated_continuous_qualification_still_advances_each_step(self):
        """
        Regression guard: qualifying every iteration still yields base + (n-1)*inc,
        identical to the pre-fix behaviour for uninterrupted progression.
        """
        self._build_double_progression(
            {'rules': ['max_repetitions'], 'all_sets': True}, repeat=True
        )

        for iteration in (1, 2, 3, 4):
            for _ in range(3):
                self._log_set(iteration, repetitions=12)

        # Four earned steps on top of the base 80.
        self.assertEqual(self.slot_entry.get_config_data(5).weight, Decimal(90))

    def test_gated_zero_qualification_stays_at_base(self):
        """Never hitting the top (3x8) keeps the weight pinned at the base."""
        self._build_double_progression(
            {'rules': ['max_repetitions'], 'all_sets': True}, repeat=True
        )

        for _ in range(3):
            self._log_set(2, repetitions=8)

        self.assertEqual(self.slot_entry.get_config_data(5).weight, Decimal(80))

    def test_gated_per_log_intermittent_qualification_does_not_backfill(self):
        """
        Same intermittent-qualification regression as the all_sets case, but on the
        *per-log* (non-``all_sets``) gated branch — a single top set qualifies under
        the permissive 'any' default. Qualifying only at iteration 2 earns exactly one
        +2.5 step (82.5) at every later iteration, NOT the back-filled two steps (85).

        Guards the per-log branch's `+= 1` independently from the all_sets branch.
        """
        self._build_double_progression({'rules': ['max_repetitions']}, repeat=True)

        # One top set logged for iteration 2 only (the 'any' policy needs just one).
        self._log_set(2, repetitions=12)

        self.assertEqual(self.slot_entry.get_config_data(3).weight, Decimal('82.5'))
        self.assertEqual(self.slot_entry.get_config_data(5).weight, Decimal('82.5'))

    def test_gated_mixed_with_later_ungated_replace_is_pinned(self):
        """
        Pin test for the documented canonical-shape assumption: mixing gated
        progression with a calendar-scheduled *ungated* config (a `replace`/deload) at
        a later iteration on the SAME field is unsupported, but its behaviour must be
        intentional and detectable.

        Setup: base 80 @1 + gated +2.5 @2 (repeat) + an ungated `replace` 200 @4.
        The lifter qualifies only at iteration 2.
          - Before the ungated config applies (iteration 3) the gated counter holds at
            one earned step -> 82.5.
          - Once the ungated `replace` @4 is the last applicable config, the ungated
            branch snaps the pointer to calendar time and the replace overrides the
            chain -> 200 (the deload value). This pins the cross-branch interaction.
        """
        self._build_double_progression(
            {'rules': ['max_repetitions'], 'all_sets': True}, repeat=True
        )
        # Calendar-scheduled ungated deload/replace on the same (weight) field.
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=4,
            value=200,
            operation=OperationChoices.REPLACE,
            step=StepChoices.ABSOLUTE,
        ).save()

        for _ in range(3):
            self._log_set(2, repetitions=12)

        # Gated branch still earns exactly one step before the replace kicks in.
        self.assertEqual(self.slot_entry.get_config_data(3).weight, Decimal('82.5'))
        # From iteration 5 the ungated replace @4 is the last applicable config and
        # overrides the chain to the deload value.
        self.assertEqual(self.slot_entry.get_config_data(5).weight, Decimal(200))

    def test_max_repetitions_partial_no_advance(self):
        """Three logs below the top (11/11/11) hold under the 'any' default"""

        self._build_double_progression({'rules': ['max_repetitions']})

        self._log_set(1, repetitions=11)
        self._log_set(1, repetitions=11)
        self._log_set(1, repetitions=11)

        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal(80))

    def test_max_repetitions_missing_log(self):
        """No log for the prior iteration holds the weight"""

        self._build_double_progression({'rules': ['max_repetitions']})

        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal(80))

    def test_max_weight_symmetry(self):
        """``max_weight`` reads log.weight and gates against calculate_maxweight"""

        # entry that logs the top of the load range -> reps advance
        entry_top = SlotEntry(slot_id=1, exercise_id=1, order=1)
        entry_top.repetition_rounding = 1
        entry_top.save()
        # entry that logs below the top -> reps hold
        entry_low = SlotEntry(slot_id=1, exercise_id=2, order=2)
        entry_low.repetition_rounding = 1
        entry_low.save()

        for entry in (entry_top, entry_low):
            WeightConfig(slot_entry=entry, iteration=1, value=100).save()
            MaxWeightConfig(slot_entry=entry, iteration=1, value=110).save()
            RepetitionsConfig(slot_entry=entry, iteration=1, value=5).save()
            RepetitionsConfig(
                slot_entry=entry,
                iteration=2,
                value=1,
                operation=OperationChoices.PLUS,
                step=StepChoices.ABSOLUTE,
                requirements={'rules': ['max_weight']},
            ).save()

        self._log_set(1, repetitions=1, slot_entry=entry_top, weight=110)
        self._log_set(1, repetitions=1, slot_entry=entry_low, weight=105)

        self.assertEqual(entry_top.get_config_data(2).repetitions, Decimal(6))
        self.assertEqual(entry_low.get_config_data(2).repetitions, Decimal(5))

    def test_combined_rules(self):
        """``{'rules': ['max_repetitions', 'rir']}`` requires both in the same log"""

        entry_met = self.slot_entry
        entry_unmet = SlotEntry(slot_id=1, exercise_id=2, order=2)
        entry_unmet.save()

        for entry in (entry_met, entry_unmet):
            self._build_double_progression(
                {'rules': ['max_repetitions', 'rir']},
                slot_entry=entry,
            )
            RiRConfig(slot_entry=entry, iteration=1, value=2).save()

        # both rules met: 12 reps (>= 12) and rir 2 (>= 2)
        self._log_set(1, repetitions=12, rir=2, slot_entry=entry_met)
        # reps met but rir too high (1 < 2 under the >= gate)
        self._log_set(1, repetitions=12, rir=1, slot_entry=entry_unmet)

        self.assertEqual(entry_met.get_config_data(2).weight, Decimal('82.5'))
        self.assertEqual(entry_unmet.get_config_data(2).weight, Decimal(80))

    def test_repeat_true_with_max_repetitions(self):
        """``repeat=True`` advances every iteration the top is hit, then stalls"""

        self._build_double_progression({'rules': ['max_repetitions']}, repeat=True)

        self._log_set(1, repetitions=12)
        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal('82.5'))

        self._log_set(2, repetitions=12)
        self.assertEqual(self.slot_entry.get_config_data(3).weight, Decimal(85))

        # Stall: top not hit, weight holds at its current value
        self._log_set(3, repetitions=8)
        self.assertEqual(self.slot_entry.get_config_data(4).weight, Decimal(85))

    def test_progressing_max_rep_top_with_weight_gate(self):
        """
        Documents the loop-ordering behaviour when the rep-range top is itself
        progressing: the ``max_repetitions``-gated weight gate reads the top via
        ``max_iterations['max_repetitions']``, which (because the loop processes
        ``weight`` before ``maxrepetitions``) lags the current iteration by one.
        """

        self.slot_entry.weight_rounding = Decimal('2.5')
        self.slot_entry.repetition_rounding = 1
        self.slot_entry.save()

        RepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=8).save()
        MaxRepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=12).save()
        MaxRepetitionsConfig(slot_entry=self.slot_entry, iteration=3, value=14).save()
        WeightConfig(slot_entry=self.slot_entry, iteration=1, value=80).save()
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=2,
            value=Decimal('2.5'),
            operation=OperationChoices.PLUS,
            step=StepChoices.ABSOLUTE,
            repeat=True,
            requirements={'rules': ['max_repetitions']},
        ).save()

        self._log_set(1, repetitions=12)
        self._log_set(2, repetitions=12)
        self._log_set(3, repetitions=14)

        # Intermediate state pins the 12 -> 14 transition at iteration 3: the rep-range
        # top has advanced to 14 and the weight has bumped twice (80 -> 85), evaluated
        # against the lagging top (calculate_maxrepetitions read at the previous pointer).
        transition = self.slot_entry.get_config_data(3)
        self.assertEqual(transition.weight, Decimal(85))
        self.assertEqual(transition.max_repetitions, Decimal(14))

        config_data = self.slot_entry.get_config_data(4)
        self.assertEqual(config_data.weight, Decimal('87.5'))
        self.assertEqual(config_data.max_repetitions, Decimal(14))

    def test_unknown_rule_holds_and_throttles_warning(self):
        """
        A bogus rule persisted past the (serializer-only) validator must hold the
        change (safe fail, no crash) and warn at most once per (slot_entry, rule).
        """

        # wger
        from wger.manager.models import slot_entry as slot_entry_module

        # Clear before and after so this test neither inherits nor leaks the
        # process-global throttle state (avoids order-dependent flakiness).
        slot_entry_module._unknown_rule_logged.clear()
        self.addCleanup(slot_entry_module._unknown_rule_logged.clear)

        self._build_double_progression({'rules': ['bogus']})
        self._log_set(1, repetitions=12)

        with self.assertLogs(slot_entry_module.logger, level='WARNING') as captured:
            # First call: holds (unknown rule -> threshold None -> never advances)
            self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal(80))
            # Second call recomputes (has_progression) but the throttle must suppress
            # a second warning for the same (slot_entry, rule) pair.
            self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal(80))

        bogus_warnings = [line for line in captured.output if 'bogus' in line]
        self.assertEqual(len(bogus_warnings), 1)

    def test_all_sets_warmup_sets_excluded(self):
        """
        A warm-up SlotEntry logged at low reps in the same iteration does not affect
        the work entry's ``all_sets`` evaluation (logs are scoped by slot_entry_id).
        """

        self._build_double_progression({'rules': ['max_repetitions'], 'all_sets': True})

        warmup = SlotEntry(slot_id=1, exercise_id=1, order=2, type='warmup')
        warmup.save()

        # Work entry: 3 sets all at the top
        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=12)
        # Warm-up logged at low reps in the same iteration, but on a different entry
        self._log_set(1, repetitions=5, slot_entry=warmup)

        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal('82.5'))

    def test_all_sets_advances_non_identity_iteration_key(self):
        """
        ``all_sets`` advancing a NON-identity ``ITERATION_KEY`` field: a progressing
        ``MaxWeightConfig`` (field 'maxweight' -> pointer 'max_weight') gated by
        ``all_sets``. Guards the key normalization in the strict branch.
        """

        self.slot_entry.weight_rounding = Decimal('2.5')
        self.slot_entry.repetition_rounding = 1
        self.slot_entry.save()

        SetsConfig(slot_entry=self.slot_entry, iteration=1, value=3).save()
        RepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=8).save()
        MaxRepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=12).save()
        WeightConfig(slot_entry=self.slot_entry, iteration=1, value=80).save()
        MaxWeightConfig(slot_entry=self.slot_entry, iteration=1, value=100).save()
        MaxWeightConfig(
            slot_entry=self.slot_entry,
            iteration=2,
            value=110,
            requirements={'rules': ['max_repetitions'], 'all_sets': True},
        ).save()

        # 3 sets all at the rep-range top -> the max_weight field advances to 110
        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=12)
        self._log_set(1, repetitions=12)

        self.assertEqual(self.slot_entry.get_config_data(2).max_weight, Decimal(110))

    def test_all_sets_no_sets_config_defaults_to_one(self):
        """
        Without a ``SetsConfig`` the prescribed count is ``None`` and floors to 1:
        zero logs hold (0 >= 1 is False), a single top log advances.
        """

        self.slot_entry.weight_rounding = Decimal('2.5')
        self.slot_entry.repetition_rounding = 1
        self.slot_entry.save()

        RepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=8).save()
        MaxRepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=12).save()
        WeightConfig(slot_entry=self.slot_entry, iteration=1, value=80).save()
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=2,
            value=Decimal('2.5'),
            operation=OperationChoices.PLUS,
            step=StepChoices.ABSOLUTE,
            requirements={'rules': ['max_repetitions'], 'all_sets': True},
        ).save()

        # No logs for the prior iteration -> holds (0 >= 1 is False)
        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal(80))

        # One log at the top -> advances (default prescribed count of 1 is met)
        self._log_set(1, repetitions=12)
        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal('82.5'))

    def test_all_sets_zero_sets_config_floors_to_one(self):
        """
        A degenerate ``SetsConfig(value=0)`` floors the prescribed count to 1, so an
        *empty* log set holds instead of vacuously advancing. Without the ``< 1``
        floor, ``prescribed_sets`` would be 0 and ``0 >= 0`` together with the vacuous
        ``all([])`` over no logs would advance the weight — the bug the floor guards.
        """

        self.slot_entry.weight_rounding = Decimal('2.5')
        self.slot_entry.repetition_rounding = 1
        self.slot_entry.save()

        SetsConfig(slot_entry=self.slot_entry, iteration=1, value=0).save()
        RepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=8).save()
        MaxRepetitionsConfig(slot_entry=self.slot_entry, iteration=1, value=12).save()
        WeightConfig(slot_entry=self.slot_entry, iteration=1, value=80).save()
        WeightConfig(
            slot_entry=self.slot_entry,
            iteration=2,
            value=Decimal('2.5'),
            operation=OperationChoices.PLUS,
            step=StepChoices.ABSOLUTE,
            requirements={'rules': ['max_repetitions'], 'all_sets': True},
        ).save()

        # No logs for the prior iteration -> holds (floored 0 -> 1, so 0 >= 1 is False).
        # This is exactly the vacuous zero-log advance the floor prevents.
        self.assertEqual(self.slot_entry.get_config_data(2).weight, Decimal(80))

    def test_all_sets_combined_rules(self):
        """
        The strict ``all_sets`` path with combined ``['max_repetitions', 'rir']`` is
        not reps-specific: every set must meet *both* rules.
        """

        entry_met = self.slot_entry
        entry_unmet = SlotEntry(slot_id=1, exercise_id=2, order=2)
        entry_unmet.save()

        for entry in (entry_met, entry_unmet):
            self._build_double_progression(
                {'rules': ['max_repetitions', 'rir'], 'all_sets': True},
                slot_entry=entry,
            )
            RiRConfig(slot_entry=entry, iteration=1, value=2).save()

        # All 3 sets meet both rules (reps 12 >= 12 and rir 2 >= 2)
        self._log_set(1, repetitions=12, rir=2, slot_entry=entry_met)
        self._log_set(1, repetitions=12, rir=2, slot_entry=entry_met)
        self._log_set(1, repetitions=12, rir=2, slot_entry=entry_met)

        # One set fails the rir rule (1 < 2 under the >= gate) -> strict path holds
        self._log_set(1, repetitions=12, rir=2, slot_entry=entry_unmet)
        self._log_set(1, repetitions=12, rir=2, slot_entry=entry_unmet)
        self._log_set(1, repetitions=12, rir=1, slot_entry=entry_unmet)

        self.assertEqual(entry_met.get_config_data(2).weight, Decimal('82.5'))
        self.assertEqual(entry_unmet.get_config_data(2).weight, Decimal(80))


class UnknownRuleLogThrottleTestCase(SimpleTestCase):
    """Unit coverage for the ``_log_unknown_rule_once`` throttle helper."""

    def setUp(self):
        # wger
        from wger.manager.models import slot_entry as slot_entry_module

        self.module = slot_entry_module
        self.module._unknown_rule_logged.clear()
        self.addCleanup(self.module._unknown_rule_logged.clear)

    def test_saved_entry_is_throttled(self):
        """A saved entry warns once per (id, rule) and is cached in the guard"""

        with self.assertLogs(self.module.logger, level='WARNING') as captured:
            self.module._log_unknown_rule_once(42, 'bogus')
            self.module._log_unknown_rule_once(42, 'bogus')

        self.assertEqual(len([line for line in captured.output if 'bogus' in line]), 1)
        self.assertIn((42, 'bogus'), self.module._unknown_rule_logged)

    def test_unsaved_entry_warns_directly_without_caching(self):
        """
        An unsaved entry (``id is None``) must warn each call (no dedupe through the
        shared guard) and must not pollute the guard with a ``None`` key.
        """

        with self.assertLogs(self.module.logger, level='WARNING') as captured:
            self.module._log_unknown_rule_once(None, 'bogus')
            self.module._log_unknown_rule_once(None, 'bogus')

        unsaved_warnings = [line for line in captured.output if 'unsaved' in line]
        self.assertEqual(len(unsaved_warnings), 2)
        self.assertEqual(self.module._unknown_rule_logged, set())


class SlotEntryDuplicateConfigTestCase(SimpleTestCase):
    def test_duplicate_configs(self):
        configs = [
            WeightConfig(
                pk=1,
                iteration=1,
                value=80,
                operation=OperationChoices.REPLACE,
                repeat=False,
            ),
            WeightConfig(
                pk=2,
                iteration=2,
                value=2,
                operation=OperationChoices.PLUS,
                repeat=True,
            ),
            WeightConfig(
                pk=3,
                iteration=6,
                value=50,
                operation=OperationChoices.REPLACE,
                repeat=False,
            ),
        ]

        result = SlotEntry.duplicate_configs(
            10,
            configs=configs,
        )

        # Repeats the config of iteration 2 up to the 8th one, the rest remains unchanged
        self.assertEqual(len(result), 6)

        self.assertEqual(result[0].iteration, 1)
        self.assertEqual(result[0].value, 80)

        self.assertEqual(result[1].iteration, 2)
        self.assertEqual(result[1].value, 2)

        self.assertEqual(result[2].iteration, 3)
        self.assertEqual(result[2].value, 2)

        self.assertEqual(result[3].iteration, 4)
        self.assertEqual(result[3].value, 2)

        self.assertEqual(result[4].iteration, 5)
        self.assertEqual(result[4].value, 2)

        self.assertEqual(result[5].iteration, 6)
        self.assertEqual(result[5].value, 50)

    def test_duplicate_configs_2(self):
        """Test that repeat configs can follow each other"""

        configs = [
            WeightConfig(
                pk=1,
                iteration=1,
                value=80,
                operation=OperationChoices.REPLACE,
                repeat=False,
            ),
            WeightConfig(
                pk=2,
                iteration=2,
                value=2,
                operation=OperationChoices.PLUS,
                repeat=True,
            ),
            WeightConfig(
                pk=3,
                iteration=5,
                value=3,
                operation=OperationChoices.MINUS,
                repeat=True,
            ),
        ]

        result = SlotEntry.duplicate_configs(
            10,
            configs=configs,
        )

        # Repeats the config of iteration 2 up to the 8th one, the rest remains unchanged
        self.assertEqual(len(result), 10)

        self.assertEqual(result[0].iteration, 1)
        self.assertEqual(result[0].value, 80)
        self.assertFalse(result[0].repeat)

        self.assertEqual(result[1].iteration, 2)
        self.assertEqual(result[1].value, 2)
        self.assertTrue(result[1].repeat)

        self.assertEqual(result[2].iteration, 3)
        self.assertEqual(result[2].value, 2)
        self.assertTrue(result[2].repeat)

        self.assertEqual(result[3].iteration, 4)
        self.assertEqual(result[3].value, 2)
        self.assertTrue(result[3].repeat)

        self.assertEqual(result[4].iteration, 5)
        self.assertEqual(result[4].value, 3)
        self.assertTrue(result[4].repeat)

        self.assertEqual(result[5].iteration, 6)
        self.assertEqual(result[5].value, 3)
        self.assertTrue(result[5].repeat)


class CalculateConfigValueTestCase(SimpleTestCase):
    def test_compound_weight_is_capped(self):
        """Percent progressions can't push the output past MAX_COMPOUND_VALUE"""

        configs = [
            WeightConfig(iteration=1, value=100, operation=OperationChoices.REPLACE),
            # +50% per iteration, repeated enough times to blow past 9999.99
            *[
                WeightConfig(
                    iteration=i,
                    value=50,
                    operation=OperationChoices.PLUS,
                    step=StepChoices.PERCENT,
                )
                for i in range(2, 20)
            ],
        ]

        result = SlotEntry.calculate_config_value(configs)

        self.assertEqual(result, MAX_COMPOUND_VALUE)

    def test_rir_is_capped_at_rir_max(self):
        """RiR uses the tighter cap (max_digits=2, decimal_places=1)"""

        configs = [
            RiRConfig(iteration=1, value=2, operation=OperationChoices.REPLACE),
            RiRConfig(iteration=2, value=50, operation=OperationChoices.PLUS),
        ]

        result = SlotEntry.calculate_config_value(configs, max_value=MAX_COMPOUND_RIR)

        self.assertEqual(result, MAX_COMPOUND_RIR)

    def test_value_below_cap_is_unchanged(self):
        configs = [
            WeightConfig(iteration=1, value=80, operation=OperationChoices.REPLACE),
            WeightConfig(iteration=2, value=5, operation=OperationChoices.PLUS),
        ]

        result = SlotEntry.calculate_config_value(configs)

        self.assertEqual(result, Decimal(85))
