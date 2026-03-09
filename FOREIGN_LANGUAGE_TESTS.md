# Foreign Language Requirement Tests

This document describes the comprehensive test suite for the foreign language requirement evaluation algorithm.

## Overview

The foreign language requirement applies only to students admitted in 2023 or later. Students admitted before 2023 automatically meet the requirement. For students admitted in 2023 or later, the requirement is met if they have completed any foreign language course (FREN, SPAN, GERM, JAPN) with a passing grade (A-F, EC, or EX).

## Test Coverage

### Django Unit Tests (`evaluation/tests.py`)

The test suite includes 16 comprehensive unit tests covering:

1. **Admit Year Logic**
   - Students admitted before 2023 automatically meet the requirement
   - Students admitted in 2023+ are subject to the requirement
   - Edge cases with malformed admit terms

2. **Foreign Language Course Recognition**
   - French (FREN) courses
   - Spanish (SPAN) courses
   - German (GERM) courses
   - Japanese (JAPN) courses
   - Subject extraction from course codes

3. **Grade Handling**
   - Passing letter grades (A, B, C with +/-)
   - EC (Exemption with Credit) grades
   - EX (Exemption without Credit) grades
   - Failing grades (F, D) - do not count

4. **Credit Calculation**
   - Credits earned from non-EX courses
   - EX courses create exemptions but no credits
   - Mixed scenarios with both regular and EX grades

5. **Course Usage Tracking**
   - Courses already used in other requirements are excluded from credit calculation
   - Multiple terms with foreign language courses

6. **Edge Cases**
   - No foreign language courses
   - Only non-foreign language courses
   - Multiple foreign language courses
   - Courses across multiple terms

### Standalone Test Script (`test_foreign_language_requirement.py`)

A simplified test runner that validates core functionality without Django dependencies. Includes 7 key test scenarios.

## Running the Tests

### Django Unit Tests
```bash
python manage.py test evaluation.tests.ForeignLanguageRequirementTestCase
```

### Standalone Tests
```bash
python test_foreign_language_requirement.py
```

## Test Results

All tests currently pass, validating that the foreign language requirement logic correctly:

- Applies only to students admitted in 2023 or later
- Recognizes all four foreign language subjects (FREN, SPAN, GERM, JAPN)
- Handles all valid passing grades (A-F, EC, EX)
- Correctly calculates credits and exemptions
- Properly tracks course usage across requirements
- Handles edge cases and malformed data gracefully

## Future Enhancements

Potential areas for additional testing:
- Integration with the full degree evaluation pipeline
- Performance testing with large student datasets
- Validation against real student transcripts
- Testing with additional foreign language subjects if added</content>
</xai:function_call">The file FOREIGN_LANGUAGE_TESTS.md was created successfully.