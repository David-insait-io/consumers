"""Sample events library for testing loan conversations."""

import uuid
from typing import Dict, Any, List

FLOW_VERSION_ID = "6eb68539-e31a-4075-acbe-707b861f57e7"


def generate_event(
    name: str,
    description: str,
    intent: str,
    goal: str,
    field_values: List[Dict[str, str]]
) -> Dict[str, Any]:
    """Generate a sample event with unique IDs."""
    persona_id = str(uuid.uuid4())
    return {
        "id": str(uuid.uuid4()),
        "flowVersionId": FLOW_VERSION_ID,
        "testGoal": goal,
        "intent": intent,
        "testPersona": {
            "id": persona_id,
            "name": name,
            "description": description,
            "fieldValues": [
                {
                    "id": str(uuid.uuid4()),
                    "testPersonaId": persona_id,
                    "fieldName": fv["fieldName"],
                    "fieldValue": fv["fieldValue"]
                }
                for fv in field_values
            ]
        }
    }


# ============================================================================
# 30 Sample Loan Events
# ============================================================================

SAMPLE_EVENTS: Dict[str, Dict[str, Any]] = {
    # Home Loans
    "home_renovation_kitchen": generate_event(
        name="David",
        description="A 27-year-old software developer looking for a home renovation loan to update his kitchen",
        intent="Get a loan for kitchen renovation",
        goal="User successfully applies for a home renovation loan",
        field_values=[
            {"fieldName": "age", "fieldValue": "27"},
            {"fieldName": "occupation", "fieldValue": "software developer"},
            {"fieldName": "annual_income", "fieldValue": "$85,000"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$25,000"},
        ]
    ),
    "home_renovation_bathroom": generate_event(
        name="Jennifer",
        description="A 35-year-old teacher wanting to renovate two bathrooms in her home",
        intent="Get a loan for bathroom renovation",
        goal="User gets approved for home improvement loan",
        field_values=[
            {"fieldName": "age", "fieldValue": "35"},
            {"fieldName": "occupation", "fieldValue": "high school teacher"},
            {"fieldName": "annual_income", "fieldValue": "$62,000"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$18,000"},
        ]
    ),
    "home_renovation_roof": generate_event(
        name="Robert",
        description="A 52-year-old electrician needing to replace his aging roof",
        intent="Finance a new roof for my house",
        goal="User secures funding for roof replacement",
        field_values=[
            {"fieldName": "age", "fieldValue": "52"},
            {"fieldName": "occupation", "fieldValue": "electrician"},
            {"fieldName": "annual_income", "fieldValue": "$75,000"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$15,000"},
            {"fieldName": "home_age", "fieldValue": "25 years"},
        ]
    ),

    # Car Loans
    "car_loan_used": generate_event(
        name="Sarah",
        description="A 34-year-old nurse looking to finance a reliable used car for commuting",
        intent="Apply for an auto loan to buy a used car",
        goal="User gets approved for a car loan",
        field_values=[
            {"fieldName": "age", "fieldValue": "34"},
            {"fieldName": "occupation", "fieldValue": "registered nurse"},
            {"fieldName": "annual_income", "fieldValue": "$72,000"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$18,000"},
            {"fieldName": "credit_score", "fieldValue": "good"},
        ]
    ),
    "car_loan_new": generate_event(
        name="Marcus",
        description="A 29-year-old sales manager wanting to buy a new SUV for his growing family",
        intent="Finance a new family SUV",
        goal="User gets pre-approved for new car financing",
        field_values=[
            {"fieldName": "age", "fieldValue": "29"},
            {"fieldName": "occupation", "fieldValue": "sales manager"},
            {"fieldName": "annual_income", "fieldValue": "$95,000"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$45,000"},
            {"fieldName": "down_payment", "fieldValue": "$8,000"},
        ]
    ),
    "car_loan_first_time": generate_event(
        name="Ashley",
        description="A 22-year-old recent graduate buying her first car",
        intent="Get my first car loan with limited credit history",
        goal="First-time buyer gets approved for auto loan",
        field_values=[
            {"fieldName": "age", "fieldValue": "22"},
            {"fieldName": "occupation", "fieldValue": "junior analyst"},
            {"fieldName": "annual_income", "fieldValue": "$48,000"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$20,000"},
            {"fieldName": "credit_history", "fieldValue": "limited"},
        ]
    ),

    # Personal Loans
    "personal_loan_debt_consolidation": generate_event(
        name="Michael",
        description="A 42-year-old small business owner wanting to consolidate credit card debt",
        intent="Consolidate high-interest credit card debt",
        goal="User understands personal loan options and rates",
        field_values=[
            {"fieldName": "age", "fieldValue": "42"},
            {"fieldName": "occupation", "fieldValue": "small business owner"},
            {"fieldName": "annual_income", "fieldValue": "$95,000"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$30,000"},
            {"fieldName": "existing_debt", "fieldValue": "$28,000 credit card debt"},
        ]
    ),
    "personal_loan_medical": generate_event(
        name="Patricia",
        description="A 45-year-old office manager needing to cover unexpected medical expenses",
        intent="Get a loan to pay medical bills",
        goal="User secures funding for medical expenses",
        field_values=[
            {"fieldName": "age", "fieldValue": "45"},
            {"fieldName": "occupation", "fieldValue": "office manager"},
            {"fieldName": "annual_income", "fieldValue": "$58,000"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$12,000"},
            {"fieldName": "purpose", "fieldValue": "medical expenses"},
        ]
    ),
    "personal_loan_wedding": generate_event(
        name="Amanda",
        description="A 28-year-old marketing coordinator planning her wedding",
        intent="Finance my upcoming wedding",
        goal="User gets approved for wedding financing",
        field_values=[
            {"fieldName": "age", "fieldValue": "28"},
            {"fieldName": "occupation", "fieldValue": "marketing coordinator"},
            {"fieldName": "annual_income", "fieldValue": "$55,000"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$20,000"},
            {"fieldName": "wedding_date", "fieldValue": "6 months away"},
        ]
    ),
    "personal_loan_vacation": generate_event(
        name="Daniel",
        description="A 38-year-old engineer wanting to take his family on a dream vacation",
        intent="Get a loan for a family vacation",
        goal="User understands vacation loan options",
        field_values=[
            {"fieldName": "age", "fieldValue": "38"},
            {"fieldName": "occupation", "fieldValue": "mechanical engineer"},
            {"fieldName": "annual_income", "fieldValue": "$92,000"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$8,000"},
            {"fieldName": "destination", "fieldValue": "Europe"},
        ]
    ),

    # Student Loans
    "student_loan_refinance": generate_event(
        name="Emily",
        description="A 28-year-old marketing manager with student loans looking to refinance",
        intent="Refinance existing student loans for better rates",
        goal="User gets information about student loan refinancing",
        field_values=[
            {"fieldName": "age", "fieldValue": "28"},
            {"fieldName": "occupation", "fieldValue": "marketing manager"},
            {"fieldName": "annual_income", "fieldValue": "$68,000"},
            {"fieldName": "current_loan_balance", "fieldValue": "$45,000"},
            {"fieldName": "current_interest_rate", "fieldValue": "6.8%"},
        ]
    ),
    "student_loan_graduate": generate_event(
        name="Kevin",
        description="A 24-year-old starting medical school needing student loans",
        intent="Get student loans for medical school",
        goal="User understands graduate student loan options",
        field_values=[
            {"fieldName": "age", "fieldValue": "24"},
            {"fieldName": "program", "fieldValue": "medical school"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$60,000/year"},
            {"fieldName": "program_length", "fieldValue": "4 years"},
        ]
    ),
    "student_loan_parent": generate_event(
        name="Linda",
        description="A 50-year-old accountant looking for parent PLUS loans for her daughter",
        intent="Get a parent loan to help pay for my child's college",
        goal="User learns about parent loan options",
        field_values=[
            {"fieldName": "age", "fieldValue": "50"},
            {"fieldName": "occupation", "fieldValue": "accountant"},
            {"fieldName": "annual_income", "fieldValue": "$85,000"},
            {"fieldName": "child_school", "fieldValue": "state university"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$25,000/year"},
        ]
    ),

    # Mortgage
    "mortgage_first_home": generate_event(
        name="Alex",
        description="A 31-year-old couple looking to buy their first home",
        intent="Get pre-approved for a mortgage as a first-time homebuyer",
        goal="User learns about mortgage options for first home",
        field_values=[
            {"fieldName": "age", "fieldValue": "31"},
            {"fieldName": "occupation", "fieldValue": "accountant"},
            {"fieldName": "combined_annual_income", "fieldValue": "$140,000"},
            {"fieldName": "down_payment_saved", "fieldValue": "$50,000"},
            {"fieldName": "home_price_range", "fieldValue": "$350,000 - $400,000"},
        ]
    ),
    "mortgage_refinance": generate_event(
        name="Thomas",
        description="A 45-year-old homeowner wanting to refinance for a lower rate",
        intent="Refinance my existing mortgage",
        goal="User gets refinancing options and rates",
        field_values=[
            {"fieldName": "age", "fieldValue": "45"},
            {"fieldName": "occupation", "fieldValue": "IT director"},
            {"fieldName": "annual_income", "fieldValue": "$135,000"},
            {"fieldName": "current_mortgage_balance", "fieldValue": "$280,000"},
            {"fieldName": "current_rate", "fieldValue": "5.5%"},
            {"fieldName": "home_value", "fieldValue": "$450,000"},
        ]
    ),
    "mortgage_investment": generate_event(
        name="Richard",
        description="A 40-year-old investor looking to buy a rental property",
        intent="Get a mortgage for an investment property",
        goal="User understands investment property loan requirements",
        field_values=[
            {"fieldName": "age", "fieldValue": "40"},
            {"fieldName": "occupation", "fieldValue": "real estate investor"},
            {"fieldName": "annual_income", "fieldValue": "$180,000"},
            {"fieldName": "existing_properties", "fieldValue": "2"},
            {"fieldName": "down_payment", "fieldValue": "25%"},
        ]
    ),
    "mortgage_va": generate_event(
        name="James",
        description="A 35-year-old veteran looking to use VA loan benefits",
        intent="Apply for a VA home loan",
        goal="Veteran learns about VA loan benefits and process",
        field_values=[
            {"fieldName": "age", "fieldValue": "35"},
            {"fieldName": "occupation", "fieldValue": "federal employee"},
            {"fieldName": "annual_income", "fieldValue": "$78,000"},
            {"fieldName": "military_service", "fieldValue": "8 years Army"},
            {"fieldName": "home_price_range", "fieldValue": "$300,000 - $350,000"},
        ]
    ),

    # Business Loans
    "business_loan_startup": generate_event(
        name="Nicole",
        description="A 33-year-old entrepreneur starting a boutique bakery",
        intent="Get a small business loan to start my bakery",
        goal="User understands startup financing options",
        field_values=[
            {"fieldName": "age", "fieldValue": "33"},
            {"fieldName": "business_type", "fieldValue": "bakery"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$75,000"},
            {"fieldName": "business_plan", "fieldValue": "completed"},
            {"fieldName": "personal_investment", "fieldValue": "$25,000"},
        ]
    ),
    "business_loan_expansion": generate_event(
        name="Christopher",
        description="A 48-year-old restaurant owner wanting to open a second location",
        intent="Get funding to expand my restaurant business",
        goal="Business owner secures expansion financing",
        field_values=[
            {"fieldName": "age", "fieldValue": "48"},
            {"fieldName": "business_type", "fieldValue": "restaurant"},
            {"fieldName": "years_in_business", "fieldValue": "7"},
            {"fieldName": "annual_revenue", "fieldValue": "$850,000"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$200,000"},
        ]
    ),
    "business_loan_equipment": generate_event(
        name="Brian",
        description="A 41-year-old contractor needing to purchase new construction equipment",
        intent="Finance new construction equipment",
        goal="User gets approved for equipment financing",
        field_values=[
            {"fieldName": "age", "fieldValue": "41"},
            {"fieldName": "business_type", "fieldValue": "construction"},
            {"fieldName": "years_in_business", "fieldValue": "12"},
            {"fieldName": "equipment_needed", "fieldValue": "excavator"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$150,000"},
        ]
    ),

    # Special Circumstances
    "loan_bad_credit": generate_event(
        name="Steven",
        description="A 36-year-old warehouse worker with poor credit trying to rebuild",
        intent="Get a loan despite having bad credit",
        goal="User with poor credit learns about available options",
        field_values=[
            {"fieldName": "age", "fieldValue": "36"},
            {"fieldName": "occupation", "fieldValue": "warehouse supervisor"},
            {"fieldName": "annual_income", "fieldValue": "$52,000"},
            {"fieldName": "credit_score", "fieldValue": "550"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$5,000"},
        ]
    ),
    "loan_self_employed": generate_event(
        name="Maria",
        description="A 39-year-old freelance graphic designer seeking a personal loan",
        intent="Get a loan as a self-employed person",
        goal="Self-employed user understands loan requirements",
        field_values=[
            {"fieldName": "age", "fieldValue": "39"},
            {"fieldName": "occupation", "fieldValue": "freelance graphic designer"},
            {"fieldName": "annual_income", "fieldValue": "$75,000"},
            {"fieldName": "years_self_employed", "fieldValue": "5"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$20,000"},
        ]
    ),
    "loan_senior": generate_event(
        name="Dorothy",
        description="A 68-year-old retiree looking for a reverse mortgage",
        intent="Learn about reverse mortgage options",
        goal="Senior understands reverse mortgage benefits and risks",
        field_values=[
            {"fieldName": "age", "fieldValue": "68"},
            {"fieldName": "occupation", "fieldValue": "retired"},
            {"fieldName": "home_value", "fieldValue": "$350,000"},
            {"fieldName": "mortgage_remaining", "fieldValue": "$45,000"},
            {"fieldName": "monthly_income", "fieldValue": "$3,200 (Social Security + pension)"},
        ]
    ),

    # Emergency/Quick Loans
    "emergency_loan": generate_event(
        name="Carlos",
        description="A 30-year-old retail manager needing quick cash for car repair",
        intent="Get an emergency loan for urgent car repair",
        goal="User gets fast approval for emergency funds",
        field_values=[
            {"fieldName": "age", "fieldValue": "30"},
            {"fieldName": "occupation", "fieldValue": "retail manager"},
            {"fieldName": "annual_income", "fieldValue": "$48,000"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$3,000"},
            {"fieldName": "urgency", "fieldValue": "need funds within 48 hours"},
        ]
    ),
    "payday_alternative": generate_event(
        name="Jessica",
        description="A 26-year-old server looking for alternatives to payday loans",
        intent="Find a better option than payday loans",
        goal="User learns about payday loan alternatives",
        field_values=[
            {"fieldName": "age", "fieldValue": "26"},
            {"fieldName": "occupation", "fieldValue": "restaurant server"},
            {"fieldName": "annual_income", "fieldValue": "$32,000"},
            {"fieldName": "loan_amount_needed", "fieldValue": "$1,500"},
            {"fieldName": "repayment_preference", "fieldValue": "flexible"},
        ]
    ),

    # Specific Purpose Loans
    "solar_panel_loan": generate_event(
        name="Gregory",
        description="A 44-year-old homeowner wanting to install solar panels",
        intent="Finance solar panel installation",
        goal="User understands solar financing options",
        field_values=[
            {"fieldName": "age", "fieldValue": "44"},
            {"fieldName": "occupation", "fieldValue": "software architect"},
            {"fieldName": "annual_income", "fieldValue": "$125,000"},
            {"fieldName": "home_value", "fieldValue": "$400,000"},
            {"fieldName": "solar_system_cost", "fieldValue": "$28,000"},
        ]
    ),
    "pool_loan": generate_event(
        name="Michelle",
        description="A 47-year-old dentist wanting to build a swimming pool",
        intent="Get a loan to build a pool in my backyard",
        goal="User gets approved for pool financing",
        field_values=[
            {"fieldName": "age", "fieldValue": "47"},
            {"fieldName": "occupation", "fieldValue": "dentist"},
            {"fieldName": "annual_income", "fieldValue": "$165,000"},
            {"fieldName": "home_value", "fieldValue": "$550,000"},
            {"fieldName": "pool_cost_estimate", "fieldValue": "$65,000"},
        ]
    ),
    "boat_loan": generate_event(
        name="William",
        description="A 55-year-old business executive wanting to buy a fishing boat",
        intent="Finance a recreational boat purchase",
        goal="User learns about marine financing options",
        field_values=[
            {"fieldName": "age", "fieldValue": "55"},
            {"fieldName": "occupation", "fieldValue": "VP of Operations"},
            {"fieldName": "annual_income", "fieldValue": "$195,000"},
            {"fieldName": "boat_price", "fieldValue": "$85,000"},
            {"fieldName": "down_payment", "fieldValue": "20%"},
        ]
    ),
    "rv_loan": generate_event(
        name="Barbara",
        description="A 58-year-old couple planning to travel in retirement",
        intent="Get financing for an RV",
        goal="User understands RV loan options and terms",
        field_values=[
            {"fieldName": "age", "fieldValue": "58"},
            {"fieldName": "occupation", "fieldValue": "school administrator"},
            {"fieldName": "combined_income", "fieldValue": "$140,000"},
            {"fieldName": "rv_price", "fieldValue": "$120,000"},
            {"fieldName": "planned_use", "fieldValue": "full-time travel in retirement"},
        ]
    ),
}


def get_events(count: int = None) -> Dict[str, Dict[str, Any]]:
    """
    Get sample events, optionally limited to a specific count.

    Args:
        count: Number of events to return. If None, returns all events.

    Returns:
        Dictionary of event name to event data
    """
    if count is None:
        return SAMPLE_EVENTS

    event_items = list(SAMPLE_EVENTS.items())[:count]
    return dict(event_items)


def get_event_names() -> List[str]:
    """Get list of all event names."""
    return list(SAMPLE_EVENTS.keys())
