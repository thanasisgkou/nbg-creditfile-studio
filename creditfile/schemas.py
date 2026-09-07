from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

FieldKey = Literal[
    "company_name",
    "requested_amount",
    "loan_purpose",
    "duration_months",
    "financial_year",
    "revenue",
    "net_income",
    "total_assets",
    "total_liabilities",
    "equity",
]
FIELD_LABELS = dict(
    zip(
        FieldKey.__args__,
        [
            "Επωνυμία",
            "Αιτούμενο ποσό",
            "Σκοπός χρηματοδότησης",
            "Διάρκεια (μήνες)",
            "Οικονομική χρήση",
            "Κύκλος εργασιών",
            "Καθαρά αποτελέσματα",
            "Σύνολο ενεργητικού",
            "Σύνολο υποχρεώσεων",
            "Ίδια κεφάλαια",
        ],
    )
)
FINANCIAL = {
    "financial_year",
    "revenue",
    "net_income",
    "total_assets",
    "total_liabilities",
    "equity",
}
MONEY = FINANCIAL - {"financial_year"} | {"requested_amount"}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(StrictModel):
    document_id: str
    page: int = Field(ge=1)
    block_id: str
    quote: str = Field(
        min_length=1,
        description="Exact single continuous source line. Use separate evidence objects for value, company, unit and year header. Never omit words within a quote or join nonadjacent lines.",
    )


class Block(StrictModel):
    case_id: str
    document_id: str
    page: int
    block_id: str
    text: str
    document_type: Literal["application", "financials"]


class Candidate(StrictModel):
    field_key: FieldKey
    entity: str | None
    financial_year: int | None
    raw_value: str
    currency: Literal["EUR"] | None
    unit_multiplier: Literal["1", "1000"] | None
    number_locale: Literal["el", "en", "unknown"]
    evidence: list[Evidence] = Field(min_length=1)


class DocumentMetadata(StrictModel):
    company_name: str | None
    currency: Literal["EUR"] | None
    unit_multiplier: Literal["1", "1000"] | None
    number_locale: Literal["el", "en", "unknown"]
    evidence: list[Evidence]


class ModelCandidate(StrictModel):
    field_key: FieldKey
    financial_year: int | None
    raw_value: str
    evidence: list[Evidence] = Field(min_length=1)


class ExtractionResponse(StrictModel):
    metadata: DocumentMetadata
    candidates: list[ModelCandidate]


class Claim(StrictModel):
    text: str = Field(
        description="Complete factual answer in Greek, including the actual requested value, currency and year where applicable. Not a title or field label."
    )
    evidence: list[Evidence] = Field(min_length=1)


class Answer(StrictModel):
    status: Literal["answered", "partial", "not_found", "conflict", "out_of_scope", "needs_review"]
    claims: list[Claim]
    unanswered: list[str]
