"""The 24 supported SME application and financial-statement fields."""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .schemas import Evidence

Kind = Literal["application", "financials"]
APPLICATION_FIELDS = (
    "company_legal_name",
    "tax_id",
    "registration_number",
    "legal_form",
    "business_activity",
    "establishment_date",
    "requested_amount",
    "currency",
    "financing_purpose",
    "tenor_months",
    "declared_annual_turnover",
    "declared_existing_debt",
)
FINANCIAL_FIELDS = (
    "company_legal_name",
    "tax_id",
    "reporting_period",
    "currency",
    "unit_scale",
    "revenue",
    "ebitda",
    "net_profit_or_loss",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "total_borrowings",
)
FIELDS = {"application": APPLICATION_FIELDS, "financials": FINANCIAL_FIELDS}
MONEY = {
    "requested_amount",
    "declared_annual_turnover",
    "declared_existing_debt",
    "revenue",
    "ebitda",
    "net_profit_or_loss",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "total_borrowings",
}
LABELS = dict(
    zip(
        dict.fromkeys(APPLICATION_FIELDS + FINANCIAL_FIELDS),
        [
            "Επωνυμία",
            "ΑΦΜ",
            "Αριθμός ΓΕΜΗ",
            "Νομική μορφή",
            "Δραστηριότητα",
            "Ημερομηνία ίδρυσης",
            "Αιτούμενο ποσό",
            "Νόμισμα",
            "Σκοπός χρηματοδότησης",
            "Διάρκεια σε μήνες",
            "Δηλωμένος κύκλος εργασιών",
            "Δηλωμένος υφιστάμενος δανεισμός",
            "Περίοδος αναφοράς",
            "Μονάδα / κλίμακα",
            "Κύκλος εργασιών",
            "EBITDA",
            "Καθαρό αποτέλεσμα",
            "Σύνολο ενεργητικού",
            "Σύνολο υποχρεώσεων",
            "Σύνολο ιδίων κεφαλαίων",
            "Συνολικός δανεισμός",
        ],
    )
)


class ProposedField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_name: str
    raw_value: str | None
    confidence: float = Field(
        ge=0,
        le=1,
        description="Uncalibrated reading confidence, not probability of correctness. Low for unclear/ambiguous characters.",
    )
    number_locale: Literal["el", "en", "unknown"]
    uncertainty: str | None
    evidence: list[Evidence]


class DocumentExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: Kind
    fields: list[ProposedField] = Field(min_length=12, max_length=12)

    @model_validator(mode="after")
    def exact_fields(self) -> "DocumentExtraction":
        names = [x.field_name for x in self.fields]
        if len(set(names)) != 12 or set(names) != set(FIELDS[self.document_type]):
            raise ValueError(
                "Exactly the twelve fields of the declared document type are required."
            )
        return self


QUESTIONS = (
    "Ποια είναι η επωνυμία και το ΑΦΜ της επιχείρησης;",
    "Ποιο ποσό χρηματοδότησης ζητείται;",
    "Ποιος είναι ο σκοπός και η διάρκεια της χρηματοδότησης;",
    "Ποιος είναι ο κύκλος εργασιών της τελευταίας χρήσης;",
    "Ποιο είναι το EBITDA;",
    "Ποιο είναι το καθαρό αποτέλεσμα της χρήσης;",
    "Ποια είναι τα συνολικά στοιχεία ενεργητικού, οι υποχρεώσεις και τα ίδια κεφάλαια;",
    "Ποιος είναι ο συνολικός τραπεζικός δανεισμός;",
    "Συμφωνεί ο δηλωμένος κύκλος εργασιών της αίτησης με τις οικονομικές καταστάσεις;",
    "Ποια missing, uncertain ή inconsistent στοιχεία απαιτούν ανθρώπινο έλεγχο;",
)
