"""Static seed corpus for a fresh knowledge base.

Each entry becomes one kb_entries row. `source='static_profile'` entries
resolve their answer live from the user's profile.json via
knowledge/resolver.py; `source='computed'` entries resolve via a small
function registry in resolver.py (falling back to the literal `answer` given
here for constants that never change).

Adding an intent here is how the bot gets better at reading application
forms: KBStore.sync_seeds() folds new entries (and new phrasings of existing
ones) into knowledge bases that already exist, so a question that used to
stop and ask starts answering itself.
"""

SEED_ENTRIES = [
    {
        "tag": "full_name",
        "canonical_question": "What is your full name?",
        "variants": [
            "What is your full name?", "Tell me your full name.",
            "What is your name?", "Can I have your full name?",
            "Please provide your complete name.", "Your name?",
        ],
        "source": "static_profile", "profile_field": "Full name",
    },
    {
        "tag": "first_name",
        "canonical_question": "What is your first name?",
        "variants": [
            "What is your first name?", "Tell me your first name.",
            "What is your given name?", "Can I know your first name?",
            "First name please.",
        ],
        "source": "static_profile", "profile_field": "First name",
    },
    {
        "tag": "last_name",
        "canonical_question": "What is your last name?",
        "variants": [
            "What is your last name?", "What is your surname?",
            "Tell me your last name.", "Your family name?", "Last name?",
        ],
        "source": "static_profile", "profile_field": "Last name",
    },
    {
        # Without this, "What is your father's name?" matches the candidate's
        # own `full_name` intent at 100% — "what is your name?" is a token
        # subset of it — and answers with the applicant's name. Pointing these
        # at their own (blank by default) fields makes the bot ask instead.
        "tag": "father_name",
        "canonical_question": "What is your father's name?",
        "variants": [
            "What is your father's name?", "Father's name", "Fathers name?",
            "Name of your father?", "Please enter your father's name.",
            "What is your parent's name?", "Guardian's name?",
        ],
        "source": "static_profile", "profile_field": "Father's name",
    },
    {
        "tag": "mother_name",
        "canonical_question": "What is your mother's name?",
        "variants": [
            "What is your mother's name?", "Mother's name", "Mothers name?",
            "Name of your mother?", "Please enter your mother's name.",
        ],
        "source": "static_profile", "profile_field": "Mother's name",
    },
    {
        "tag": "marital_status",
        "canonical_question": "What is your marital status?",
        "variants": [
            "What is your marital status?", "Are you married?",
            "Marital status?", "Single or married?",
        ],
        "source": "static_profile", "profile_field": "Marital status",
    },
    {
        "tag": "gender",
        "canonical_question": "What is your gender?",
        "variants": [
            "What is your gender?", "What do you identify as?", "Gender",
            "Please select your gender.", "Male or Female?",
        ],
        "source": "static_profile", "profile_field": "Gender",
    },
    {
        "tag": "mobile",
        "canonical_question": "What is your mobile number?",
        "variants": [
            "What is your mobile number?", "Tell me your phone number.",
            "What is your cell phone number?",
            "Can I have your mobile phone number?", "Contact number?", "Phone?",
        ],
        "source": "static_profile", "profile_field": "Mobile",
    },
    {
        "tag": "email",
        "canonical_question": "What is your email address?",
        "variants": [
            "What is your email address?", "Tell me your email.",
            "What is your email?", "Can I have your email?",
            "Email address please.", "Your email ID?",
        ],
        "source": "static_profile", "profile_field": "Email",
    },
    {
        "tag": "location",
        "canonical_question": "Where are you located?",
        "variants": [
            "Where are you located?", "What is your location?",
            "Where do you live?", "Your current city?",
            "Which state are you from?", "Current location?",
            "Which city do you reside in?",
        ],
        "source": "static_profile", "profile_field": "Location",
    },
    {
        "tag": "current_salary",
        "canonical_question": "What is your current salary?",
        "variants": [
            "What is your current salary?", "What is your CTC?",
            "How much are you earning?", "What is your income?",
            "Current annual package?", "Present salary?",
            "Current CTC?", "What is your last drawn salary?",
        ],
        "source": "static_profile", "profile_field": "Salary",
    },
    {
        "tag": "date_of_birth",
        "canonical_question": "What is your date of birth?",
        "variants": [
            "What is your date of birth?", "When is your birthday?",
            "What is your DOB?", "Your birth date?", "Date of birth?",
        ],
        "source": "static_profile", "profile_field": "Date of birth",
    },
    {
        "tag": "expected_salary",
        "canonical_question": "What is your expected salary?",
        "variants": [
            "What is your expected salary?", "What is your desired CTC?",
            "What salary are you expecting?", "Your expected income?",
            "Expected package?", "What is your salary expectation?",
            "Expected CTC?",
        ],
        "source": "static_profile", "profile_field": "Expected salary",
    },
    {
        "tag": "preferred_location",
        "canonical_question": "What is your preferred work location?",
        "variants": [
            "What is your preferred work location?",
            "Where do you prefer to work?",
            "What is your desired job location?",
            "Your preferred city for work?", "Preferred location?",
        ],
        "source": "static_profile", "profile_field": "Preferred work location",
    },
    {
        "tag": "notice_period",
        "canonical_question": "What is your notice period?",
        "variants": [
            "What is your notice period?", "When can you join?",
            "What is your availability to join?", "How soon can you start?",
            "Joining time?", "How many days notice period do you have?",
            "Earliest joining date?",
        ],
        "source": "static_profile", "profile_field": "Notice period",
    },
    {
        "tag": "current_experience",
        "canonical_question": "How many years of experience do you have?",
        "variants": [
            "How many years of experience do you have?",
            "What is your total experience?",
            "How much experience do you have?",
            "Your total work experience?", "Current professional experience?",
            "Total years in industry?", "Years of work experience?",
            "Total professional experience?", "Years of overall experience?",
            "Relevant years of experience?", "What is your relevant experience?",
        ],
        "source": "static_profile", "profile_field": "Total experience",
    },
    {
        "tag": "bool_employee",
        "canonical_question": "Have you worked at our organization?",
        "variants": [
            "Have you worked at our organization?",
            "Were you previously employed by this organization?",
            "Did you work for us before?", "Any prior employment here?",
            "Have you ever worked with this company?",
            "Have you previously worked for us?",
            "Any previous work experience with our company?",
            "Did you work here before?", "Have you worked here previously?",
        ],
        "source": "computed", "answer": "No",
    },
    {
        "tag": "last_working_day",
        "canonical_question": "What is your last working day?",
        "variants": [
            "What is your last working day?",
            "When is your last day at your current company?",
            "What is your last date of employment?",
            "When can you serve your last day?", "Last working day?",
            "When is your last day?", "What is your last date?",
            "Last day of work?",
        ],
        "source": "computed", "answer": "30 days",
    },
    {
        "tag": "tool_implemented",
        "canonical_question": "Have you implemented this tool?",
        "variants": [
            "Have you implemented this tool?",
            "Have you worked with this technology before?",
            "Have you used this tool?",
            "Do you have hands-on experience with this?",
            "Have you implemented this?", "Have you worked on this technology?",
            "Have you used this technology?", "Have you worked with this tool?",
            "Have you ever used this?", "Any hands-on experience with this tool?",
            "Have you implemented anything with this tool?",
            "Do you have experience implementing this?",
            "Have you used this in production?", "Have you worked on this before?",
        ],
        "source": "computed", "answer": "Yes",
    },
    {
        "tag": "salutation",
        "canonical_question": "How should we address you?",
        "variants": [
            "How should we address you?", "What is your salutation?",
            "What is your title?", "How do you prefer to be addressed?",
            "Mr., Ms., or Dr.?",
        ],
        "source": "static_profile", "profile_field": "Salutation",
    },
    {
        "tag": "privacy_policy_consent",
        "canonical_question": "I consent to the Privacy Policy",
        "variants": [
            "I consent to the Privacy Policy", "Do you agree to the Privacy Policy?",
            "I accept the Privacy Policy", "Consent to the Privacy Policy",
            "Do you agree to our terms?", "Accept terms and conditions?",
        ],
        "source": "computed", "answer": "Yes",
    },
    {
        # Kept strictly yes/no. Phrasings that ask the candidate to *pick a
        # city* used to live here too, which meant a question like "select the
        # city you are residing in or willing to relocate to" matched this
        # intent and got answered "Yes" — see `city_selection` below.
        "tag": "relocation_bool",
        "canonical_question": "Are you willing to relocate?",
        "variants": [
            "Are you willing to relocate?", "Open to relocation?",
            "Would you move to a different city for this role?",
            "Are you open to relocating for this job?",
            "Can you relocate if required?",
        ],
        "source": "static_profile", "profile_field": "Relocate",
    },
    {
        "tag": "city_selection",
        "canonical_question": "Which city are you currently residing in or willing to relocate to?",
        "variants": [
            "Please select the city you are currently residing or willing to relocate to",
            "Please select the city you are currently residing or willing to relocate to.",
            "Select the city you are currently residing in or willing to relocate to",
            "Which city are you currently residing in or willing to relocate to?",
            "Select your preferred work city", "Choose your preferred location",
            "Which location would you prefer to work from?",
            "Select the city you would like to work in",
            "Pick your preferred job location",
            "Which city do you prefer?", "Which city would you prefer?",
            "Preferred city?", "Which location do you prefer?",
            "Which city are you comfortable working in?",
        ],
        "source": "static_profile", "profile_field": "Preferred work location",
    },
    {
        "tag": "current_industry",
        "canonical_question": "Which industry are you currently working in?",
        "variants": [
            "Which industry you are currently working in?",
            "Which industry are you currently working in?",
            "What industry do you work in?", "Your current industry?",
            "Which domain are you working in?", "What is your current domain?",
            "Which sector do you work in?",
        ],
        "source": "computed", "answer": "IT Services & Consulting",
    },
    {
        "tag": "third_party_payroll",
        "canonical_question": "Are you comfortable working on a third-party payroll and being deployed at a client?",
        "variants": [
            "Are you okay to work on a permanent payroll and to be deployed at a client?",
            "Are you comfortable working on third party payroll?",
            "Are you okay with being deployed at a client location?",
            "Would you be willing to work on our payroll deployed at a client site?",
            "Are you fine with a contract-to-hire role?",
            "Are you okay working at a client location?",
            "Are you comfortable with a consulting/deputation role?",
        ],
        "source": "computed", "answer": "Yes",
    },
    {
        "tag": "work_from_office",
        "canonical_question": "Are you comfortable working from the office?",
        "variants": [
            "Are you comfortable working from office?",
            "Are you okay with work from office?",
            "Can you work from the office?",
            "Are you willing to work onsite?",
            "Is hybrid working acceptable to you?",
            "Are you comfortable with a 5-day work from office role?",
        ],
        "source": "computed", "answer": "Yes",
    },
    {
        "tag": "notice_period_negotiable",
        "canonical_question": "Is your notice period negotiable?",
        "variants": [
            "Is your notice period negotiable?",
            "Can your notice period be negotiated?",
            "Can you buy out your notice period?",
            "Is early release possible?",
        ],
        "source": "static_profile", "profile_field": "Notice period negotiable",
    },
    {
        "tag": "interview_availability",
        "canonical_question": "Are you available for an interview?",
        "variants": [
            "Are you available for an interview?",
            "Can you attend the interview this week?",
            "Are you available for a face-to-face interview?",
            "Would you be available for a weekend interview?",
            "Are you available for a virtual interview?",
        ],
        "source": "computed", "answer": "Yes",
    },
    {
        "tag": "offers_in_hand",
        "canonical_question": "Do you have any other offers in hand?",
        "variants": [
            "Do you have any other offers in hand?",
            "Any offers in hand?", "Are you holding any other offer?",
            "Do you have competing offers?",
        ],
        "source": "computed", "answer": "No",
    },
    {
        "tag": "employment_status",
        "canonical_question": "Are you currently employed?",
        "variants": [
            "Are you currently employed?", "What is your employment status?",
            "Are you working currently?", "Current job status?",
        ],
        "source": "computed", "answer": "Yes",
    },
    {
        "tag": "education",
        "canonical_question": "What is your highest qualification?",
        "variants": [
            "What is your highest qualification?",
            "Your educational background?", "Highest degree obtained?",
            "What did you study?", "Your academic qualification?",
        ],
        "source": "static_profile", "profile_field": "Highest qualification",
    },
    {
        "tag": "fresher_or_exp",
        "canonical_question": "Are you a fresher or experienced?",
        "variants": [
            "Are you a fresher or experienced?", "How would you describe yourself?",
            "Fresher or experienced professional?",
        ],
        "source": "computed", "answer": "Experienced",
    },
    {
        "tag": "passport",
        "canonical_question": "Do you have a passport?",
        "variants": [
            "Do you have a passport?", "Do you hold a valid passport?",
            "Passport available?",
        ],
        "source": "static_profile", "profile_field": "Passport",
    },
    {
        "tag": "shift_willingness",
        "canonical_question": "Are you willing to work in shifts?",
        "variants": [
            "Are you willing to work in shifts?", "Can you work in rotational shifts?",
            "Night shift availability?", "Shift preference?",
            "Are you comfortable with rotational shifts?",
            "Are you comfortable working in night shifts?",
            "Are you okay with shift work?",
        ],
        "source": "static_profile", "profile_field": "Shift willingness",
    },
    {
        "tag": "vehicle",
        "canonical_question": "Do you have a two-wheeler?",
        "variants": [
            "Do you have a two-wheeler?", "Do you own a vehicle?",
            "Do you have your own vehicle?", "Own a bike or car?",
        ],
        "source": "static_profile", "profile_field": "Vehicle",
    },
    {
        "tag": "immediately_available",
        "canonical_question": "Are you immediately available to join?",
        "variants": [
            "Are you immediately available to join?", "Immediate joiner?",
            "Can you join immediately?", "Availability to join immediately?",
        ],
        "source": "static_profile", "profile_field": "Immediately available",
    },
    {
        "tag": "work_authorization",
        "canonical_question": "Are you authorized to work in this country?",
        "variants": [
            "Are you authorized to work in this country?",
            "Are you legally eligible to work here?",
            "Work authorization status?",
        ],
        # Sponsorship used to live here, but it is the opposite question:
        # authorized to work = Yes means sponsorship required = No.
        "retired_variants": ["Do you require visa sponsorship?"],
        "source": "static_profile", "profile_field": "Work authorization",
    },
    {
        "tag": "visa_sponsorship",
        "canonical_question": "Do you require visa sponsorship?",
        "variants": [
            "Do you require visa sponsorship?",
            "Will you now or in the future require sponsorship for employment?",
            "Will you require sponsorship for employment visa status?",
            "Do you need employer sponsorship to work?",
            "Will you need H-1B visa sponsorship?",
            "Do you require a work visa?",
        ],
        "source": "static_profile", "profile_field": "Visa sponsorship required",
    },
    {
        "tag": "previous_company",
        "canonical_question": "What is your previous/current company?",
        "variants": [
            "What is your current company?", "What is your previous company?",
            "Which company do you work for?", "Your present employer?",
            "Name of your current organization?",
        ],
        "source": "static_profile", "profile_field": "Current company",
    },
    {
        "tag": "current_designation",
        "canonical_question": "What is your current designation?",
        "variants": [
            "What is your current designation?", "Your current job title?",
            "What is your current role?", "Current position held?",
        ],
        "source": "static_profile", "profile_field": "Current designation",
    },
]


def skill_intent(skill, exp):
    return {
        "tag": f"skill_exp::{skill.lower().replace(' ', '_')}",
        "canonical_question": f"How many years of experience do you have in {skill}?",
        "variants": [
            f"How many years of experience do you have in {skill}?",
            f"Experience in {skill}", f"How long have you been working with {skill}?",
            f"Years of {skill} experience?", f"Rate your {skill} expertise.",
            f"Do you know {skill}? How long?",
        ],
        "source": "static_profile", "profile_field": f"Skills.{skill}",
    }


def skills_summary_intent():
    return {
        "tag": "skills_summary",
        "canonical_question": "What are your key skills?",
        "variants": [
            "What are your key skills?", "Tell me your skills.",
            "What skills do you have?", "Your key competencies?",
            "List your technical skills.", "What technologies do you know?",
        ],
        "source": "computed", "answer": "",
    }


def build_seed_entries(profile: dict) -> list:
    """Combine the static list with per-user dynamic skill intents."""
    entries = [dict(e) for e in SEED_ENTRIES]
    skills = profile.get("Skills") or {}
    for skill, exp in skills.items():
        entries.append(skill_intent(skill, exp))
    if skills:
        entries.append(skills_summary_intent())
    return entries
