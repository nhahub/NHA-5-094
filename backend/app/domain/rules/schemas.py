import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict
from app.domain.rules.models import RuleSeverity


class BusinessRuleBase(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    rule_type: str = "EQUALITY"
    expression: Dict[str, Any]
    severity: RuleSeverity = RuleSeverity.ERROR


class BusinessRuleCreate(BusinessRuleBase):
    process_version_id: uuid.UUID


class BusinessRuleRead(BusinessRuleBase):
    id: uuid.UUID
    process_version_id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CalculationDefinitionBase(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    calculation_type: str = "FORMULA"
    configuration: Dict[str, Any]


class CalculationDefinitionCreate(CalculationDefinitionBase):
    process_version_id: uuid.UUID


class CalculationDefinitionRead(CalculationDefinitionBase):
    id: uuid.UUID
    process_version_id: uuid.UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class RuleEvaluationRequest(BaseModel):
    rule_id: Optional[uuid.UUID] = None
    expression: Optional[Dict[str, Any]] = None
    context_data: Dict[str, Any] = {}


class RuleEvaluationResult(BaseModel):
    rule_id: Optional[uuid.UUID] = None
    passed: bool
    message: str
    severity: RuleSeverity = RuleSeverity.ERROR
    details: Dict[str, Any] = {}


class CalculationRequest(BaseModel):
    calculation_id: Optional[uuid.UUID] = None
    formula: Optional[Union[Dict[str, Any], str]] = None
    context_data: Dict[str, Any] = {}


class CalculationResult(BaseModel):
    calculation_id: Optional[uuid.UUID] = None
    value: Any = None
    status: str = "SUCCESS"
    error: Optional[str] = None
