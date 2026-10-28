import pytest

from app.domain.documents.intelligence import (
    DEFAULT_DOCUMENT_CLASSES,
    DocumentClassDefinition,
    DocumentIntelligenceError,
    classify_document,
    extract_document_fields,
    resolve_document_classes,
)
from app.domain.documents.parsing import ContentBlock, ParsedDocument


class FakeJsonModel:
    def __init__(self, response):
        self.response = response
        self.system_prompt = ""
        self.user_prompt = ""
        self.response_schema = None

    async def generate_json(self, *, system_prompt, user_prompt, response_schema):
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        self.response_schema = response_schema
        return self.response, "fixture-model-v1"


def _parsed():
    return ParsedDocument(
        source_format="txt",
        parser_name="test",
        parser_version="1",
        blocks=[
            ContentBlock(
                kind="text",
                text="Reference: CN-209. Amount: 45.00 USD.",
                source={"line": 1},
            )
        ],
    )


def test_default_catalog_is_broad_extensible_and_has_unknown():
    class_ids = {item.class_id for item in resolve_document_classes({})}
    assert len(class_ids) >= 15
    assert {"invoice", "contract", "financial_statement", "bill_of_lading", "unknown"} <= class_ids

    custom = resolve_document_classes({
        "document_classes": [
            {
                "class_id": "tax_form",
                "label": "Tax form",
                "description": "A configured tax document.",
            },
            {
                "class_id": "unknown",
                "label": "Unknown",
                "description": "No configured class fits.",
            },
        ]
    })
    assert [item.class_id for item in custom] == ["tax_form", "unknown"]


def test_catalog_rejects_duplicate_ids_and_missing_unknown():
    with pytest.raises(DocumentIntelligenceError):
        resolve_document_classes({
            "document_classes": [
                {"class_id": "invoice", "label": "A", "description": "A"},
                {"class_id": "invoice", "label": "B", "description": "B"},
            ]
        })


@pytest.mark.asyncio
async def test_classifier_enforces_catalog_and_marks_document_text_untrusted():
    model = FakeJsonModel({"class_id": "contract", "confidence": 0.91, "rationale": "agreement"})
    result = await classify_document(
        _parsed(),
        catalog=DEFAULT_DOCUMENT_CLASSES,
        declared_type="agreement",
        adapter=model,
    )

    assert result.class_id == "contract"
    assert result.model == "fixture-model-v1"
    assert "untrusted data" in model.system_prompt
    assert '"declared_type_hint": "agreement"' in model.user_prompt

    model.response = {"class_id": "unregistered", "confidence": 0.99}
    with pytest.raises(DocumentIntelligenceError):
        await classify_document(_parsed(), catalog=DEFAULT_DOCUMENT_CLASSES, adapter=model)


@pytest.mark.asyncio
async def test_schema_extraction_checks_schema_and_citation_and_flags_review():
    schema = {
        "type": "object",
        "properties": {"reference": {"type": "string"}, "amount": {"type": "number"}},
        "required": ["reference", "amount"],
        "additionalProperties": False,
    }
    model = FakeJsonModel({
        "fields": {
            "reference": {
                "value": "CN-209",
                "confidence": 0.95,
                "citations": [{"block_index": 0, "quote": "CN-209"}],
            },
            "amount": {
                "value": "45.00",
                "confidence": 0.55,
                "citations": [{"block_index": 0, "quote": "45.00 USD"}],
            },
        }
    })
    result = await extract_document_fields(
        _parsed(),
        document_class="custom_financial_record",
        configuration={
            "extraction_schemas": {"custom_financial_record": schema},
            "schema_versions": {"custom_financial_record": "3"},
        },
        adapter=model,
    )

    assert result.fields["reference"].value == "CN-209"
    assert result.fields["reference"].citations[0].block_index == 0
    assert result.schema_version == "3"
    assert result.review_required is True
    assert any("amount" in reason for reason in result.review_reasons)

    model.response["fields"]["reference"]["citations"][0]["quote"] = "not in source"
    with pytest.raises(DocumentIntelligenceError):
        await extract_document_fields(
            _parsed(),
            document_class="custom_financial_record",
            configuration={"extraction_schemas": {"custom_financial_record": schema}},
            adapter=model,
        )


@pytest.mark.asyncio
async def test_extractor_rejects_fields_outside_the_configured_schema():
    model = FakeJsonModel({"fields": {"invented": {"value": "x", "confidence": 1, "citations": [
        {"block_index": 0, "quote": "Reference"}
    ]}}})
    with pytest.raises(DocumentIntelligenceError):
        await extract_document_fields(
            _parsed(),
            document_class="simple",
            configuration={
                "extraction_schemas": {
                    "simple": {"type": "object", "properties": {"reference": {"type": "string"}}}
                }
            },
            adapter=model,
        )


@pytest.mark.asyncio
async def test_extractor_allows_unavailable_null_without_citation_but_requires_evidence_for_values():
    schema = {
        "type": "object",
        "properties": {"reference": {"type": ["string", "null"]}},
        "required": ["reference"],
        "additionalProperties": False,
    }
    model = FakeJsonModel({"fields": {
        "reference": {"value": None, "confidence": 0.2, "citations": []}
    }})
    result = await extract_document_fields(
        _parsed(), document_class="reference_document",
        configuration={"extraction_schemas": {"reference_document": schema}}, adapter=model,
    )
    assert result.fields["reference"].value is None
    assert result.review_required is True

    model.response["fields"]["reference"] = {"value": "invented", "confidence": 0.99, "citations": []}
    with pytest.raises(DocumentIntelligenceError, match="source evidence"):
        await extract_document_fields(
            _parsed(), document_class="reference_document",
            configuration={"extraction_schemas": {"reference_document": schema}}, adapter=model,
        )
