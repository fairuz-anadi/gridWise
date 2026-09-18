"""LLM output -> validated directives (the guardrail layer). Owner: Turjo.

PLACEHOLDER so the API runs before the LLM lane lands: every note comes back as no_op.
Turjo replaces the body; the signature is the agreed interface and must not change.
"""
from app.schemas import Battery, Directive, DirectiveType

__all__ = ["Directive", "interpret_and_validate"]


async def interpret_and_validate(notes: list[str], battery: Battery) -> list[Directive]:
    """One Directive per note, in note_index order. Never raises; a note that fails becomes no_op."""
    return [
        Directive(
            note_index=i,
            applies=False,
            directive_type=DirectiveType.no_op,
            structured_adjustment=None,
            explanation="Interpreter not implemented yet.",
        )
        for i in range(len(notes))
    ]
