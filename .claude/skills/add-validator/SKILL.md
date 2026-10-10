---
name: add-validator
description: Add a new custom Guardrails AI validator (or injection/PII pattern) to the analyst guardrail pipeline, wired into the suite and covered by red-team tests.
---
# Add a validator

1. Implement it in `analyst/guardrails/validators.py`: subclass `Validator`, decorate with
   `@register_validator(name="analyst/<name>", data_type="string")`, return `PassResult` / `FailResult`
   (provide `fix_value` if FIX is possible). For a new injection phrase, just extend `_INJECTION_PATTERNS`.
2. Wire it in `analyst/guardrails/suite.py` on the right checkpoint (input / sql / tool_output / output) with the
   right `OnFailAction` (EXCEPTION block, FIX repair, NOOP flag); log through `EventLog`.
3. Add tests in `tests/test_validators.py`: positive, negative (no false positive on normal analyst questions),
   and a control with guardrails disabled (`env_unguarded`) showing the attack goes through.
4. Update the README guardrail table if the behaviour is user-visible.
5. Run the `verify` skill.
