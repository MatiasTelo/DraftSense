"""El tipo 1 como ranking de cinco campeones (ADR-022, `docs/20-tipos-de-pregunta.md` §2).

El sampler elige un **par ancla** como antes elegía la pregunta de tipo 1 —puente, honeypot,
retest o el par por prioridad—, y este módulo lo completa con tres campeones al azar, guarda el
ranking servido y, al contestar, traduce el orden a las diez comparaciones que se guardan.

Lo que se guarda sigue siendo `pairwise_dimension` con `{"choice": "a" | "b" | "unknown"}`, una
fila por par: todo lo que ya funcionaba por par —`answer_counts`, entropía, cobertura, aristas del
grafo y agregación— sigue funcionando sin saber que hubo un ranking.
"""

from __future__ import annotations

import itertools
import random
import uuid
from collections.abc import Collection, Iterable, Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Question, QuestionType, Ranking
from app.services.answers import UNKNOWN_CHOICE, AnswerShapeError
from app.services.questions import RANKING_SIZE, Combination, Space

#: Un par en forma canónica, con su dimensión: la identidad de una pregunta de tipo 1.
PairKey = tuple[int, int, int]


def canonical(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a < b else (b, a)


def pairs(champions: Iterable[int]) -> list[tuple[int, int]]:
    """Los pares canónicos de un conjunto de campeones: diez para un ranking."""
    return [canonical(a, b) for a, b in itertools.combinations(champions, 2)]


def combinations_of(champions: Sequence[int], dimension_id: int) -> list[Combination]:
    return [
        Combination(
            QuestionType.PAIRWISE_DIMENSION, low, champion_b=high, dimension_id=dimension_id
        )
        for low, high in pairs(champions)
    ]


def choices_from_order(order: Sequence[int]) -> dict[tuple[int, int], str]:
    """Qué dice el orden sobre cada par: `a` si `champion_a` quedó arriba, `b` si no.

    `order` va de más a menos. El orden canónico de la pregunta (`champion_a < champion_b`) no
    tiene nada que ver con quién quedó arriba, y por eso la traducción es por par.
    """
    position = {champion: index for index, champion in enumerate(order)}
    return {
        (low, high): "a" if position[low] < position[high] else "b" for low, high in pairs(order)
    }


def extreme_pair(order: Sequence[int]) -> tuple[int, int]:
    """El par de las puntas: el primero contra el último. Es el que se repite como retest."""
    return canonical(order[0], order[-1])


def validate_answer(answer: dict[str, Any], champions: Collection[int]) -> list[int] | None:
    """El orden recibido, o `None` si fue *Not sure*. Lanza `AnswerShapeError` si no corresponde.

    El orden tiene que ser una permutación exacta de los cinco campeones servidos: ni repetidos, ni
    faltantes, ni ajenos. Que el cliente sólo pueda reordenar lo que se le mostró es lo que hace
    que el ranking guardado sea el que la persona vio.
    """
    if set(answer) == {"choice"}:
        if answer["choice"] != UNKNOWN_CHOICE:
            raise AnswerShapeError("choice must be 'unknown'; use 'order' to rank")
        return None
    if set(answer) != {"order"}:
        raise AnswerShapeError("answer must have exactly the key 'order' or 'choice'")
    order = answer["order"]
    if (
        not isinstance(order, list)
        or not all(isinstance(c, int) and not isinstance(c, bool) for c in order)
        or len(order) != RANKING_SIZE
        or set(order) != set(champions)
    ):
        raise AnswerShapeError(
            f"order must list the {RANKING_SIZE} champions of the ranking, each once"
        )
    return list(order)


def draw_extras(
    anchor: Question,
    space: Space,
    honeypot_pairs: Collection[PairKey],
    rng: random.Random,
    max_retries: int,
) -> list[int]:
    """Tres campeones más para el ranking del ancla (`docs/21-sampler.md` §5.1).

    Se vuelve a sortear si alguno de los otros nueve pares es una honeypot en esa dimensión: una
    honeypot sólo se contesta como ancla y con su cadencia (`docs/22-calidad-de-datos.md` §3.7).
    Si los reintentos se agotan —un pool chico y un catálogo denso—, se acepta el último sorteo: un
    lote corto es peor, y al guardar, la fila de ese par no se inserta (`responses.record_ranking`),
    así que la honeypot no queda contestada fuera de cadencia.
    """
    assert anchor.champion_b is not None and anchor.dimension_id is not None
    anchor_pair = (anchor.champion_a, anchor.champion_b)
    others = [c for c in sorted(space.champion_ids) if c not in anchor_pair]
    extras: list[int] = []
    for _ in range(max(1, max_retries)):
        extras = rng.sample(others, RANKING_SIZE - 2)
        chosen = [*anchor_pair, *extras]
        if not any(
            (low, high, anchor.dimension_id) in honeypot_pairs
            for low, high in pairs(chosen)
            if (low, high) != anchor_pair
        ):
            break
    return extras


def keys_of(ranking: Ranking) -> set[PairKey]:
    """Los diez pares del ranking, con su dimensión."""
    return {(low, high, ranking.dimension_id) for low, high in pairs(ranking.champions)}


async def pending_pairs(
    session: AsyncSession, respondent_id: uuid.UUID, queued: Collection[int]
) -> set[PairKey]:
    """Los pares de los rankings que el cliente tiene en cola sin contestar.

    El cliente manda en `queued` los `question_id` de sus tarjetas, que en el tipo 1 son anclas
    (ADR-020). Si el ancla de un ranking nuevo fuera uno de estos pares, contestar primero el de
    la cola dejaría ese par respondido y el ranking nuevo terminaría en un 409.
    """
    if not queued:
        return set()
    rows = await session.execute(
        sa.select(Ranking).where(
            Ranking.respondent_id == respondent_id,
            Ranking.anchor_question_id.in_(list(queued)),
            Ranking.submitted_order.is_(None),
        )
    )
    taken: set[PairKey] = set()
    for ranking in rows.scalars():
        taken |= keys_of(ranking)
    return taken


async def honeypot_pairs(session: AsyncSession, patch_id: int) -> set[PairKey]:
    """Los pares de las honeypots vigentes del parche, para no meterlos como pares no ancla."""
    rows = await session.execute(
        sa.select(Question.champion_a, Question.champion_b, Question.dimension_id).where(
            Question.patch_id == patch_id,
            Question.is_honeypot,
            Question.type == QuestionType.PAIRWISE_DIMENSION,
        )
    )
    return {(a, b, d) for a, b, d in rows.tuples() if b is not None and d is not None}


def build(
    respondent_id: uuid.UUID,
    anchor: Question,
    space: Space,
    honeypots: Collection[PairKey],
    rng: random.Random,
    max_retries: int,
) -> Ranking:
    """El ranking servido, con los cinco campeones en orden aleatorio. No lo agrega a la sesión.

    El orden aleatorio no es cosmético: si el ancla saliera siempre en las dos primeras filas, la
    tarjeta delataría cuál es el par que importa —y con él, una honeypot o un retest (§1.4 de
    `docs/12-api.md`)—.
    """
    assert anchor.champion_b is not None and anchor.dimension_id is not None
    champions = [
        anchor.champion_a,
        anchor.champion_b,
        *draw_extras(anchor, space, honeypots, rng, max_retries),
    ]
    rng.shuffle(champions)
    return Ranking(
        respondent_id=respondent_id,
        patch_id=anchor.patch_id,
        dimension_id=anchor.dimension_id,
        anchor_question_id=anchor.question_id,
        champions=champions,
    )
