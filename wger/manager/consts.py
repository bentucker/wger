#  This file is part of wger Workout Manager <https://github.com/wger-project>.
#  Copyright (C) 2013 - 2021 wger Team
#
#  wger Workout Manager is free software: you can redistribute it and/or modify
#  it under the terms of the GNU Affero General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  wger Workout Manager is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU Affero General Public License for more details.
#
#  You should have received a copy of the GNU Affero General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.

# Standard Library
from collections import namedtuple


RIR_OPTIONS = [None, 0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5]

REP_UNIT_REPETITIONS = 1
REP_UNIT_TILL_FAILURE = 2
REP_UNIT_MAX_REPS = 7

REP_UNIT_SECONDS = 3
REP_UNIT_MINUTES = 4

REP_UNIT_METERS = 8
REP_UNIT_KILOMETERS = 6
REP_UNIT_MILES = 5

WEIGHT_UNIT_KG = 1
WEIGHT_UNIT_LB = 2

# Unit type constants (matching RepetitionUnit.UNIT_TYPE_* choices)
UNIT_TYPE_REPETITIONS = 'REPETITIONS'
UNIT_TYPE_TIME = 'TIME'
UNIT_TYPE_DISTANCE = 'DISTANCE'


RequirementRule = namedtuple(
    'RequirementRule',
    ['log_field', 'threshold_method', 'iteration_key'],
)
"""
Metadata for a single requirement rule key.

    log_field        – attribute on WorkoutLog holding the *logged* value to test
    threshold_method – SlotEntry method computing the *prescribed* threshold
    iteration_key    – key in `max_iterations` tracking that threshold's progression
"""

# Single source of truth for requirement rule keys, shared by the serializer-level
# validator (allowed keys) and the progression engine (gate logic). The table holds
# strings only, so this module stays a dependency-free leaf (no models import) and
# avoids app-loading import-order fragility.
#
# Note the decoupling that makes "double progression" work with zero schema change:
# the public rule key `max_repetitions` (underscore, consistent with the API's
# `max_repetitions_configs` field and `SetConfigData.max_repetitions`) reads the
# *logged* value `log.repetitions` but compares it against the *top-of-range*
# calculator `calculate_maxrepetitions` (no underscore). The table maps one to the
# other explicitly, so no existing method is renamed and no `f'calculate_{rule}'`
# string construction is used.
REQUIREMENT_RULES = {
    'weight': RequirementRule('weight', 'calculate_weight', 'weight'),
    'repetitions': RequirementRule('repetitions', 'calculate_repetitions', 'repetitions'),
    'rir': RequirementRule('rir', 'calculate_rir', 'rir'),
    'rest': RequirementRule('rest', 'calculate_rest', 'rest'),
    'max_weight': RequirementRule('weight', 'calculate_maxweight', 'maxweight'),
    'max_repetitions': RequirementRule(
        'repetitions', 'calculate_maxrepetitions', 'maxrepetitions'
    ),
}

REQUIREMENTS_RULES_KEYS = list(REQUIREMENT_RULES.keys())
